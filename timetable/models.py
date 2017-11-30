# -*- coding: utf-8 -*-
from django.db import models
from django.db.models import Count, Q
from django.contrib.auth.models import User
import datetime
from _collections import defaultdict

WEEKDAYS = (
    ('MON', 'ponedeljek'),
    ('TUE', 'torek'),
    ('WED', 'sreda'),
    ('THU', 'četrtek'),
    ('FRI', 'petek'),
)

WEEKDAYSSLO = dict()
for (en, slo) in WEEKDAYS:
    WEEKDAYSSLO[en] = slo

PREFERENCELEVELS = (
    ('WANT', 'Want'),
    ('HATE', 'Hate'),
    ('CANT', 'Unable'),
)

WORKHOURS = (
    ('07:00', '07:00'),
    ('08:00', '08:00'),
    ('09:00', '09:00'),
    ('10:00', '10:00'),
    ('11:00', '11:00'),
    ('12:00', '12:00'),
    ('13:00', '13:00'),
    ('14:00', '14:00'),
    ('15:00', '15:00'),
    ('16:00', '16:00'),
    ('17:00', '17:00'),
    ('18:00', '18:00'),
    ('19:00', '19:00'),
    ('20:00', '20:00'),
    ('21:00', '21:00'),
)

AFTERHOURS = ('22:00', '22:00')

PEOPLEVALUEPREFERENCES = (
    ('MAXDAYSWEEK', 'Max days per week'),
    ('MINDAYSWEEK', 'Min days per week'),
    ('MAXHOURSDAY', 'Max hours per day'),
    ('MINHOURSDAY', 'Min hours per day'),
    ('MAXHOURSCONT', 'Max hours continuously'),
    ('MAXGAPSDAY', 'Max gaps per day'),
    ('MAXGAPSWEEK', 'Max gaps per week'),
    ('MAXCHANGESWEEK', 'Max building changes per week'),
    ('MAXCHANGESDAY', 'Max building changes per day'),
    ('MINCHANGEGAP', 'Min gap between changes'),
)


TAGVALUEPREFERENCES = (
    ('MAXDAYSWEEK', 'Max days per week for a tag'),
    ('MINDAYSWEEK', 'Min days per week for a tag'),
    ('MAXHOURSDAY', 'Max hours per day for a tag'),
    ('MINHOURSDAY', 'Min hours per day for a tag'),
    ('MAXGAPSDAY', 'Max gaps per day for a tag'),
    ('MAXGAPSWEEK', 'Max gaps per week for a tag'),
    ('MAXCHANGESWEEK', 'Max building changes per week'),
    ('MAXCHANGESDAY', 'Max building changes per day'),
    ('MINCHANGEGAP', 'Min gap between changes'),
    ('MINACTIVITYGAP', 'Min gap between a set of activities'),
    ('MULSIZE', 'Multiply group size for activities with this tag by a factor'),
    ('SHRINKGROUPS', 'Group size for activity -> Group size - VALUE'),
    ('MAXROOMSREALIZATIONS', 'Maximal number of different rooms used by the set of realization'),
)

PREFERENCETYPES = (
    ('COMMENT', 'A random comment'),
    ('NOOVERLAP', 'Must not overlap'),
    ('GROUPED', 'Activities must be grouped'),
    ('CONSECUTIVE', 'Realizations must be consecutive'),
    ('ENDSSTUDENTSDAY', "Activity ends student's day"),
    ('SAMEDAY', 'A set of activities/realizations must be on the same day'),
)

ACTIVITYTYPES = (
    ('LAB', 'Laborant vaje'),
    ('LV', 'Laboratorijske vaje'),
    ('AV', 'Avditorne vaje'),
    ('P', 'Predavanja'),
    ('TUT', 'Tutorstvo'),
    ('REP', 'Repetitorij')
)


class Resource(models.Model):
    def __str__(self):
        return self.name
    name = models.CharField(max_length=255)


class Heuristic(models.Model):
    def __str__(self):
        return self.name
    name = models.CharField(max_length=255)


