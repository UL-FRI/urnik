"""
Superuser-only, server-rendered view for ``prepare_ortools_groups`` preview and
execution.
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods
from io import StringIO

from timetable.models import Timetable

from .preparation_run_forms import PrepareGroupsOptionsForm


def _require_staff(user):
    if not (user.is_authenticated and user.is_superuser):
        raise PermissionDenied


@login_required
@require_http_methods(["GET", "POST"])
def preparation_preview(request, timetable_slug):
    _require_staff(request.user)
    timetable = get_object_or_404(Timetable, slug=timetable_slug)
    command = None
    output = None
    succeeded = None
    if request.method == "POST":
        form = PrepareGroupsOptionsForm(request.POST, timetable=timetable)
        if form.is_valid():
            command = form.command(timetable_slug)
            if request.POST.get("action") == "run":
                data = form.cleaned_data
                stream = StringIO()
                try:
                    call_command(
                        "prepare_ortools_groups",
                        timetable_slug,
                        data["year"],
                        stdout=stream,
                        stderr=stream,
                        previous_timetable_slug=(
                            data["previous_timetable"].slug
                            if data["previous_timetable"] is not None
                            else None
                        ),
                        hint_sources=data["hint_source"],
                        hint_strategy=data["hint_strategy"],
                        exclude_study=[study.short_name for study in data["exclude_study"]],
                        dry_run=data["dry_run"],
                    )
                    succeeded = True
                except CommandError as error:
                    stream.write("ERROR: {}\n".format(error))
                    succeeded = False
                except Exception as error:
                    stream.write("UNEXPECTED ERROR: {}\n".format(error))
                    succeeded = False
                output = stream.getvalue() or "Command completed without output."
    else:
        form = PrepareGroupsOptionsForm(timetable=timetable)
    return render(
        request,
        "friprosveta/preparation_preview.html",
        {
            "timetable": timetable,
            "timetable_slug": timetable_slug,
            "form": form,
            "command": command,
            "output": output,
            "succeeded": succeeded,
        },
    )
