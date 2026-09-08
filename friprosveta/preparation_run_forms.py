"""
Staff-only, server-rendered form for the ``prepare_ortools_groups`` management
command preview.

This form NEVER executes the management command. It only builds a
copy-pasteable shell command string from validated user input, mirroring the
contract of ``friprosveta/solver_run_forms.py``.

Defaults are intentionally safe: the only hint source selected by default is
``current-enrollments`` (no prior timetable needed). Prior hint sources require
a previous timetable, which the form validates. ``previous-enrollments`` reads
the prior year's imported Studis records directly and is preferred over copied
group membership or size.
"""
from django import forms

from friprosveta.models import Study
from timetable.models import Timetable

HINT_SOURCE_CHOICES = (
    ("current-enrollments", "Current enrollments (safe, no prior timetable)"),
    (
        "previous-enrollments",
        "Previous Studis enrollments (recommended fallback)",
    ),
    (
        "previous-students",
        "Previous group members (legacy, requires prior timetable)",
    ),
    ("previous-size", "Previous group size (legacy, requires prior timetable)"),
)
HINT_STRATEGY_CHOICES = (
    ("first", "first"),
    ("first-non-zero", "first-non-zero"),
    ("max", "max"),
    ("max-non-zero", "max-non-zero"),
    ("max-group", "max-group"),
)
PRIOR_HINT_SOURCES = frozenset(
    ("previous-enrollments", "previous-students", "previous-size")
)


class PrepareGroupsOptionsForm(forms.Form):
    year = forms.CharField(
        max_length=8,
        required=True,
        label="Studis year",
        help_text="Positional year argument passed to the command (e.g. 2026).",
    )
    previous_timetable = forms.ModelChoiceField(
        queryset=Timetable.objects.none(),
        required=False,
        label="Previous timetable",
        help_text=(
            "Required only when a prior hint source is selected. "
            "Use previous Studis enrollments as the recommended fallback. "
            "The current timetable is excluded from this list."
        ),
    )
    hint_source = forms.MultipleChoiceField(
        choices=HINT_SOURCE_CHOICES,
        initial=["current-enrollments"],
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label="Hint sources",
        help_text=(
            "Defaults to current enrollments only, which is safe and needs "
            "no prior timetable. For early preparation, combine current and "
            "previous Studis enrollments with the max strategy."
        ),
    )
    hint_strategy = forms.ChoiceField(
        choices=HINT_STRATEGY_CHOICES,
        initial="max",
        required=True,
        label="Hint strategy",
    )
    exclude_study = forms.ModelMultipleChoiceField(
        queryset=Study.objects.all().order_by("short_name"),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": "6"}),
        label="Excluded studies",
        help_text=(
            "Studies whose lecture groups are not resized or subdivided. "
            "Matches the repeatable --exclude-study option by short name."
        ),
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=False,
        label="Dry run (validate only, roll back all changes)",
    )

    def __init__(self, *args, timetable, **kwargs):
        super().__init__(*args, **kwargs)
        self.timetable = timetable
        # Previous timetable selection excludes the current timetable so an
        # operator cannot point the prior-source workflow at itself.
        self.fields["previous_timetable"].queryset = Timetable.objects.exclude(
            pk=timetable.pk
        ).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        hint_sources = set(cleaned_data.get("hint_source") or [])
        previous_timetable = cleaned_data.get("previous_timetable")
        if hint_sources & PRIOR_HINT_SOURCES and not previous_timetable:
            raise forms.ValidationError(
                "A previous timetable is required when any prior hint source "
                "is selected."
            )
        return cleaned_data

    def command(self, timetable_slug):
        """Build a copy-pasteable shell command from validated cleaned data."""
        data = self.cleaned_data
        parts = [
            "python3 manage.py prepare_ortools_groups",
            timetable_slug,
            str(data["year"]),
        ]
        previous_timetable = data.get("previous_timetable")
        if previous_timetable is not None:
            parts.append("--previous-timetable-slug={}".format(previous_timetable.slug))
        # Preserve submission order while dropping duplicates, matching the
        # management command's dict.fromkeys dedupe.
        seen = set()
        for hint_source in data.get("hint_source", []):
            if hint_source in seen:
                continue
            seen.add(hint_source)
            parts.append("--hint-source={}".format(hint_source))
        parts.append("--hint-strategy={}".format(data["hint_strategy"]))
        for study in data.get("exclude_study", []):
            parts.append("--exclude-study={}".format(study.short_name))
        if data.get("dry_run"):
            parts.append("--dry-run")
        return " ".join(parts)
