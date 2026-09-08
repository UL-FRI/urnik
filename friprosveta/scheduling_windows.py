from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

import timetable.models as timetable_models
from timetable.models import ACTIVITYTYPES, AFTERHOURS, WEEKDAYS, WORKHOURS


SCHEDULING_WINDOW_END_CHOICES = WORKHOURS + (AFTERHOURS,)
SCHEDULING_WINDOW_WEIGHT_VALIDATORS = [MinValueValidator(0), MaxValueValidator(100)]


class ActivityTypeSchedulingWindow(models.Model):
    timetable = models.ForeignKey(
        timetable_models.Timetable,
        related_name="activity_type_scheduling_windows",
        on_delete=models.CASCADE,
    )
    activity_type = models.CharField(max_length=4, choices=ACTIVITYTYPES)
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    end = models.CharField(max_length=5, choices=SCHEDULING_WINDOW_END_CHOICES)
    active = models.BooleanField(default=True)
    weight = models.PositiveSmallIntegerField(
        default=50,
        validators=SCHEDULING_WINDOW_WEIGHT_VALIDATORS,
        help_text="100 makes this window hard; lower values make it a soft preference.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("timetable", "activity_type", "day"),
                name="activity_type_scheduling_window_unique_day",
            ),
            models.CheckConstraint(
                condition=models.Q(start__lt=models.F("end")),
                name="activity_type_scheduling_window_start_before_end",
            ),
        ]

    def clean(self):
        if self.start >= self.end:
            raise ValidationError({"end": "End must be after start."})


class ActivityTypeSchedulingRestriction(models.Model):
    """One FET-style unavailable time preference for an activity type."""

    timetable = models.ForeignKey(
        timetable_models.Timetable,
        related_name="activity_type_scheduling_restrictions",
        on_delete=models.CASCADE,
    )
    activity_type = models.CharField(max_length=4, choices=ACTIVITYTYPES)
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    weight = models.PositiveSmallIntegerField(
        validators=SCHEDULING_WINDOW_WEIGHT_VALIDATORS,
        help_text="0 is available, 1-99 is soft unavailability, and 100 is hard.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("timetable", "activity_type", "day", "start"),
                name="activity_type_scheduling_restriction_unique_slot",
            ),
        ]


class ActivityRealizationSchedulingWindow(models.Model):
    timetable = models.ForeignKey(
        timetable_models.Timetable,
        related_name="activity_realization_scheduling_windows",
        on_delete=models.CASCADE,
    )
    realization = models.ForeignKey(
        timetable_models.ActivityRealization,
        related_name="scheduling_window_overrides",
        on_delete=models.CASCADE,
    )
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(
        max_length=5,
        choices=WORKHOURS,
        null=True,
        blank=True,
    )
    end = models.CharField(
        max_length=5,
        choices=SCHEDULING_WINDOW_END_CHOICES,
        null=True,
        blank=True,
    )
    unrestricted = models.BooleanField(default=False)
    weight = models.PositiveSmallIntegerField(
        default=50,
        validators=SCHEDULING_WINDOW_WEIGHT_VALIDATORS,
        help_text="100 makes this window hard; lower values make it a soft preference.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("timetable", "realization", "day"),
                name="activity_realization_scheduling_window_unique_day",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        unrestricted=True,
                        start__isnull=True,
                        end__isnull=True,
                    )
                    | models.Q(
                        unrestricted=False,
                        start__isnull=False,
                        end__isnull=False,
                        start__lt=models.F("end"),
                    )
                ),
                name="activity_realization_scheduling_window_valid_bounds",
            ),
        ]

    def clean(self):
        errors = {}
        if self.unrestricted:
            if self.start is not None:
                errors["start"] = "Unrestricted overrides cannot define a start."
            if self.end is not None:
                errors["end"] = "Unrestricted overrides cannot define an end."
        else:
            if self.start is None:
                errors["start"] = "Bounded overrides require a start."
            if self.end is None:
                errors["end"] = "Bounded overrides require an end."
            if self.start is not None and self.end is not None and self.start >= self.end:
                errors["end"] = "End must be after start."
        if (
            self.timetable_id is not None
            and self.realization_id is not None
            and self.realization.activity.activityset_id != self.timetable.activityset_id
        ):
            errors["realization"] = (
                "Realization must belong to the timetable activity set."
            )
        if errors:
            raise ValidationError(errors)


class TeacherSchedulingWindow(models.Model):
    timetable = models.ForeignKey(
        timetable_models.Timetable,
        related_name="teacher_scheduling_windows",
        on_delete=models.CASCADE,
    )
    teacher = models.ForeignKey(
        timetable_models.Teacher,
        related_name="scheduling_window_overrides",
        on_delete=models.CASCADE,
    )
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS, null=True, blank=True)
    end = models.CharField(
        max_length=5, choices=SCHEDULING_WINDOW_END_CHOICES, null=True, blank=True
    )
    unrestricted = models.BooleanField(default=False)
    unavailable = models.BooleanField(default=False)
    weight = models.PositiveSmallIntegerField(
        default=50,
        validators=SCHEDULING_WINDOW_WEIGHT_VALIDATORS,
        help_text="100 makes this window hard; lower values make it a soft preference.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("timetable", "teacher", "day"),
                name="teacher_scheduling_window_unique_day",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        unrestricted=True,
                        unavailable=False,
                        start__isnull=True,
                        end__isnull=True,
                    )
                    | models.Q(
                        unavailable=True,
                        unrestricted=False,
                        start__isnull=True,
                        end__isnull=True,
                    )
                    | models.Q(
                        unrestricted=False,
                        unavailable=False,
                        start__isnull=False,
                        end__isnull=False,
                        start__lt=models.F("end"),
                    )
                ),
                name="teacher_scheduling_window_valid_bounds",
            ),
        ]

    def clean(self):
        errors = {}
        if self.unrestricted:
            if self.unavailable:
                errors["unavailable"] = "An unrestricted override cannot be unavailable."
            if self.start is not None:
                errors["start"] = "Unrestricted overrides cannot define a start."
            if self.end is not None:
                errors["end"] = "Unrestricted overrides cannot define an end."
        elif self.unavailable:
            if self.start is not None:
                errors["start"] = "Unavailable overrides cannot define a start."
            if self.end is not None:
                errors["end"] = "Unavailable overrides cannot define an end."
            if self.weight != 100:
                errors["weight"] = "Unavailable overrides must be hard."
        else:
            if self.start is None:
                errors["start"] = "Bounded overrides require a start."
            if self.end is None:
                errors["end"] = "Bounded overrides require an end."
            if self.start is not None and self.end is not None and self.start >= self.end:
                errors["end"] = "End must be after start."
        if (
            self.timetable_id is not None
            and self.teacher_id is not None
            and self.timetable.activityset_id is not None
            and not self.timetable.teachers.filter(id=self.teacher_id).exists()
        ):
            errors["teacher"] = "Teacher must belong to the timetable activity set."
        if errors:
            raise ValidationError(errors)
