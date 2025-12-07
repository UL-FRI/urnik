"""
Classroom-related models: Classroom, ClassroomSet, and ClassroomNResources.
"""
from django.db import models


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
    location = models.ForeignKey("Location", on_delete=models.CASCADE)


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