class ActivitySet(models.Model):
    def __str__(self):
        return self.name
    created = models.DateTimeField(default=datetime.datetime.now)
    slug = models.SlugField()
    name = models.CharField(max_length=64)
    locked = models.BooleanField(default=False)

    @property
    def teachers(self):
        return Teacher.objects.filter(activities__activityset__exact=self).distinct()

    @property
    def groups(self):
        return Group.objects.filter(activities__activityset__exact=self).distinct()


class PreferenceSet(models.Model):
    def __str__(self):
        return self.name
    # children = models.ManyToManyField(PreferenceSet, symetrical = False)
    created = models.DateTimeField(default=datetime.datetime.now)
    slug = models.SlugField()
    name = models.CharField(max_length=64)
    locked = models.BooleanField(default=False)


class ClassroomSet(models.Model):
    def __str__(self):
        return self.name
    created = models.DateField()
    slug = models.SlugField()
    name = models.CharField(max_length=64)
    locked = models.BooleanField(default=False)
    classrooms = models.ManyToManyField('Classroom', blank=True,
                                        related_name='classroomset')


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
        last = self.short_name.split('_')[-1]
        llast = len(last)
        if self._is_number(last) and len(last) == 1:
            last = '0' + last
        return "{0} ({1}), {2}".format(self.short_name[:-llast]+last, self.size, self.groupset)

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
    parent = models.ForeignKey('self', null=True, blank=True)
    groupset = models.ForeignKey('GroupSet', related_name='groups')

    # Return the second part of group name, split by '_'
    @property
    def study(self):
        split = self.short_name.split('_')
        if len(split) >= 2:
            return split[1]
        # No study found: return default
        return "UNKNOWN"

    @property
    def classyear(self):
        split = self.short_name.split('_')
        return split[0]

    @property
    def type(self):
        split = self.short_name.split('_')
        if len(split) >= 3:
            return split[2]
        # No study found: return default
        return None

    @property
    def groupnum(self):
        split = self.short_name.split('_')
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
        split = self.short_name.split('_')
        if len(split) >= 5:
            return split[-3]
        return ""

    def children(self, scope='sub'):
        """
        Scope = sub for all children (default), one for single level.
        """
        l = []
        for i in self.group_set.all():
            l.append(i)
            if scope == 'sub':
                l += i.children()
        l.sort(key=lambda x: x.name)
        return l

    def family(self):
        return self.children() + [self] + self.parents

    @property
    def time_preferences(self):
        return GroupTimePreference.objects.filter(group=self)

    @property
    def all_time_preferences(self):
        """
        Return all time preferences (as a QuerySet) for the group,
        including time preferences of all parents of this group.
        """
        groups = self.parents + [self]
        return GroupTimePreference.objects.filter(group__in=groups)

    def is_available(self, day, timeslot, non_available_levels=['CANT']):
        '''
        Return True if group is available in the given timeslot.
        Available means that group has no GroupTimePreferences that
        would make it unavailable in the given timeslot.
        The timeslot is a set of WORKHOURS.
        '''
        time_preferences = self.all_time_preferences.filter(
            level__in=non_available_levels)
        non_available_hours = defaultdict(set)
        for time_preference in time_preferences:
            tp_hours = time_preference.hours()
            tp_day = time_preference.day
            non_available_hours[tp_day].update(tp_hours)
        return non_available_hours[day].isdisjoint(timeslot)

    @property
    def value_preferences(self):
        return GroupValuePreference.objects.filter(group=self)

    class Meta:
        ordering = ['name']


