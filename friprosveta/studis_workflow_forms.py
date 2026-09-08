"""
Staff-only forms for Studis workflow commands.

Each form validates operator input for a specific management command and can
build a copy-pasteable command preview from sanitized values.
"""

from datetime import date

from django import forms

from timetable.models import TimetableSet


STUDIS_SEMESTER_CHOICES = (("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"))


def _default_year():
    return str(date.today().year)


def _default_semester():
    return "2"


class StudisSemesterForm(forms.Form):
    year = forms.IntegerField(
        min_value=2000,
        initial=int(_default_year()),
        label="Studis year",
        help_text="Enter the first part of the study year, e.g. 2026 for 2026/2027.",
    )
    semester_id = forms.ChoiceField(
        choices=STUDIS_SEMESTER_CHOICES,
        initial=_default_semester(),
        label="Semester",
        help_text="Semester id in Studis: 1=zimski, 2=poletni, 3=celoletni, 4=blocni",
    )


class SyncSubjectsForm(forms.Form):
    """No user parameters needed for sync_subjects."""


class ImportNajaveForm(StudisSemesterForm):
    subject_code = forms.CharField(
        required=False,
        label="Subject code",
        help_text="Optional subject code filter when you only want one subject.",
    )

    def command(self, timetable_slug):
        data = self.cleaned_data
        command = " ".join(
            [
                "python3",
                "manage.py",
                "import_studis_najave",
                timetable_slug,
                str(data["year"]),
                data["semester_id"],
            ]
        )
        if data["subject_code"]:
            command += " --subject={}".format(data["subject_code"])
        return command


class CreateActivitiesForm(StudisSemesterForm):
    subject_code = forms.CharField(
        required=False,
        label="Subject code",
        help_text="Optional subject code filter when you want to update one subject.",
    )

    def command(self, timetable_slug):
        data = self.cleaned_data
        command = " ".join(
            [
                "python3",
                "manage.py",
                "create_activities",
                timetable_slug,
                str(data["year"]),
                data["semester_id"],
            ]
        )
        if data["subject_code"]:
            command += " --subject_code={}".format(data["subject_code"])
        return command


class ImportStudentsForm(forms.Form):
    year = forms.IntegerField(
        min_value=2000,
        initial=int(_default_year()),
        label="Studis year",
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=date.today,
        label="Enrollment date",
    )
    unconfirmed = forms.BooleanField(
        required=False,
        label="Include unconfirmed enrollments",
        initial=False,
    )
    unfinished = forms.BooleanField(
        required=False,
        label="Include unfinished enrollments",
        initial=False,
    )
    preenrolment = forms.BooleanField(
        required=False,
        label="Include preenrolments",
        initial=False,
    )

    def command(self, timetable_slug):
        data = self.cleaned_data
        command = " ".join(
            [
                "python3",
                "manage.py",
                "import_studis_students",
                timetable_slug,
                str(data["year"]),
                data["date"].isoformat(),
            ]
        )
        if data["unconfirmed"]:
            command += " --unconfirmed"
        if data["unfinished"]:
            command += " --unfinished"
        if data["preenrolment"]:
            command += " --preenrolment"
        return command


class CreateRealizationsForm(forms.Form):
    timetable_set = forms.ModelChoiceField(
        queryset=TimetableSet.objects.all().order_by("slug"),
        to_field_name="slug",
        label="Timetable set",
        help_text="Timetable set used when computing realizations.",
    )

    def __init__(self, *args, timetable=None, **kwargs):
        super().__init__(*args, **kwargs)
        if timetable is not None:
            self.fields["timetable_set"].queryset = timetable.timetable_sets.all().order_by(
                "slug"
            )

    def command(self, timetable_slug):
        return " ".join(
            [
                "python3",
                "manage.py",
                "create_realizations",
                timetable_slug,
                str(self.cleaned_data["timetable_set"].slug),
            ]
        )


class FindMissingTeachersForm(forms.Form):
    timetable_set = forms.ModelChoiceField(
        queryset=TimetableSet.objects.all().order_by("slug"),
        to_field_name="slug",
        label="Timetable set",
        help_text="Timetable set whose imported najave should be checked.",
    )

    def __init__(self, *args, timetable=None, **kwargs):
        super().__init__(*args, **kwargs)
        if timetable is not None:
            self.fields["timetable_set"].queryset = timetable.timetable_sets.all().order_by(
                "slug"
            )

    def command(self, timetable_slug):
        return "python3 manage.py find_missing_teachers {} {}".format(
            timetable_slug,
            self.cleaned_data["timetable_set"].slug,
        )


class RemovePadGroupsForm(forms.Form):
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label="Preview only",
        help_text="Report PAD groups without removing them.",
    )

    def command(self, timetable_slug):
        command = "python3 manage.py remove_pad_groups {}".format(timetable_slug)
        if self.cleaned_data["dry_run"]:
            command += " --dry-run"
        return command


class CreateTopLevelGroupsForm(StudisSemesterForm):
    def command(self, timetable_slug):
        data = self.cleaned_data
        return "{} {} {} {} {} {}".format(
            "python3",
            "manage.py",
            "create_top_level_groups",
            timetable_slug,
            str(data["year"]),
            data["semester_id"],
        )
