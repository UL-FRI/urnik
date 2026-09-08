from datetime import date
from io import StringIO
from threading import Thread

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

from .studis_workflow_forms import (
    CreateActivitiesForm,
    CreateRealizationsForm,
    CreateTopLevelGroupsForm,
    FindMissingTeachersForm,
    ImportNajaveForm,
    ImportStudentsForm,
    RemovePadGroupsForm,
    SyncSubjectsForm,
)


STUDIS_WORKFLOW_LOCK_PREFIX = "friprosveta:studis-workflow-lock"
STUDIS_WORKFLOW_STATE_PREFIX = "friprosveta:studis-workflow-state"
STUDIS_WORKFLOW_CACHE_TTL_SECONDS = 60 * 60 * 12


def _lock_key(timetable_slug):
    return "{}:{}".format(STUDIS_WORKFLOW_LOCK_PREFIX, timetable_slug)


def _state_key(timetable_slug):
    return "{}:{}".format(STUDIS_WORKFLOW_STATE_PREFIX, timetable_slug)


def _mark_running_state(timetable_slug, data):
    cache.set(
        _state_key(timetable_slug),
        data,
        timeout=STUDIS_WORKFLOW_CACHE_TTL_SECONDS,
    )


def _mark_finished_state(timetable_slug, data):
    cache.set(
        _state_key(timetable_slug),
        data,
        timeout=STUDIS_WORKFLOW_CACHE_TTL_SECONDS,
    )


def get_studis_workflow_status(timetable_slug):
    """Return latest Studis workflow state for a timetable if available."""
    state = cache.get(_state_key(timetable_slug))
    if not isinstance(state, dict):
        return None
    state = dict(state)
    state["is_running"] = is_studis_workflow_running(timetable_slug)
    return state


def is_studis_workflow_running(timetable_slug):
    """Return ``True`` when a Studis workflow lock exists for timetable."""
    return bool(cache.get(_lock_key(timetable_slug)))


def _require_staff(user):
    if not (user.is_authenticated and user.is_superuser):
        raise PermissionDenied


def _default_form_data():
    """Build initial form data for GET render."""
    default_year = str(date.today().year)
    return {
        "year": default_year,
        "semester_id": "2",
    }


