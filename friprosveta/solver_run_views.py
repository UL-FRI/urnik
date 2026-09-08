from io import StringIO
from threading import Thread
from typing import Dict

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from timetable.models import Timetable

from .solver_run_forms import RunOptionsForm


SOLVER_GENERATION_LOCK_PREFIX = "friprosveta:solver-generation-lock"
SOLVER_GENERATION_STATE_PREFIX = "friprosveta:solver-generation-state"
SOLVER_GENERATION_CACHE_TTL_SECONDS = 60 * 60 * 12


def _require_staff(user):
    if not (user.is_authenticated and user.is_superuser):
        raise PermissionDenied


def _lock_key(timetable_slug: str) -> str:
    return "{}:{}".format(SOLVER_GENERATION_LOCK_PREFIX, timetable_slug)


def _state_key(timetable_slug: str) -> str:
    return "{}:{}".format(SOLVER_GENERATION_STATE_PREFIX, timetable_slug)


def _mark_running_state(timetable_slug: str, data: Dict[str, object]) -> None:
    cache.set(
        _state_key(timetable_slug),
        data,
        timeout=SOLVER_GENERATION_CACHE_TTL_SECONDS,
    )


def _mark_finished_state(timetable_slug: str, data: Dict[str, object]) -> None:
    cache.set(
        _state_key(timetable_slug),
        data,
        timeout=SOLVER_GENERATION_CACHE_TTL_SECONDS,
    )


def get_solver_generation_status(timetable_slug):
    """Return latest generation state for a timetable if available."""
    state = cache.get(_state_key(timetable_slug))
    if not isinstance(state, dict):
        return None
    state = dict(state)
    state["is_running"] = is_generation_running(timetable_slug)
    return state


def is_generation_running(timetable_slug):
    """Return ``True`` when a generation lock exists for the timetable."""
    return bool(cache.get(_lock_key(timetable_slug)))


def _run_preview(request, timetable_slug, repair):
    _require_staff(request.user)
    timetable = get_object_or_404(Timetable, slug=timetable_slug)
    command = None
    output = None
    succeeded = None
    generation_status = get_solver_generation_status(timetable_slug)
    generation_running = is_generation_running(timetable_slug)

    if request.method == "POST":
        form = RunOptionsForm(request.POST, timetable=timetable, repair=repair)
        if form.is_valid():
            command = form.command(timetable_slug)
            if request.POST.get("action") == "run":
                if generation_running:
                    form.add_error(None, "A solver generation is already running for this timetable.")
                    output = None
                    succeeded = False
                else:
                    data = form.cleaned_data
                    stream = StringIO()
                    started_at = timezone.now()
                    lock_token = started_at.isoformat()
                    lock_key = _lock_key(timetable_slug)
                    if not cache.add(lock_key, lock_token, timeout=SOLVER_GENERATION_CACHE_TTL_SECONDS):
                        form.add_error(
                            None,
                            "A solver generation is already running for this timetable.",
                        )
                        generation_running = True
                        generation_status = get_solver_generation_status(timetable_slug)
                        if not isinstance(generation_status, dict):
                            generation_status = {"is_running": True, "status": "running"}
                    else:
                        command_payload = {
                            "timetable_slug": timetable_slug,
                            "status": "running",
                            "is_running": True,
                            "mode": data["mode"],
                            "repair": repair,
                            "command": command,
                            "started_at": started_at.isoformat(),
                            "started_by": request.user.get_username(),
                        }
                        _mark_running_state(timetable_slug, command_payload)

                        def run_generation():
                            close_old_connections()
                            final_payload = dict(command_payload)
                            try:
                                call_command(
                                    "ortools_generate",
                                    timetable_slug,
                                    stdout=stream,
                                    stderr=stream,
                                    time_limit=data["time_limit"],
                                    debug=data["debug"],
                                    progress_every=data["progress_every"],
                                    build_timeout=data["build_timeout"],
                                    num_search_workers=data["num_search_workers"],
                                    max_memory_mb=data["max_memory_mb"] or 4096,
                                    clear_existing=data["clear_existing"],
                                    ready_only=data["ready_only"],
                                    allocation_time_weight=data["allocation_time_weight"],
                                    allocation_room_weight=data["allocation_room_weight"],
                                    cross_section_razor=data["cross_section_razor"],
                                    cross_section_group_razor=data[
                                        "cross_section_group_razor"
                                    ],
                                    mode=data["mode"],
                                    repair_realization=[
                                        r.id for r in data.get("repair_realization", [])
                                    ],
                                )
                                final_payload["status"] = "succeeded"
                                final_payload["error"] = None
                            except CommandError as error:
                                stream.write("ERROR: {}\n".format(error))
                                final_payload["status"] = "failed"
                                final_payload["error"] = str(error)
                            except Exception as error:
                                stream.write("UNEXPECTED ERROR: {}\n".format(error))
                                final_payload["status"] = "failed"
                                final_payload["error"] = str(error)
                            finally:
                                final_payload["finished_at"] = timezone.now().isoformat()
                                final_payload["is_running"] = False
                                final_payload["output"] = stream.getvalue()
                                _mark_finished_state(timetable_slug, final_payload)
                                cache.delete(lock_key)
                                close_old_connections()

                        thread = Thread(target=run_generation, daemon=True)
                        thread.start()
                        return HttpResponseRedirect(
                            reverse("solver_dashboard", kwargs={"timetable_slug": timetable_slug})
                        )
            else:
                output = None

    else:
        form = RunOptionsForm(timetable=timetable, repair=repair)
    
    return render(
        request,
        "friprosveta/solver_run_preview.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
            "command": command,
            "is_repair": repair,
            "output": output,
            "succeeded": succeeded,
            "generation_status": generation_status,
            "generation_running": generation_running,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def solver_run_preview(request, timetable_slug):
    return _run_preview(request, timetable_slug, repair=False)


@login_required
@require_http_methods(["GET", "POST"])
def solver_repair_preview(request, timetable_slug):
    return _run_preview(request, timetable_slug, repair=True)
