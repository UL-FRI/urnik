"""
All preference-related models.
"""
from django.db import models

from .constants import (
    PREFERENCELEVELS,
    WEEKDAYS,
    WORKHOURS,
    PEOPLEVALUEPREFERENCES,
    TAGVALUEPREFERENCES,
    PREFERENCETYPES,
)


class Preference(models.Model):
    def __str__(self):
        return self.level + " " + str(self.weight)

    preferenceset = models.ForeignKey(
        "PreferenceSet", related_name="preferences", on_delete=models.CASCADE
    )
    level = models.CharField(max_length=4, choices=PREFERENCELEVELS)
    weight = models.FloatField(default=1.0)

    def adjustedWeight(self):
        if self.level == "CANT":
            return 1.0
        else:
            return self.weight


class GroupPreference(Preference):
    def __str__(self):
        return str(self.group) + " " + str(self.level)

    group = models.ForeignKey(
        "Group", related_name="group_preferences", on_delete=models.CASCADE
    )

    def adjustedWeight(self, optional_adjustment=0.5):
        if self.level == "CANT":
            return 1.0
        else:
            return self.weight


class GroupTimePreference(GroupPreference):
    def __str__(self):
        return "{0}: {1} {2} {3}, {4} ({5})".format(
            self.group,
            self.level,
            self.day,
            self.start,
            self.duration,
            Preference.__str__(self),
        )

    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    duration = models.IntegerField(default=1)

    def adjustedWeight(self):
        return GroupPreference.adjustedWeight(self, 0.5)

    def hours(self):
        index = WORKHOURS.index((self.start, self.start))
        return [
            i[0] for i in WORKHOURS[index : min(len(WORKHOURS), index + self.duration)]
        ]


class GroupValuePreference(GroupPreference):
    def __str__(self):
        return (
            str(self.group)
            + " "
            + " "
            + str(self.level)
            + self.name
            + ","
            + str(self.value)
        )

    value = models.IntegerField()
    name = models.CharField(max_length=24, choices=PEOPLEVALUEPREFERENCES)

    def adjustedWeight(self):
        return GroupPreference.adjustedWeight(self, 0.5)


class TeacherPreference(Preference):
    def __str__(self):
        return str(self.teacher) + " " + str(self.level)

    teacher = models.ForeignKey(
        "Teacher", related_name="teacher_preferences", on_delete=models.CASCADE
    )

    def adjustedWeight(self, optional_adjustment=1, min_weight=0, max_weight=1):
        if self.level == "CANT":
            return 1.0
        else:
            # Preferencea dolžine 2 ima weight 1
            # Dve preferenci dolžine 2 pa 2
            # Zato ta formula (čeprav lepa in hitra) ni čisto dobra za TeacherTimePreference.
            preferences = TeacherPreference.objects.filter(
                teacher=self.teacher, level=self.level, preferenceset=self.preferenceset
            )
            wsum = preferences.aggregate(s=models.Sum("weight"))
            original_weight = optional_adjustment * self.weight / wsum["s"]
            return min_weight + original_weight * (max_weight - min_weight)


class TeacherValuePreference(TeacherPreference):
    def __str__(self):
        return (
            str(self.teacher)
            + " "
            + " "
            + str(self.level)
            + str(self.name)
            + ","
            + str(self.value)
        )

    value = models.IntegerField()
    name = models.CharField(max_length=24, choices=PEOPLEVALUEPREFERENCES)

    def adjustedWeight(self):
        return self.weight
        # return TeacherPreference.adjustedWeight(self, 0.5)


class TeacherTimePreference(TeacherPreference):
    def __str__(self):
        return (
            str(self.teacher)
            + " "
            + " "
            + str(self.level)
            + str(self.day)
            + ","
            + str(self.start)
            + " (+"
            + str(self.duration)
            + ")"
            + " "
            + Preference.__str__(self)
        )

    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    duration = models.IntegerField(default=1)

    def adjustedWeight(self, min_weight=0.4, max_weight=0.99):
        if self.level == "CANT":
            return 1.0
        else:
            wsum = 0
            preferences = TeacherTimePreference.objects.filter(
                teacher=self.teacher, level=self.level, preferenceset=self.preferenceset
            )
            for preference in preferences:
                wsum += preference.weight * preference.duration
            original_weight = self.weight / wsum
            return min_weight + original_weight * (max_weight - min_weight)

    def hours(self):
        index = WORKHOURS.index((self.start, self.start))
        return [
            i[0] for i in WORKHOURS[index : min(len(WORKHOURS), index + self.duration)]
        ]


class TeacherDescriptivePreference(TeacherPreference):
    def __str__(self):
        return str(self.teacher) + " " + str(self.level) + "," + str(self.value)

    typename = models.CharField(
        max_length=16, choices=PREFERENCETYPES, default="COMMENT"
    )
    value = models.TextField(blank=True)

    def adjustedWeight(self):
        return 0.0


class ActivityPreference(Preference):
    def __str__(self):
        return str(self.classroom) + " " + str(self.activity) + Preference.__str__(self)

    classroom = models.ForeignKey("Classroom", on_delete=models.CASCADE)
    activity = models.ForeignKey("Activity", on_delete=models.CASCADE)


class ActivityTimePlacePreference(Preference):
    def __str__(self):
        return (
            str(self.classroom)
            + " "
            + str(self.activity)
            + self.day
            + " "
            + self.start
            + " (+"
            + str(self.duration)
            + ")"
            + Preference.__str__(self)
        )

    classroom = models.ForeignKey("Classroom", on_delete=models.CASCADE)
    activity = models.ForeignKey("Activity", on_delete=models.CASCADE)
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    duration = models.IntegerField()


class TagPreference(Preference):
    def __str__(self):
        return "{} {}".format(self.tag, self.level)

    tag = models.ForeignKey("Tag", related_name="preferences", on_delete=models.CASCADE)

    def adjustedWeight(self, optional_adjustment=0.5):
        if self.level == "CANT":
            return 1.0
        else:
            return self.weight


class TagValuePreference(TagPreference):
    def __str__(self):
        return "{}: {} {} {}".format(self.tag, self.level, self.name, self.value)

    value = models.IntegerField()
    name = models.CharField(max_length=24, choices=TAGVALUEPREFERENCES)

    def adjustedWeight(self):
        return TagPreference.adjustedWeight(self, 0.5)


class TagTimePreference(TagPreference):
    def __str__(self):
        return (
            str(self.tag)
            + " "
            + " "
            + str(self.level)
            + str(self.day)
            + ","
            + str(self.start)
            + " (+"
            + str(self.duration)
            + ")"
            + " "
            + Preference.__str__(self)
        )

    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    duration = models.IntegerField(default=1)

    def adjustedWeight(self):
        return TagPreference.adjustedWeight(self, 0.5)

    def hours(self):
        index = WORKHOURS.index((self.start, self.start))
        return [
            i[0] for i in WORKHOURS[index : min(len(WORKHOURS), index + self.duration)]
        ]


class TagDescriptivePreference(TagPreference):
    def __str__(self):
        return str(self.tag) + " " + str(self.level) + "," + str(self.value)

    typename = models.CharField(
        max_length=16, choices=PREFERENCETYPES, default="COMMENT"
    )
    value = models.TextField()

    def adjustedWeight(self):
        return 0.0