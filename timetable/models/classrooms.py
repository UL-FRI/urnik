"""
Classroom-related models: Classroom, ClassroomSet, and ClassroomNResources.
"""
from django.db import models

from .constants import ACTIVITYTYPES, WORKHOURS


class ClassroomSet(models.Model):
    def __str__(self):
        return self.name

    created = models.DateField()
    slug = models.SlugField()
    name = models.CharField(max_length=64)
    locked = models.BooleanField(default=False)
    classrooms = models.ManyToManyField(
        "Classroom", blank=True, related_name="classroomset"
    )


class Classroom(models.Model):
    def __str__(self):
        return "{0} ({1})".format(self.name, self.short_name)

    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=32)
    resources = models.ManyToManyField(
        "Resource", through="ClassroomNResources", blank=True, related_name="classrooms"
    )
    capacity = models.IntegerField()
    minimum_realization_size = models.PositiveIntegerField(
        default=0,
        help_text="Minimum realization size required to use this room. Set 0 for no minimum.",
    )
    location = models.ForeignKey("Location", on_delete=models.CASCADE)
    allow_overlaps = models.BooleanField(
        default=False,
        help_text="Allow simultaneous allocations, for example for virtual rooms.",
    )
    is_virtual = models.BooleanField(
        default=False,
        help_text="Marks a room for remote-delivery cycles.",
    )


class ClassroomActivityType(models.Model):
    """An optional activity-type allowlist for a classroom."""

    classroom = models.ForeignKey(
        Classroom, related_name="supported_activity_types", on_delete=models.CASCADE
    )
    activity_type = models.CharField(max_length=4, choices=ACTIVITYTYPES)

    class Meta:
        unique_together = (("classroom", "activity_type"),)

    def __str__(self):
        return "{0}: {1}".format(self.classroom, self.activity_type)


class ClassroomActivityStartTime(models.Model):
    """Allowed starts for an activity type in a classroom, when configured."""

    classroom = models.ForeignKey(
        Classroom, related_name="activity_start_times", on_delete=models.CASCADE
    )
    activity_type = models.CharField(max_length=4, choices=ACTIVITYTYPES)
    start = models.CharField(max_length=5, choices=WORKHOURS)

    class Meta:
        unique_together = (("classroom", "activity_type", "start"),)

    def __str__(self):
        return "{0}: {1} at {2}".format(self.classroom, self.activity_type, self.start)


class ClassroomNResources(models.Model):
    def __str__(self):
        return "{0}/{1}({2})".format(self.resource, self.classroom, self.n)

    class Meta:
        unique_together = (("resource", "classroom"),)

    resource = models.ForeignKey("Resource", on_delete=models.CASCADE)
    classroom = models.ForeignKey(
        Classroom, related_name="n_resources", on_delete=models.CASCADE
    )
    n = models.IntegerField()