def _run_workflow_async(request, timetable_slug, workflow, command, command_name, *args, **kwargs):
    stream = StringIO()
    started_at = timezone.now()
    lock_key = _lock_key(timetable_slug)
    lock_token = started_at.isoformat()

    if not cache.add(lock_key, lock_token, timeout=STUDIS_WORKFLOW_CACHE_TTL_SECONDS):
        return None

    payload = {
        "timetable_slug": timetable_slug,
        "workflow": workflow,
        "status": "running",
        "is_running": True,
        "command": command,
        "started_at": started_at.isoformat(),
        "started_by": request.user.get_username(),
    }
    _mark_running_state(timetable_slug, payload)

    def run_workflow():
        close_old_connections()
        final_payload = dict(payload)
        try:
            call_command(
                command_name,
                *args,
                stdout=stream,
                stderr=stream,
                **kwargs,
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
            final_output = stream.getvalue()
            if not final_output:
                if final_payload["status"] == "succeeded":
                    final_output = "Command completed without output."
                else:
                    final_output = "Command failed without output."
            final_payload["finished_at"] = timezone.now().isoformat()
            final_payload["is_running"] = False
            final_payload["output"] = final_output
            final_payload["succeeded"] = final_payload["status"] == "succeeded"
            _mark_finished_state(timetable_slug, final_payload)
            cache.delete(lock_key)
            close_old_connections()

    thread = Thread(target=run_workflow, daemon=True)
    thread.start()
    return thread


def _mark_workflow_running_error(form):
    if not hasattr(form, "cleaned_data"):
        form.full_clean()
    form.add_error(
        None,
        "A Studis workflow is already running for this timetable.",
    )


def _studis_workflow_context(
    timetable,
    timetable_slug,
    import_najave_form,
    create_activities_form,
    import_students_form,
    create_realizations_form,
    find_missing_teachers_form,
    remove_pad_groups_form,
    create_top_level_groups_form,
    sync_subjects_form,
    command,
    output,
    succeeded,
    workflow,
    studis_workflow_status,
):
    return {
        "timetable": timetable,
        "timetable_slug": timetable_slug,
        "import_najave_form": import_najave_form,
        "create_activities_form": create_activities_form,
        "import_students_form": import_students_form,
        "create_realizations_form": create_realizations_form,
        "find_missing_teachers_form": find_missing_teachers_form,
        "remove_pad_groups_form": remove_pad_groups_form,
        "create_top_level_groups_form": create_top_level_groups_form,
        "sync_subjects_form": sync_subjects_form,
        "command": command,
        "output": output,
        "succeeded": succeeded,
        "workflow": workflow,
        "studis_workflow_status": studis_workflow_status,
    }


@login_required
@require_http_methods(["GET", "POST"])
def studis_workflow_preview(request, timetable_slug):
    _require_staff(request.user)
    timetable = get_object_or_404(Timetable, slug=timetable_slug)

    default_data = _default_form_data()
    command = None
    output = None
    succeeded = None
    workflow = request.POST.get("workflow") if request.method == "POST" else None
    action = request.POST.get("action") if request.method == "POST" else None
    studis_workflow_status = get_studis_workflow_status(timetable_slug)

    import_najave_form = ImportNajaveForm(
        initial=default_data,
    )
    create_activities_form = CreateActivitiesForm(
        initial=default_data,
    )
    import_students_form = ImportStudentsForm(
        initial={
            "year": int(default_data["year"]),
            "date": date.today(),
        }
    )
    create_realizations_form = CreateRealizationsForm(
        timetable=timetable,
    )
    find_missing_teachers_form = FindMissingTeachersForm(timetable=timetable)
    remove_pad_groups_form = RemovePadGroupsForm()
    create_top_level_groups_form = CreateTopLevelGroupsForm(
        initial=default_data,
    )
    sync_subjects_form = SyncSubjectsForm(request.POST or None)

    if request.method == "POST":
        if workflow == "sync_subjects":
            command = "python3 manage.py sync_subjects True"
            if action == "run":
                thread = _run_workflow_async(
                    request,
                    timetable_slug,
                    workflow,
                    command,
                    "sync_subjects",
                    "True",
                )
                if thread is not None:
                    return HttpResponseRedirect(
                        reverse(
                            "solver_dashboard", kwargs={"timetable_slug": timetable_slug}
                        )
                    )
                _mark_workflow_running_error(sync_subjects_form)

        elif workflow == "import_studis_najave":
            import_najave_form = ImportNajaveForm(
                request.POST,
            )
            if import_najave_form.is_valid():
                command = import_najave_form.command(timetable_slug)
                if action == "run":
                    data = import_najave_form.cleaned_data
                    args = [
                        timetable_slug,
                        str(data["year"]),
                        data["semester_id"],
                    ]
                    kwargs = {}
                    if data.get("subject_code"):
                        kwargs["subject"] = [data["subject_code"]]
                    thread = _run_workflow_async(
                        request,
                        timetable_slug,
                        workflow,
                        command,
                        "import_studis_najave",
                        *args,
                        **kwargs,
                    )
                    if thread is not None:
                        return HttpResponseRedirect(
                            reverse(
                                "solver_dashboard",
                                kwargs={"timetable_slug": timetable_slug},
                            )
                        )
                    _mark_workflow_running_error(import_najave_form)

        elif workflow == "create_activities":
            create_activities_form = CreateActivitiesForm(
                request.POST,
            )
            if create_activities_form.is_valid():
                command = create_activities_form.command(timetable_slug)
                if action == "run":
                    data = create_activities_form.cleaned_data
                    kwargs = {}
                    if data.get("subject_code"):
                        kwargs["subject_code"] = data["subject_code"]
                    thread = _run_workflow_async(
                        request,
                        timetable_slug,
                        workflow,
                        command,
                        "create_activities",
                        timetable_slug,
                        int(data["year"]),
                        data["semester_id"],
                        **kwargs,
                    )
                    if thread is not None:
                        return HttpResponseRedirect(
                            reverse(
                                "solver_dashboard",
                                kwargs={"timetable_slug": timetable_slug},
                            )
                        )
                    _mark_workflow_running_error(create_activities_form)

        elif workflow == "import_studis_students":
            import_students_form = ImportStudentsForm(
                request.POST,
            )
            if import_students_form.is_valid():
                command = import_students_form.command(timetable_slug)
                if action == "run":
                    data = import_students_form.cleaned_data
                    thread = _run_workflow_async(
                        request,
                        timetable_slug,
                        workflow,
                        command,
                        "import_studis_students",
                        timetable_slug,
                        str(data["year"]),
                        data["date"].isoformat(),
                        unconfirmed=data["unconfirmed"],
                        unfinished=data["unfinished"],
                        preenrolment=data["preenrolment"],
                    )
                    if thread is not None:
                        return HttpResponseRedirect(
                            reverse(
                                "solver_dashboard",
                                kwargs={"timetable_slug": timetable_slug},
                            )
                        )
                    _mark_workflow_running_error(import_students_form)

        elif workflow == "create_top_level_groups":
            create_top_level_groups_form = CreateTopLevelGroupsForm(
                request.POST,
            )
            if create_top_level_groups_form.is_valid():
                command = create_top_level_groups_form.command(timetable_slug)
                if action == "run":
                    data = create_top_level_groups_form.cleaned_data
                    thread = _run_workflow_async(
                        request,
                        timetable_slug,
                        workflow,
                        command,
                        "create_top_level_groups",
                        timetable_slug,
                        str(data["year"]),
                        data["semester_id"],
                    )
                    if thread is not None:
                        return HttpResponseRedirect(
                            reverse(
                                "solver_dashboard",
                                kwargs={"timetable_slug": timetable_slug},
                            )
                        )
                    _mark_workflow_running_error(create_top_level_groups_form)

        elif workflow == "create_realizations":
            create_realizations_form = CreateRealizationsForm(
                request.POST,
                timetable=timetable,
            )
            if create_realizations_form.is_valid():
                command = create_realizations_form.command(timetable_slug)
                if action == "run":
                    thread = _run_workflow_async(
                        request,
                        timetable_slug,
                        workflow,
                        command,
                        "create_realizations",
                        timetable_slug,
                        str(create_realizations_form.cleaned_data["timetable_set"].slug),
                    )
                    if thread is not None:
                        return HttpResponseRedirect(
                            reverse(
                                "solver_dashboard",
                                kwargs={"timetable_slug": timetable_slug},
                            )
                        )
                    _mark_workflow_running_error(create_realizations_form)

        elif workflow == "check_durations":
            command = "python3 manage.py check_durations {}".format(timetable_slug)
            if action == "run":
                thread = _run_workflow_async(
                    request,
                    timetable_slug,
                    workflow,
                    command,
                    "check_durations",
                    timetable_slug,
                )
                if thread is not None:
                    return HttpResponseRedirect(
                        reverse(
                            "solver_dashboard", kwargs={"timetable_slug": timetable_slug}
                        )
                    )
                _mark_workflow_running_error(sync_subjects_form)

        elif workflow == "set_visible_groups":
            command = "python3 manage.py set_visible_groups {}".format(timetable_slug)
            if action == "run":
                thread = _run_workflow_async(
                    request,
                    timetable_slug,
                    workflow,
                    command,
                    "set_visible_groups",
                    timetable_slug,
                )
                if thread is not None:
                    return HttpResponseRedirect(
                        reverse(
                            "solver_dashboard", kwargs={"timetable_slug": timetable_slug}
                        )
                    )
                _mark_workflow_running_error(sync_subjects_form)

        elif workflow == "find_missing_teachers":
            find_missing_teachers_form = FindMissingTeachersForm(
                request.POST, timetable=timetable
            )
            if find_missing_teachers_form.is_valid():
                command = find_missing_teachers_form.command(timetable_slug)
                if action == "run":
                    thread = _run_workflow_async(
                        request,
                        timetable_slug,
                        workflow,
                        command,
                        "find_missing_teachers",
                        timetable_slug,
                        find_missing_teachers_form.cleaned_data["timetable_set"].slug,
                    )
                    if thread is not None:
                        return HttpResponseRedirect(
                            reverse(
                                "solver_dashboard", kwargs={"timetable_slug": timetable_slug}
                            )
                        )
                    _mark_workflow_running_error(find_missing_teachers_form)

        elif workflow == "remove_pad_groups":
            remove_pad_groups_form = RemovePadGroupsForm(request.POST)
            if remove_pad_groups_form.is_valid():
                command = remove_pad_groups_form.command(timetable_slug)
                if action == "run":
                    thread = _run_workflow_async(
                        request,
                        timetable_slug,
                        workflow,
                        command,
                        "remove_pad_groups",
                        timetable_slug,
                        dry_run=remove_pad_groups_form.cleaned_data["dry_run"],
                    )
                    if thread is not None:
                        return HttpResponseRedirect(
                            reverse(
                                "solver_dashboard", kwargs={"timetable_slug": timetable_slug}
                            )
                        )
                    _mark_workflow_running_error(remove_pad_groups_form)

    return render(
        request,
        "friprosveta/studis_workflow_preview.html",
        _studis_workflow_context(
            timetable,
            timetable_slug,
            import_najave_form,
            create_activities_form,
            import_students_form,
            create_realizations_form,
            find_missing_teachers_form,
            remove_pad_groups_form,
            create_top_level_groups_form,
            sync_subjects_form,
            command,
            output,
            succeeded,
            workflow,
            studis_workflow_status,
        ),
    )