class Activity(models.Model):
    def __str__(self):
        groups = self.groups.all()
        return "{0} {1}".format(self.name, "-".join([str(group) for group in groups]))
    # old_teachers = models.ManyToManyField('Teacher', blank=True, through='ActivityPercentage', related_name='old_teacher_activities')
    teachers = models.ManyToManyField('Teacher', blank=True, related_name='activities')
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=32)
    activityset = models.ForeignKey('ActivitySet', related_name='activities')
    type = models.CharField(max_length=4, choices=ACTIVITYTYPES)
    locations = models.ManyToManyField('Location', blank=False)
    duration = models.IntegerField()
    requirements = models.ManyToManyField('Resource', blank=True)
    requirements_per_student = models.ManyToManyField('Resource', blank=True,
                                                      through='NRequirementsPerStudent',
                                                      related_name='per_student_activities')
    groups = models.ManyToManyField('Group', blank=True, related_name='activities')
    mustNotOverlap = models.ManyToManyField('self', symmetrical=True, blank=True)
    before = models.ManyToManyField('self', symmetrical=False, related_name='after', blank=True)

    def groups_on_realizations_without_teachers(self, groupset):
        realizations = self.realizations_without_teachers(groupset)
        return self.groups.filter(realizations__in=realizations, groupset=groupset).distinct()

    def realizations_without_teachers(self, groupset):
        annotated_realizations = self.realizations.all().annotate(teacher_count=Count('teachers'))
        return annotated_realizations.filter(teacher_count=0)

    def groups_without_realization(self, groupset):
        """
        Return the queryset of all groups on acvitiy that are not part of any
        realiazation related to this activity.
        All groups are limited to a given groupset.
        """
        groups = Group.objects.filter(activities__exact=self, groupset=groupset)
        return groups.exclude(realizations__in=self.realizations.all(), groupset=groupset)

    def preferred_rooms(self, timetable=None):
        location_ids = self.locations.all().values_list('id', flat=True)
        if timetable is None:
            cl = Classroom.objects.filter(location__id__in=location_ids).distinct()
        else:
            cl = Classroom.objects.filter(classroomset__timetables=timetable,
                                          location__id__in=location_ids).distinct()
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
        ordering = ['name']


class NRequirementsPerStudent(models.Model):
    def __str__(self):
        return "{0}/{2}({1})".format(self.resource, self.activity, self.n)

    class Meta:
        unique_together = (("resource", "activity"),)
    resource = models.ForeignKey(Resource)
    activity = models.ForeignKey(Activity)
    n = models.FloatField()


class ActivityRealization(models.Model):
    def __str__(self):
        return self.activity.name + " " + \
            " ".join([str(i) for i in self.teachers.all()]) + " " + \
            " ".join([str(i) for i in self.groups.all()])

    activity = models.ForeignKey('Activity', related_name='realizations')
    teachers = models.ManyToManyField('Teacher', related_name='activity_realizations',
                                      blank=True)
    groups = models.ManyToManyField('Group', blank=True, related_name='realizations')
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
            classrooms = classrooms.filter(n_resources__resource=nr.resource,
                                           n_resources__n__gte=nr.n * n_students)
        return classrooms

    def id_string(self):
        self.activity.name + "-" + self.id


#class ActivityPercentage(models.Model):
#    teacher = models.ForeignKey('Teacher')
#    activity = models.ForeignKey('Activity')
    # value = models.FloatField(default=1.0)


class Teacher(models.Model):
    def __str__(self):
        s = "Ambrož Zasekamožević"
        if self.user is not None:
            s = "{0}, {1}".format(self.user.last_name, self.user.first_name)
        if s == '':
            s = self.user
        return s

    user = models.OneToOneField(User, null=True, related_name='teacher')
    # activities = models.ManyToManyField('Activity', blank=True, through='ActivityPercentage')
    code = models.CharField(max_length=32, default="", unique=True)

    @property
    def time_preferences(self):
        return TeacherTimePreference.objects.filter(teacher=self)

    @property
    def value_preferences(self):
        return TeacherValuePreference.objects.filter(teacher=self)

    @property
    def descriptive_preferences(self):
        return TeacherDescriptivePreference.objects.filter(teacher=self)

    def id_string(self):
        return "{0}({1})".format(self.__str__(), self.user)


class LocationDistance(models.Model):
    distance = models.IntegerField()
    time = models.IntegerField()
    from_location = models.ForeignKey('Location', related_name='from_location')
    to_location = models.ForeignKey('Location', related_name='to_location')


class Classroom(models.Model):
    def __str__(self):
        return "{0} ({1})".format(self.name, self.short_name)
    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=32)
    resources = models.ManyToManyField(Resource, through='ClassroomNResources',
                                       blank=True, related_name='classrooms')
    capacity = models.IntegerField()
    location = models.ForeignKey('Location')


