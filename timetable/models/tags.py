"""
Tag model.
"""
from django.db import models


class Tag(models.Model):
    def __str__(self):
        return self.name

    name = models.CharField(max_length=32)
    description = models.TextField()
    teachers = models.ManyToManyField("Teacher", blank=True, related_name="tags")
    activities = models.ManyToManyField("Activity", blank=True, related_name="tags")
    activity_realizations = models.ManyToManyField(
        "ActivityRealization", blank=True, related_name="tags"
    )
    groups = models.ManyToManyField("Group", blank=True, related_name="tags")

    @property
    def value_preferences(self):
        from .preferences import TagValuePreference
        return TagValuePreference.objects.filter(tag=self)