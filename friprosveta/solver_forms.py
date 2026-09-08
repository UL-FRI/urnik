"""
Typed forms for the superuser-only Solver Setup UI.

These forms expose only the SolverConstraint behavior the OR-Tools solver
actually consumes (see friprosveta/services/ortools_solver.py). The ``hard``,
``weight`` and ``classrooms`` fields are intentionally absent: the solver
treats every constraint as hard and ignores room scoping, and the UI must not
imply otherwise.

All selectable querysets are scoped to a timetable so an operator cannot
attach a constraint to activities, realizations, teachers or groups belonging
to a different timetable.
"""
from django import forms

from friprosveta.models import Activity as FriActivity, ManualActivity, SolverWeightSettings
from timetable.models import (
    Activity,
    ActivityRealization,
    Classroom,
    Group,
    GroupTimePreference,
    Resource,
    SolverConstraint,
    StudyModule,
    Teacher,
    Timetable,
    WEEKDAYS,
    WORKHOURS,
)


class SchedulingScopeActivityForm(forms.ModelForm):
    exclude_from_solver = forms.BooleanField(
        required=False,
        label="Exclude from solver",
    )

    class Meta:
        model = FriActivity
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["exclude_from_solver"] = not self.instance.ready_to_schedule

    def save(self, commit=True):
        self.instance.ready_to_schedule = not self.cleaned_data["exclude_from_solver"]
        if commit:
            self.instance.save(update_fields=["ready_to_schedule"])
        return self.instance


class ManualActivityForm(forms.ModelForm):
    class Meta:
        model = ManualActivity
        fields = (
            "subject",
            "lecture_type",
            "name",
            "duration",
            "enabled",
            "teachers",
            "groups",
            "locations",
            "requirements",
            "required_rooms",
            "fixed_day",
            "fixed_start",
            "fixed_room",
        )
        widgets = {
            "teachers": forms.SelectMultiple(attrs={"size": "8"}),
            "groups": forms.SelectMultiple(attrs={"size": "8"}),
            "locations": forms.SelectMultiple(attrs={"size": "5"}),
            "requirements": forms.SelectMultiple(attrs={"size": "8"}),
            "required_rooms": forms.SelectMultiple(attrs={"size": "10"}),
        }
        help_texts = {
            "name": "Leave blank to use the subject name.",
            "required_rooms": "When set, these rooms take precedence over resource matching.",
            "fixed_day": "Set day, start, and room together to create a fixed allocation.",
        }

    def __init__(self, *args, timetable, **kwargs):
        self.timetable = timetable
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = _group_queryset(timetable)
        self.fields["required_rooms"].queryset = _classroom_queryset(timetable)
        self.fields["fixed_room"].queryset = _classroom_queryset(timetable)
        self.fields["requirements"].queryset = Resource.objects.filter(archived=False)

    def clean(self):
        cleaned = super().clean()
        fixed_values = [
            cleaned.get("fixed_day"),
            cleaned.get("fixed_start"),
            cleaned.get("fixed_room"),
        ]
        if any(fixed_values) and not all(fixed_values):
            raise forms.ValidationError(
                "A fixed allocation requires a weekday, start time, and room."
            )
        room = cleaned.get("fixed_room")
        if room is None:
            return cleaned
        required_rooms = cleaned.get("required_rooms")
        if required_rooms and room not in required_rooms:
            self.add_error("fixed_room", "The fixed room must be one of the allowed rooms.")
        requirements = cleaned.get("requirements")
        if requirements and room.resources.filter(pk__in=requirements).count() != len(requirements):
            self.add_error("fixed_room", "The fixed room does not provide every required resource.")
        group_size = sum(group.size or 0 for group in cleaned.get("groups", []))
        if group_size and room.capacity < group_size:
            self.add_error(
                "fixed_room",
                "The fixed room capacity is smaller than the selected groups.",
            )
        return cleaned