class ClassroomNResources(models.Model):
    def __str__(self):
        return "{0}/{1}({2})".format(self.resource, self.classroom, self.n)

    class Meta:
        unique_together = (("resource", "classroom"),)
    resource = models.ForeignKey(Resource)
    classroom = models.ForeignKey(Classroom, related_name='n_resources')
    n = models.IntegerField()


class TimetableSet(models.Model):
    def __str__(self):
        return self.name
    slug = models.SlugField()
    public = models.BooleanField(default=False)
    name = models.CharField(max_length=64)
    modified = models.DateTimeField(auto_now_add=True)
    timetables = models.ManyToManyField('Timetable', related_name='timetable_sets')

    @property
    def allocations(self):
        return Allocation.objects.filter(
            Q(timetable__timetable_sets__pk=self.pk) |\
            Q(timetable__respected_by__timetable_sets__pk=self.pk)).distinct()


def defaultTimetableSet():
    return TimetableSet.objects.filter(public=True).order_by('-modified')[0]

def defaultTimetable():
    return Timetable.objects.filter(public=True,
                                    start__lte=datetime.datetime.now()).order_by('-start')[0]

class Timetable(models.Model):
    def __str__(self):
        return self.name
    # respects = models.ManyToManyField('self', blank=True)
    activityset = models.ForeignKey('ActivitySet', blank=True)

    preferenceset = models.ForeignKey('PreferenceSet', blank=True, null=True)
    groupset = models.ForeignKey('GroupSet', blank=True, null=True, related_name='timetables')
    classroomset = models.ForeignKey('ClassroomSet', blank=False, null=False,
                                     related_name='timetables')

    respects = models.ManyToManyField("self", related_name="respected_by",
                                      symmetrical=False, blank=True)

    @property
    def allocations(self):
        return Allocation.objects.filter(
            Q(timetable__pk = self.pk) |\
            Q(timetable__respected_by__pk = self.pk))

    @property
    def classrooms(self):
        return self.classroomset.classrooms

    @property
    def realizations(self):
        return ActivityRealization.objects.filter(activity__activityset=self.activityset)

    @property
    def preferences(self):
        return self.preferenceset.preferences
    name = models.CharField(max_length=64)
    slug = models.SlugField()
    public = models.BooleanField(default=False)
    start = models.DateField(default=datetime.date.today)
    end = models.DateField(default=datetime.date.today)
    preference_deadline = models.DateField(default=datetime.date.today)

    @property
    def activities(self):
        return self.activityset.activities

    @property
    def teachers(self):
        return self.activityset.teachers

    @property
    def groups(self):
        return self.groupset.groups


class Allocation(models.Model):
    def __str__(self):
        # return "{0} {1} {2}".format(self.classroom, self.day, self.start)
        name = ''
        teachers = ''
        duration = '0'
        tt = '?'
        try:
            name = self.activityRealization.activity.name
            teachers = " ".join([str(i) for i in self.activityRealization.teachers.all()])
            duration = str(self.duration)
            tt = str(self.timetable)
        except:
            pass
        s = teachers + \
            " [" + name + ']' + \
            " " + str(self.classroom) + " " + self.day + \
            ' ' + self.start + ' (+' + duration + ')' + \
            ' ' + tt
        return s

    def mailRepresentationFrom(self):
        return '{0}, {1}, {2} ob {3}'.format(self.activityRealization.activity.name,
                                             self.classroom,
                                             WEEKDAYSSLO[self.day],
                                             self.start)

    def mailRepresentationTo(self):
        return "{0}, {1} ob {2}".format(self.classroom, WEEKDAYSSLO[self.day],
                                        self.start)

    timetable = models.ForeignKey(Timetable, related_name='own_allocations')
    # respected_by = models.ManyToManyField(Timetable, related_name='allocations')
    activityRealization = models.ForeignKey(ActivityRealization, related_name='allocations')
    classroom = models.ForeignKey(Classroom, null=True)
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)

    @property
    def end(self):
        endi = WORKHOURS.index((self.start, self.start))+self.duration
        if endi >= len(WORKHOURS):
            return AFTERHOURS[0]
        return WORKHOURS[endi][0]

    @property
    def duration(self):
        return self.activityRealization.duration

    @property
    def teachers(self):
        return self.activityRealization.teachers

    @property
    def groups(self):
        """
        Return the QuerySet of groups on this realization.
        """
        return self.activityRealization.groups.all()

    @property
    def hours(self):
        i = WORKHOURS.index((self.start, self.start))
        hours = WORKHOURS[i:min(len(WORKHOURS), i+self.duration)]
        return [hour[0] for hour in hours]

    @property
    def are_groups_available(self):
        '''
        Return True if groups on this allocation are available according to
        their GroupTimePreferences (with level CANT).
        Returns False otherwise.
        '''
        return len(self.groups_not_available) == 0

    @property
    def groups_not_available(self):
        """
        Return the list of not-available groups in the allocation timeslot.
        """
        return [group for group in self.groups
                if not group.is_available(self.day, set(self.hours))]

    @property
    def startWithinWorkingHours(self):
        """
        Return the set of allocations that starts when this allocation is active.
        """
        return Allocation.objects.filter(timetable=self.timetable, day=self.day,
                                         start__in=self.hours).exclude(id=self.id)

    def is_classroom_too_small(self):
        """
        Return True if the classroom is too small for this allocation.
        """
        return self.activityRealization.size > self.classroom.capacity

    def is_classroom_too_big(self, percentage):
        """
        Return True if the classroom is too big for this allocation.
        At least percentage (given as float between 0 and 1)
        has to be filled.
        """
        min_group_size = self.classroom.capacity * percentage
        return self.activityRealization.size < min_group_size


