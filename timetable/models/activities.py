"""
Activity-related models: Activity, ActivitySet, ActivityRealization, and NRequirementsPerStudent.
"""
import datetime

from django.db import models
from django.db.models import Count

from .constants import ACTIVITYTYPES


class ActivitySet(models.Model):
    def __str__(self):
        return self.name

    created = models.DateTimeField(default=datetime.datetime.now)
    slug = models.SlugField()
    name = models.CharField(max_length=64)
    locked = models.BooleanField(default=False)

    @property
    def teachers(self):
        from .core import Teacher
        return Teacher.objects.filter(activities__activityset__exact=self).distinct()

    @property
    def groups(self):
        from .groups import Group
        return Group.objects.filter(activities__activityset__exact=self).distinct()


class Activity(models.Model):
    def __str__(self):
        groups = self.groups.all()
        return "{0} {1}".format(self.name, "-".join([str(group) for group in groups]))

    teachers = models.ManyToManyField("Teacher", blank=True, related_name="activities")
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=32)
    activityset = models.ForeignKey(
        "ActivitySet", related_name="activities", on_delete=models.CASCADE
    )
    type = models.CharField(max_length=4, choices=ACTIVITYTYPES)
    locations = models.ManyToManyField("Location", blank=False)
    duration = models.IntegerField()
    requirements = models.ManyToManyField("Resource", blank=True)
    requirements_per_student = models.ManyToManyField(
        "Resource",
        blank=True,
        through="NRequirementsPerStudent",
        related_name="per_student_activities",
    )
    groups = models.ManyToManyField("Group", blank=True, related_name="activities")
    mustNotOverlap = models.ManyToManyField("self", symmetrical=True, blank=True)
    before = models.ManyToManyField(
        "self", symmetrical=False, related_name="after", blank=True
    )
    required_rooms = models.ManyToManyField("Classroom")

    def groups_on_realizations_without_teachers(self, groupset):
        realizations = self.realizations_without_teachers(groupset)
        return self.groups.filter(
            realizations__in=realizations, groupset=groupset
        ).distinct()

    def realizations_without_teachers(self, groupset):
        annotated_realizations = self.realizations.all().annotate(
            teacher_count=Count("teachers")
        )
        return annotated_realizations.filter(teacher_count=0)

    def groups_without_realization(self, groupset):
        """
        Return the queryset of all groups on acvitiy that are not part of any
        realiazation related to this activity.
        All groups are limited to a given groupset.
        """
        from .groups import Group
        groups = Group.objects.filter(activities__exact=self, groupset=groupset)
        return groups.exclude(
            realizations__in=self.realizations.all(), groupset=groupset
        )

    def preferred_rooms(self, timetable=None):
        """Return the list of preferred rooms.

        When they are explicitely set return then otherwise filter by requirements.
        """
        if self.required_rooms.exists():
            return self.required_rooms.all()

        from .classrooms import Classroom
        location_ids = self.locations.all().values_list("id", flat=True)
        if timetable is None:
            cl = Classroom.objects.filter(location__id__in=location_ids).distinct()
        else:
            cl = Classroom.objects.filter(
                classroomset__timetables=timetable, location__id__in=location_ids
            ).distinct()
        for r in self.requirements.all():
            cl = cl.filter(resources__exact=r)
        return cl

    @property
    def size(self):
        size = 0
        for group in self.groups.all():
            size += group.size
        return size

    class Meta:
        ordering = ["name"]


class NRequirementsPerStudent(models.Model):
    def __str__(self):
        return "{0}/{2}({1})".format(self.resource, self.activity, self.n)

    class Meta:
        unique_together = (("resource", "activity"),)

    resource = models.ForeignKey("Resource", on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    n = models.FloatField()


class ActivityRealization(models.Model):
    def __str__(self):
        return (
            self.activity.name
            + " "
            + " ".join([str(i) for i in self.teachers.all()])
            + " "
            + " ".join([str(i) for i in self.groups.all()])
        )

    activity = models.ForeignKey(
        "Activity", related_name="realizations", on_delete=models.CASCADE
    )
    teachers = models.ManyToManyField(
        "Teacher", related_name="activity_realizations", blank=True
    )
    groups = models.ManyToManyField("Group", blank=True, related_name="realizations")
    intended_size = models.IntegerField(default=0, blank=True)

    @property
    def locations(self):
        return self.activity.locations

    @property
    def duration(self):
        return self.activity.duration

    @property
    def size(self):
        """
        The number of students on this realization.
        """
        size = 0
        for group in self.groups.all():
            if group.size is not None:
                size += group.size
        return max(size, self.intended_size)

    @property
    def group_size(self):
        """
        The number of students on this realization.
        """
        size = 0
        for group in self.groups.all():
            if group.size is not None:
                size += group.size
        return size

    def preferred_rooms(self, timetable=None, n_students=None):
        if n_students is None:
            n_students = self.size
        classrooms = self.activity.preferred_rooms(timetable)
        for nr in NRequirementsPerStudent.objects.filter(activity=self.activity):
            classrooms = classrooms.filter(
                n_resources__resource=nr.resource, n_resources__n__gte=nr.n * n_students
            )
        return classrooms

    def id_string(self):
        self.activity.name + "-" + self.id