class SolverWeightSettingsForm(forms.ModelForm):
    class Meta:
        model = SolverWeightSettings
        fields = (
            "scheduling_window_weight",
            "lecture_grid_alignment_weight",
            "consecutive_teacher_room_weight",
            "room_adjacency_weight",
            "lecture_back_to_back_penalty",
        )
        help_texts = {
            "scheduling_window_weight": "Base points for each applicable soft scheduling-window or activity-type restriction hour.",
            "lecture_grid_alignment_weight": "Points for aligned P (3h), LV (2h), and AV (2h) starts.",
            "consecutive_teacher_room_weight": "Points when adjacent realizations of one activity keep a teacher in the same room.",
            "room_adjacency_weight": "Points for adjacent occupied slots in a physical room.",
            "lecture_back_to_back_penalty": "Points deducted when distinct P lectures for one top-level group are immediately adjacent.",
        }
        labels = {
            "scheduling_window_weight": "Soft time restriction base weight",
            "lecture_grid_alignment_weight": "Activity grid alignment weight",
            "consecutive_teacher_room_weight": "Adjacent teacher same-room weight",
            "room_adjacency_weight": "Room compactness weight",
            "lecture_back_to_back_penalty": "Back-to-back lecture penalty",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.min_value = 0
            field.help_text += " Set to 0 to disable this soft rule."


class CopyGroupTimePreferencesForm(forms.Form):
    source_timetable = forms.ModelChoiceField(
        queryset=Timetable.objects.none(),
        label="Source timetable",
    )

    def __init__(self, *args, timetable, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_timetable"].queryset = (
            Timetable.objects.exclude(pk=timetable.pk)
            .filter(groupset__isnull=False, preferenceset__isnull=False)
            .order_by("-start", "-id")
        )

    def clean_source_timetable(self):
        source = self.cleaned_data["source_timetable"]
        if not GroupTimePreference.objects.filter(preferenceset=source.preferenceset).exists():
            raise forms.ValidationError("The selected timetable has no group time preferences.")
        return source

RELATION_TYPES = (
    ("NOOVERLAP", "Realizations must not overlap"),
    ("GROUPED", "Realizations must start together"),
    ("CONSECUTIVE", "Realizations must be consecutive"),
    ("SAMEDAY", "Realizations must be on the same day"),
    ("SAMESTARTINGTIME", "Realizations must start at the same time"),
    ("SAMEROOM", "Realizations must use the same room"),
    ("MAXROOMSREALIZATIONS", "Maximum different rooms across realizations"),
)
ENDS_DAY_TYPES = (("ENDSSTUDENTSDAY", "Realization ends the students' day"),)
WORKLOAD_TYPES = (
    ("MAXDAYSWEEK", "Maximum active days per week"),
    ("MINDAYSWEEK", "Minimum active days per week"),
    ("MAXHOURSDAY", "Maximum hours per day"),
    ("MAXHOURSCONT", "Maximum continuous hours"),
    ("MAXSPANDAY", "Maximum daily span"),
    ("MINCHANGEGAP", "Minimum gap between building changes"),
)
LECTURE_GROUP_TYPES = (
    ("MAXLECTUREHOURSDAY", "Maximum lecture hours per day for a top-level group"),
)
ROOM_TYPES = (("FIXEDROOM", "Fixed room for activities or realizations"),)
PLACEMENT_TYPES = (("FIXEDPLACEMENT", "Fixed weekday, time, and room"),)
TIME_TYPES = (("FIXEDTIME", "Fixed weekday and time"),)

CATEGORY_CHOICES = (
    ("relation", "Relation between activities / realizations"),
    ("ends_day", "Ends students' day"),
    ("workload", "Workload / movement limits"),
    ("lecture_group", "Lecture hours per top-level group"),
    ("room", "Fixed room assignment"),
    ("placement", "Exact time and room assignment"),
    ("time", "Exact time assignment"),
)

CATEGORY_TYPE_MAP = {
    "relation": {value for value, _ in RELATION_TYPES},
    "ends_day": {value for value, _ in ENDS_DAY_TYPES},
    "workload": {value for value, _ in WORKLOAD_TYPES},
    "lecture_group": {value for value, _ in LECTURE_GROUP_TYPES},
    "room": {value for value, _ in ROOM_TYPES},
    "placement": {value for value, _ in PLACEMENT_TYPES},
    "time": {value for value, _ in TIME_TYPES},
}


def _activity_queryset(timetable):
    return Activity.objects.filter(activityset=timetable.activityset).order_by("name")


def _realization_queryset(timetable):
    return ActivityRealization.objects.filter(
        activity__activityset=timetable.activityset
    ).order_by("activity__name")


def _teacher_queryset(timetable):
    return (
        Teacher.objects.filter(
            activity_realizations__activity__activityset=timetable.activityset
        )
        .distinct()
        .order_by("user__last_name", "user__first_name")
    )


def _group_queryset(timetable):
    return (
        Group.objects.filter(groupset=timetable.groupset)
        .exclude(short_name="VSI_PADALCI")
        .exclude(short_name__endswith="_PAD")
        .distinct()
        .order_by("short_name")
    )


def _classroom_queryset(timetable):
    if timetable.classroomset_id is None:
        return Classroom.objects.none()
    return timetable.classrooms.order_by("short_name")


def _effective_realization_ids(timetable, activity_ids, realization_ids):
    """
    Mirror ``_solver_constraint_realizations``: the effective set is the union
    of directly-selected realizations and all realizations of selected
    activities, restricted to the timetable's activityset.
    """
    direct = set(realization_ids)
    from_activity = set(
        ActivityRealization.objects.filter(
            activity__activityset=timetable.activityset,
            activity_id__in=activity_ids,
        ).values_list("id", flat=True)
    )
    return direct | from_activity


class SolverConstraintCategoryForm(forms.Form):
    category = forms.ChoiceField(
        choices=CATEGORY_CHOICES, widget=forms.RadioSelect, label="Constraint category"
    )


class ActivityBeforeRelationForm(forms.Form):
    before_activity = forms.ModelChoiceField(
        queryset=Activity.objects.none(),
        label="Earlier activity",
        help_text="Every realization of this activity must finish first.",
    )
    after_activities = forms.ModelMultipleChoiceField(
        queryset=Activity.objects.none(),
        label="Later activities",
        widget=forms.SelectMultiple(attrs={"size": "12"}),
        help_text="Every realization of these activities must start after the earlier activity finishes.",
    )

    def __init__(self, *args, timetable, **kwargs):
        super().__init__(*args, **kwargs)
        activities = _activity_queryset(timetable)
        self.fields["before_activity"].queryset = activities
        self.fields["after_activities"].queryset = activities

    def clean(self):
        cleaned = super().clean()
        before_activity = cleaned.get("before_activity")
        after_activities = cleaned.get("after_activities")
        if before_activity is not None and after_activities is not None:
            if before_activity in after_activities:
                self.add_error(
                    "after_activities",
                    "An activity cannot be ordered before itself.",
                )
        return cleaned

    def save(self):
        before_activity = self.cleaned_data["before_activity"]
        after_activities = self.cleaned_data["after_activities"]
        before_activity.before.add(*after_activities)
        return before_activity, list(after_activities)


class StudyModuleForm(forms.ModelForm):
    class Meta:
        model = StudyModule
        fields = ("name", "active", "activities", "non_overlapping_with")

    def __init__(self, *args, timetable, **kwargs):
        self.timetable = timetable
        super().__init__(*args, **kwargs)
        self.fields["activities"].queryset = _activity_queryset(timetable)
        self.fields["activities"].widget.attrs["size"] = "10"
        modules = StudyModule.objects.filter(timetable=timetable)
        if self.instance.pk:
            modules = modules.exclude(pk=self.instance.pk)
        self.fields["non_overlapping_with"].queryset = modules
        self.fields["non_overlapping_with"].widget.attrs["size"] = "8"
        self.fields["activities"].help_text = (
            "Every selected activity must not overlap with the others in this module."
        )
        self.fields["non_overlapping_with"].help_text = (
            "Selected modules must not overlap with this module."
        )

    def clean_activities(self):
        activities = self.cleaned_data["activities"]
        if activities.count() < 2:
            raise forms.ValidationError("Select at least two activities.")
        return activities

    def save(self, commit=True):
        module = super().save(commit=False)
        module.timetable = self.timetable
        if commit:
            module.save()
            self.save_m2m()
        return module


class SolverConstraintForm(forms.ModelForm):
    """
    Typed create/edit form for a SolverConstraint.

    Per-category field visibility matches solver consumption:
      relation / ends_day: activities + realizations only (teachers/groups
        are disabled and cleared on save).
      workload: teachers + groups only (activities/realizations are disabled
        and cleared on save).
      relation value: only MAXROOMSREALIZATIONS uses it; disabled otherwise.
    """

    class Meta:
        model = SolverConstraint
        fields = ("name", "constraint_type", "active", "value",
                  "activities", "realizations", "teachers", "groups")

    def __init__(self, *args, timetable, category, **kwargs):
        if category not in CATEGORY_TYPE_MAP:
            raise ValueError("Unknown solver constraint category: {!r}".format(category))
        self.timetable = timetable
        self.category = category
        super().__init__(*args, **kwargs)

        type_choices = {
            "relation": RELATION_TYPES,
            "ends_day": ENDS_DAY_TYPES,
            "workload": WORKLOAD_TYPES,
            "lecture_group": LECTURE_GROUP_TYPES,
            "room": ROOM_TYPES,
            "placement": PLACEMENT_TYPES,
            "time": TIME_TYPES,
        }[category]
        self.fields["constraint_type"] = forms.ChoiceField(
            choices=type_choices,
            initial=self.initial.get("constraint_type"),
            widget=forms.Select,
        )

        self.fields["activities"] = forms.ModelMultipleChoiceField(
            queryset=_activity_queryset(timetable),
            required=False,
            widget=forms.SelectMultiple(attrs={"size": "8"}),
            help_text="Activities from this timetable. Select with Ctrl/Cmd.",
        )
        self.fields["realizations"] = forms.ModelMultipleChoiceField(
            queryset=_realization_queryset(timetable),
            required=False,
            widget=forms.SelectMultiple(attrs={"size": "8"}),
            help_text="Activity realizations from this timetable.",
        )
        self.fields["teachers"] = forms.ModelMultipleChoiceField(
            queryset=_teacher_queryset(timetable),
            required=False,
            widget=forms.SelectMultiple(attrs={"size": "6"}),
            help_text="Teachers assigned to realizations in this timetable.",
        )
        self.fields["groups"] = forms.ModelMultipleChoiceField(
            queryset=_group_queryset(timetable),
            required=False,
            widget=forms.SelectMultiple(attrs={"size": "6"}),
            help_text="Groups belonging to this timetable's groupset.",
        )

        if category == "workload":
            self.fields["value"] = forms.IntegerField(
                min_value=1, required=True,
                help_text="Positive integer limit (e.g. max days, max hours, min gap).",
            )
            self.fields["activities"].disabled = True
            self.fields["realizations"].disabled = True
        elif category == "lecture_group":
            self.fields["value"] = forms.IntegerField(
                min_value=1,
                required=True,
                help_text="Maximum P (lecture) hours for each selected top-level group per day.",
            )
            self.fields["groups"].queryset = _group_queryset(timetable).filter(parent__isnull=True)
            self.fields["groups"].help_text = "Top-level groups only; their descendant groups are included automatically."
            self.fields["teachers"].disabled = True
            self.fields["activities"].disabled = True
            self.fields["realizations"].disabled = True
        elif category in ("room", "placement", "time"):
            self.fields["value"] = forms.IntegerField(required=False, disabled=True)
            self.fields["teachers"].disabled = True
            self.fields["groups"].disabled = True
            if category in ("room", "placement"):
                self.fields["classrooms"] = forms.ModelMultipleChoiceField(
                    queryset=_classroom_queryset(timetable),
                    required=False,
                    widget=forms.SelectMultiple(attrs={"size": "6"}),
                    help_text="Select exactly one room for this rule.",
                )
            if category in ("placement", "time"):
                self.fields["day"] = forms.ChoiceField(
                    choices=WEEKDAYS, initial=self.instance.day
                )
                self.fields["start"] = forms.ChoiceField(
                    choices=WORKHOURS, initial=self.instance.start
                )
        elif category == "relation":
            self.fields["value"] = forms.IntegerField(
                min_value=1, required=False,
                help_text="Used only by MAXROOMSREALIZATIONS; other relation types discard it.",
            )
            self.fields["teachers"].disabled = True
            self.fields["groups"].disabled = True
        else:
            self.fields["value"] = forms.IntegerField(
                required=False, disabled=True,
                help_text="Not used for this constraint type.",
            )
            self.fields["teachers"].disabled = True
            self.fields["groups"].disabled = True

    def clean(self):
        cleaned = super().clean()
        constraint_type = cleaned.get("constraint_type")
        activities = list(cleaned.get("activities") or [])
        realizations = list(cleaned.get("realizations") or [])
        teachers = list(cleaned.get("teachers") or [])
        groups = list(cleaned.get("groups") or [])
        classrooms = list(cleaned.get("classrooms") or [])
        value = cleaned.get("value")

        activity_ids = {a.id for a in activities}
        realization_ids = {r.id for r in realizations}
        effective_ids = _effective_realization_ids(
            self.timetable, activity_ids, realization_ids
        )

        if self.category in ("workload", "lecture_group"):
            if self.category == "workload" and not teachers and not groups:
                self.add_error(
                    None,
                    "Workload / movement constraints require at least one "
                    "teacher or group from this timetable.",
                )
            if self.category == "lecture_group" and not groups:
                self.add_error(None, "Select at least one top-level group.")
            if value is None or value < 1:
                self.add_error("value", "A positive integer value is required.")
        elif self.category == "room":
            if len(effective_ids) < 1:
                self.add_error(None, "Select at least one activity or realization.")
            if len(classrooms) != 1:
                self.add_error("classrooms", "Select exactly one room.")
        elif self.category == "placement":
            if len(effective_ids) != 1:
                self.add_error(
                    None, "Select exactly one realization, or one activity with one realization."
                )
            if len(classrooms) != 1:
                self.add_error("classrooms", "Select exactly one room.")
        elif self.category == "time":
            if len(effective_ids) != 1:
                self.add_error(
                    None, "Select exactly one realization, or one activity with one realization."
                )
        elif self.category == "ends_day":
            if len(effective_ids) < 1:
                self.add_error(
                    None,
                    "ENDSSTUDENTSDAY requires at least one activity or "
                    "realization from this timetable.",
                )
        else:
            if len(effective_ids) < 2:
                self.add_error(
                    None,
                    "Relation constraints must expand to at least two distinct "
                    "realizations in this timetable. Selecting one activity with "
                    "a single realization, or an activity plus its own realization, "
                    "is not enough.",
                )
            if constraint_type == "MAXROOMSREALIZATIONS":
                if value is None or value < 1:
                    self.add_error("value", "MAXROOMSREALIZATIONS requires a positive value.")
        return cleaned

    def _ignored_m2m_fields(self):
        if self.category in ("relation", "ends_day"):
            return ("teachers", "groups")
        if self.category == "lecture_group":
            return ("activities", "realizations", "teachers")
        if self.category in ("room", "placement", "time"):
            return ("teachers", "groups")
        return ("activities", "realizations")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.timetable = self.timetable
        instance.hard = True
        instance.weight = 1.0
        if self.category in ("placement", "time"):
            instance.day = self.cleaned_data["day"]
            instance.start = self.cleaned_data["start"]
        else:
            instance.day = None
            instance.start = None
        if self.category == "ends_day" or (
            self.category == "relation"
            and instance.constraint_type != "MAXROOMSREALIZATIONS"
        ):
            instance.value = None
        if commit:
            instance.save()
            self.save_m2m()
            if self.category in ("room", "placement"):
                instance.classrooms.set(self.cleaned_data["classrooms"])
            elif self.category == "time":
                instance.classrooms.set([])
            for field_name in self._ignored_m2m_fields():
                getattr(instance, field_name).set([])
        return instance