class Tag(models.Model):
    def __str__(self):
        return self.name
    name = models.CharField(max_length=32)
    description = models.TextField()
    teachers = models.ManyToManyField('Teacher', blank=True, related_name='tags')
    activities = models.ManyToManyField('Activity', blank=True, related_name='tags')
    activity_realizations = models.ManyToManyField('ActivityRealization',
                                                   blank=True, related_name='tags')
    groups = models.ManyToManyField('Group', blank=True, related_name='tags')

    @property
    def value_preferences(self):
        return TagValuePreference.objects.filter(tag=self)


class Preference(models.Model):
    def __str__(self):
        return self.level + \
            " " + str(self.weight)

    preferenceset = models.ForeignKey("PreferenceSet", related_name="preferences")
    level = models.CharField(max_length=4, choices=PREFERENCELEVELS)
    weight = models.FloatField(default=1.0)

    def adjustedWeight(self):
        if self.level == 'CANT':
            return 1.0
        else:
            return self.weight


class GroupPreference(Preference):
    def __str__(self):
        return str(self.group) + ' ' + str(self.level)

    group = models.ForeignKey('Group', related_name='group_preferences')

    def adjustedWeight(self, optionalAdjustment=0.5):
        if self.level == 'CANT':
            return 1.0
        else:
            return self.weight


class GroupTimePreference(GroupPreference):
    def __str__(self):
        return "{0}: {1} {2} {3}, {4} ({5})".format(self.group, self.level, self.day,
                                                     self.start, self.duration,
                                                     Preference.__str__(self))

    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    duration = models.IntegerField(default=1)

    def adjustedWeight(self):
        return GroupPreference.adjustedWeight(self, 0.5)

    def hours(self):
        index = WORKHOURS.index((self.start, self.start))
        return [i[0] for i in WORKHOURS[index:min(len(WORKHOURS), index+self.duration)]]


class GroupValuePreference(GroupPreference):
    def __str__(self):
        return str(self.group) + " " + ' ' + str(self.level) +\
            self.name + ',' + str(self.value)
    value = models.IntegerField()
    name = models.CharField(max_length=24, choices=PEOPLEVALUEPREFERENCES)

    def adjustedWeight(self):
        return GroupPreference.adjustedWeight(self, 0.5)


class TeacherPreference(Preference):
    def __str__(self):
        return str(self.teacher) + ' ' + str(self.level)

    teacher = models.ForeignKey('Teacher', related_name='teacher_preferences')

    def adjustedWeight(self, optionalAdjustment=1, min_weight=0, max_weight=1):
        if self.level == 'CANT':
            return 1.0
        else:
            # Preferencea dolžine 2 ima weight 1
            # Dve preferenci dolžine 2 pa 2
            # Zato ta formula (čeprav lepa in hitra) ni čisto dobra za TeacherTimePreference.
            preferences = TeacherPreference.objects.filter(teacher=self.teacher, level=self.level,
                                                           preferenceset=self.preferenceset)
            wsum = preferences.aggregate(s=models.Sum('weight'))
            original_weight = optionalAdjustment*self.weight / wsum['s']
            return min_weight + original_weight * (max_weight - min_weight)


