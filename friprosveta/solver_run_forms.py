from django import forms

from .solver_forms import _realization_queryset


class RunOptionsForm(forms.Form):
    time_limit = forms.IntegerField(
        min_value=0,
        initial=60,
        label="Time limit (seconds)",
        help_text="Maximum CP-SAT search time. Set 0 to run until CP-SAT proves optimal or infeasible.",
    )
    debug = forms.BooleanField(
        required=False,
        initial=False,
        label="Debug output",
        help_text="Include model-build progress and feasibility diagnostics in the output.",
    )
    progress_every = forms.IntegerField(
        min_value=1,
        initial=50,
        label="Progress every N realizations",
        help_text="How often debug output reports model-build progress.",
    )
    build_timeout = forms.IntegerField(
        min_value=0,
        initial=0,
        label="Build timeout (0 = none)",
        help_text="Stop before search if model construction exceeds this many seconds.",
    )
    num_search_workers = forms.IntegerField(
        min_value=1,
        initial=8,
        label="Number of search workers",
        help_text="Parallel CP-SAT workers. Lower this together with memory on constrained hosts.",
    )
    max_memory_mb = forms.IntegerField(
        min_value=1,
        initial=4096,
        required=False,
        label="Maximum solver memory (MiB)",
        help_text="Defaults to 4096 MiB. Lower the worker count as well on memory-constrained hosts.",
    )
    clear_existing = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Replace existing allocations only after a complete feasible schedule is found.",
    )
    ready_only = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Schedule only activities selected in Scheduling Scope. Required for exclusions to apply.",
    )
    allocation_time_weight = forms.IntegerField(
        min_value=0,
        initial=100,
        help_text="Soft reward for retaining an existing allocation's day and time in improve mode. Set 0 to disable.",
    )
    allocation_room_weight = forms.IntegerField(
        min_value=0,
        initial=25,
        help_text="Soft reward for retaining an existing allocation's classroom in improve mode. Set 0 to disable.",
    )
    cross_section_razor = forms.IntegerField(
        required=False,
        min_value=0,
        initial=None,
        help_text=(
            "Allow student cross-section overlaps up to this number. Larger overlaps "
            "remain prohibited. Leave empty to prohibit every shared-student overlap."
        ),
    )
    cross_section_group_razor = forms.IntegerField(
        required=False,
        min_value=0,
        initial=None,
        help_text=(
            "Ignore group assignments below this effective size for solver group "
            "availability and overlap constraints. Timetable data remains unchanged."
        ),
    )

    def __init__(self, *args, timetable, repair=False, **kwargs):
        super().__init__(*args, **kwargs)
        if repair:
            self.fields["mode"] = forms.ChoiceField(
                choices=(("repair", "repair"),), initial="repair", widget=forms.HiddenInput()
            )
            self.fields["repair_realization"] = forms.ModelMultipleChoiceField(
                queryset=_realization_queryset(timetable),
                required=False,
                widget=forms.SelectMultiple(attrs={"size": "6"}),
                help_text="Only these realizations may move; all other existing allocations stay fixed.",
                label="Realizations to repair",
            )
        else:
            self.fields["mode"] = forms.ChoiceField(
                choices=(("scratch", "Generate from scratch"), ("improve", "Regenerate and prefer current placements")),
                initial="scratch",
                label="Generation strategy",
                help_text="Scratch ignores current placements. Improve treats them as soft preferences.",
            )

    def command(self, timetable_slug):
        data = self.cleaned_data
        parts = [
            "python3 manage.py ortools_generate",
            timetable_slug,
            "--time-limit={}".format(data["time_limit"]),
            "--num-search-workers={}".format(data["num_search_workers"]),
            "--max-memory-mb={}".format(data["max_memory_mb"] or 4096),
            "--progress-every={}".format(data["progress_every"]),
            "--allocation-time-weight={}".format(data["allocation_time_weight"]),
            "--allocation-room-weight={}".format(data["allocation_room_weight"]),
            "--mode={}".format(data["mode"]),
        ]
        if data["debug"]:
            parts.append("--debug")
        if data["build_timeout"]:
            parts.append("--build-timeout={}".format(data["build_timeout"]))
        if data["clear_existing"]:
            parts.append("--clear-existing")
        if data["ready_only"]:
            parts.append("--ready-only")
        if data["cross_section_razor"] is not None:
            parts.append("--cross-section-razor={}".format(data["cross_section_razor"]))
        if data["cross_section_group_razor"] is not None:
            parts.append(
                "--cross-section-group-razor={}".format(
                    data["cross_section_group_razor"]
                )
            )
        for realization in data.get("repair_realization", []):
            parts.append("--repair-realization={}".format(realization.id))
        return " ".join(parts)
