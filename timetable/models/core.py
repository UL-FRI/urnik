"""
Core models: Resource, ResourceGroup, Teacher, Location, and LocationDistance.
"""
from django.contrib.auth.models import User
from django.db import models


class ResourceGroup(models.Model):
    """A group of related resources."""
    def __str__(self):
        return self.name

    name = models.CharField(max_length=255, help_text="Name of the resource group (e.g., 'Projection Equipment', 'Computer Labs')")
    required = models.BooleanField(
        default=False,
        help_text="If checked, users must select at least one resource from this group"
    )
    exactly_one = models.BooleanField(
        default=False,
        help_text="If checked, users must select exactly one resource from this group (not more, not less)"
    )
    order = models.IntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)"
    )

    class Meta:
        ordering = ['order', 'name']


class Resource(models.Model):
    """A resource that can be assigned to activities or classrooms."""
    def __str__(self):
        return self.name

    name = models.CharField(max_length=255)
    group = models.ForeignKey(
        ResourceGroup,
        related_name='resources',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The group this resource belongs to"
    )
    order = models.IntegerField(
        default=0,
        help_text="Display order within the group (lower numbers appear first)"
    )

    class Meta:
        ordering = ['group__order', 'group__name', 'order', 'name']

class Teacher(models.Model):
    def __str__(self):
        s = "Ambrož Zasekamožević"
        if self.user is not None:
            s = "{0}, {1}".format(self.user.last_name, self.user.first_name)
        if s == "":
            s = self.user
        return s

    user = models.OneToOneField(
        User, null=True, related_name="teacher", on_delete=models.CASCADE
    )
    # activities = models.ManyToManyField('Activity', blank=True, through='ActivityPercentage')
    code = models.CharField(max_length=32, default="", unique=True)

    @property
    def time_preferences(self):
        from .preferences import TeacherTimePreference
        return TeacherTimePreference.objects.filter(teacher=self)

    @property
    def value_preferences(self):
        from .preferences import TeacherValuePreference
        return TeacherValuePreference.objects.filter(teacher=self)

    @property
    def descriptive_preferences(self):
        from .preferences import TeacherDescriptivePreference
        return TeacherDescriptivePreference.objects.filter(teacher=self)

    def id_string(self):
        return "{0}({1})".format(self.__str__(), self.user)


class Location(models.Model):
    def __str__(self):
        return self.name

    name = models.CharField(max_length=100)
    distances = models.ManyToManyField(
        "self", through="LocationDistance", symmetrical=False
    )

    @property
    def short_location_name(self):
        if "Sežana" in self.name:
            return "Sežana"
        else:
            return "Ljubljana"


class LocationDistance(models.Model):
    distance = models.IntegerField()
    time = models.IntegerField()
    from_location = models.ForeignKey(
        "Location", related_name="from_location", on_delete=models.CASCADE
    )
    to_location = models.ForeignKey(
        "Location", related_name="to_location", on_delete=models.CASCADE
    )