class TeacherValuePreference(TeacherPreference):
    def __str__(self):
        return str(self.teacher) + " " + ' ' + str(self.level) +\
            str(self.name) + ',' + str(self.value)
    value = models.IntegerField()
    name = models.CharField(max_length=24, choices=PEOPLEVALUEPREFERENCES)

    def adjustedWeight(self):
        return self.weight
        # return TeacherPreference.adjustedWeight(self, 0.5)


class TeacherTimePreference(TeacherPreference):
    def __str__(self):
        return str(self.teacher) + " " + ' ' + str(self.level) + \
            str(self.day) + ',' + str(self.start) + ' (+' + str(self.duration)+')' + \
            " " + Preference.__str__(self)
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    duration = models.IntegerField(default=1)

    def adjustedWeight(self, min_weight=0.4, max_weight=0.99):
        if self.level == 'CANT':
            return 1.0
        else:
            wsum = 0
            preferences = TeacherTimePreference.objects.filter(teacher=self.teacher,
                                                               level=self.level,
                                                               preferenceset=self.preferenceset)
            for preference in preferences:
                wsum += preference.weight * preference.duration
            original_weight = self.weight / wsum
            return min_weight + original_weight * (max_weight - min_weight)

    def hours(self):
        index = WORKHOURS.index((self.start, self.start))
        return [i[0] for i in WORKHOURS[index:min(len(WORKHOURS), index+self.duration)]]


class TeacherDescriptivePreference(TeacherPreference):
    def __str__(self):
        return str(self.teacher) + ' ' + str(self.level) + ',' + str(self.value)

    typename = models.CharField(max_length=16, choices=PREFERENCETYPES, default='COMMENT')
    value = models.TextField(blank=True)

    def adjustedWeight(self):
        return 0.0


class ActivityPreference(Preference):
    def __str__(self):
        return str(self.classroom) + " " + str(self.activity) + \
            Preference.__str__(self)
    classroom = models.ForeignKey('Classroom')
    activity = models.ForeignKey('Activity')


class ActivityTimePlacePreference(Preference):
    def __str__(self):
        return str(self.classroom) + " " + str(self.activity) + self.day + \
            " " + self.start + " (+" + str(self.duration) + ")" + Preference.__str__(self)
    classroom = models.ForeignKey(Classroom)
    activity = models.ForeignKey(Activity)
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    duration = models.IntegerField()


class TagPreference(Preference):
    def __str__(self):
        return self.tag + ' ' + self.level

    tag = models.ForeignKey('Tag', related_name='preferences')

    def adjustedWeight(self, optionalAdjustment=0.5):
        if self.level == 'CANT':
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
        return str(self.tag) + " " + ' ' + str(self.level) + \
            str(self.day) + ',' + str(self.start) + \
            ' (+' + str(self.duration)+')' + \
            " " + Preference.__str__(self)
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)
    duration = models.IntegerField(default=1)

    def adjustedWeight(self):
        return TagPreference.adjustedWeight(self, 0.5)

    def hours(self):
        index = WORKHOURS.index((self.start, self.start))
        return [i[0] for i in WORKHOURS[index:min(len(WORKHOURS), index+self.duration)]]


class TagDescriptivePreference(TagPreference):
    def __str__(self):
        return str(self.tag) + ' ' + str(self.level) + ',' + str(self.value)
    typename = models.CharField(max_length=16, choices=PREFERENCETYPES, default='COMMENT')
    value = models.TextField()

    def adjustedWeight(self):
        return 0.0


class Location(models.Model):
    def __str__(self):
        return self.name
    name = models.CharField(max_length=100)
    distances = models.ManyToManyField("self", through='LocationDistance', symmetrical=False)

    @property
    def shortLocationName(self):
        if "Sežana" in self.name:
            return "Sežana"
        else:
            return "Ljubljana"
