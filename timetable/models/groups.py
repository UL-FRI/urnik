"""
Group-related models: Group and GroupSet.
"""
import datetime
from collections import defaultdict

from django.db import models

from .constants import WEEKDAYS


class GroupSet(models.Model):
    def __str__(self):
        return self.name

    # children = models.ManyToManyField(PreferenceSet, symetrical = False)
    created = models.DateTimeField()
    slug = models.SlugField()
    name = models.CharField(max_length=64)
    locked = models.BooleanField(default=False)


class Group(models.Model):
    def __str__(self):
        last = self.short_name.split("_")[-1]
        llast = len(last)
        if self._is_number(last) and len(last) == 1:
            last = "0" + last
        return "{0} ({1}), {2}".format(
            self.short_name[:-llast] + last, self.size, self.groupset
        )

    def _is_number(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    def id_string(self):
        return self.short_name

    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=64)
    size = models.IntegerField(null=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="+", on_delete=models.CASCADE
    )
    groupset = models.ForeignKey(
        "GroupSet", related_name="groups", on_delete=models.CASCADE
    )
    visible_in_navigation = models.BooleanField(default=False, null=False, blank=False)

    # Return the second part of group name, split by '_'
    @property
    def study(self):
        split = self.short_name.split("_")
        if len(split) >= 2:
            return split[1]
        # No study found: return default
        return "UNKNOWN"

    @property
    def classyear(self):
        split = self.short_name.split("_")
        return split[0]

    @property
    def type(self):
        split = self.short_name.split("_")
        if len(split) >= 3:
            return split[2]
        # No study found: return default
        return None

    @property
    def groupnum(self):
        split = self.short_name.split("_")
        if len(split) >= 4:
            return split[-1]
        # No study found: return default
        return -1

    @property
    def parents(self):
        """
        Return the list of all parents.
        First parent is the first element in the list,
        its parent second...
        """
        parent = self.parent
        parents = []
        while parent is not None:
            parents.append(parent)
            parent = parent.parent
        return parents

    @property
    def subjectname(self):
        split = self.short_name.split("_")
        if len(split) >= 5:
            return split[-3]
        return ""

    def children(self, scope="sub"):
        """
        Scope = sub for all children (default), one for single level.
        """
        children = []
        for group in Group.objects.filter(parent=self):
            children.append(group)
            if scope == "sub":
                children += group.children()
        children.sort(key=lambda x: x.name)
        return children

    def family(self):
        return self.children() + [self] + self.parents

    @property
    def time_preferences(self):
        from .preferences import GroupTimePreference
        return GroupTimePreference.objects.filter(group=self)

    @property
    def all_time_preferences(self):
        """
        Return all time preferences (as a QuerySet) for the group,
        including time preferences of all parents of this group.
        """
        from .preferences import GroupTimePreference
        groups = self.parents + [self]
        return GroupTimePreference.objects.filter(group__in=groups)

    def is_available(self, day, timeslot, non_available_levels=["CANT"]):
        """
        Return True if group is available in the given timeslot.
        Available means that group has no GroupTimePreferences that
        would make it unavailable in the given timeslot.
        The timeslot is a set of WORKHOURS.
        """
        time_preferences = self.all_time_preferences.filter(
            level__in=non_available_levels
        )
        non_available_hours = defaultdict(set)
        for time_preference in time_preferences:
            tp_hours = time_preference.hours()
            tp_day = time_preference.day
            non_available_hours[tp_day].update(tp_hours)
        return non_available_hours[day].isdisjoint(timeslot)

    @property
    def value_preferences(self):
        from .preferences import GroupValuePreference
        return GroupValuePreference.objects.filter(group=self)

    class Meta:
        ordering = ["name"]