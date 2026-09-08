"""
First-class constraints for the OR-Tools timetable solver.

These models are intentionally generic while the solver evolves. They allow new
solver behavior to be configured directly instead of encoding everything through
FET-oriented tags.
"""
from django.db import models

from .constants import WEEKDAYS, WORKHOURS


class SolverConstraint(models.Model):
    RELATION_TYPES = (
        ("NOOVERLAP", "Realizations must not overlap"),
        ("GROUPED", "Realizations must start together"),
        ("CONSECUTIVE", "Realizations must be consecutive"),
        ("SAMEDAY", "Realizations must be on the same day"),
        ("SAMESTARTINGTIME", "Realizations must start at the same time"),
        ("SAMEROOM", "Realizations must use the same room"),
        ("ENDSSTUDENTSDAY", "Realization ends the students' day"),
        ("MAXROOMSREALIZATIONS", "Maximum different rooms across realizations"),
        ("MAXDAYSWEEK", "Maximum active days per week"),
        ("MINDAYSWEEK", "Minimum active days per week"),
        ("MAXHOURSDAY", "Maximum hours per day"),
        ("MAXHOURSCONT", "Maximum continuous hours"),
        ("MAXSPANDAY", "Maximum daily span"),
        ("MINCHANGEGAP", "Minimum gap between building changes"),
        ("MAXLECTUREHOURSDAY", "Maximum lecture hours per day for a top-level group"),
        ("FIXEDROOM", "Fixed room for activities or realizations"),
        ("FIXEDPLACEMENT", "Fixed weekday, time, and room for a realization"),
        ("FIXEDTIME", "Fixed weekday and time for a realization"),
    )

    name = models.CharField(max_length=128)
    timetable = models.ForeignKey(
        "Timetable", related_name="solver_constraints", on_delete=models.CASCADE
    )
    constraint_type = models.CharField(max_length=32, choices=RELATION_TYPES)
    active = models.BooleanField(default=True)
    hard = models.BooleanField(default=True)
    weight = models.FloatField(default=1.0)
    value = models.IntegerField(null=True, blank=True)
    day = models.CharField(max_length=3, choices=WEEKDAYS, null=True, blank=True)
    start = models.CharField(max_length=5, choices=WORKHOURS, null=True, blank=True)
    activities = models.ManyToManyField("Activity", blank=True)
    realizations = models.ManyToManyField("ActivityRealization", blank=True)
    teachers = models.ManyToManyField("Teacher", blank=True)
    groups = models.ManyToManyField("Group", blank=True)
    classrooms = models.ManyToManyField("Classroom", blank=True)

    def __str__(self):
        return "{}: {}".format(self.name, self.constraint_type)


class StudyModule(models.Model):
    """A selectable study module and the modules that can be taken with it."""

    name = models.CharField(max_length=128)
    timetable = models.ForeignKey(
        "Timetable", related_name="study_modules", on_delete=models.CASCADE
    )
    active = models.BooleanField(default=True)
    activities = models.ManyToManyField("Activity", blank=True)
    non_overlapping_with = models.ManyToManyField("self", symmetrical=True, blank=True)

    class Meta:
        ordering = ("name",)
        unique_together = (("timetable", "name"),)

    def __str__(self):
        return self.name
