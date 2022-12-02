import datetime
import logging
from collections import defaultdict
from operator import attrgetter, itemgetter

import frinajave
import friprosveta
import timetable.models
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from friprosveta.studis import Studenti
from timetable.models import Group

logger = logging.getLogger(__name__)

# Create your models here.
REALIZATIONSIZES = [
    ("MAJHNE", "izvajanje v majhnih skupinah"),
    ("ASISTENTA", "izvajanje v velikih skupinah z asistentoma"),
    (
        "DEMONSTRATOR",
        "izvajanje v velikih skupinah z enim " " asistentom in demonstratorjema",
    ),
    ("DRUGO", "drugo"),
]

"""
Enrolment types: #studis_id, #description
"""
ENROLMENTTYPES = [
    (4, "Prvi vpis v letnik"),
    (41, "Vzporedni vpis"),
    (42, "Prvi vpis diplomanta"),
    (43, "Prepis"),
    (44, "Dodatno leto (absolvent)"),
    (5, "Ponavljanje letnika"),
    (7, "Podaljšanje statusa po končanem dodatnem letu"),
    (21, "Izjemno podaljšanje statusa"),
    (1, "Vpis po merilih za prehode"),
    (45, "Vpis v semester skupnega študijskega programa"),
    (47, "Vpis po merilih za prehode v isti letnik"),
    (51, "Prvi vpis v program - v višji letnik na podlagi priznanih obveznosti"),
    (46, "Vpis za zaključek"),
    (3, "Občan"),
    (23, "Pavzer"),
    (25, "Študentje drugih fakultet UL"),
    (26, "Študentje skupnega programa kjer fakulteta ni nosilec"),
    (27, "Študentje drugih univerz"),
    (28, "Polaganje izpitov izven študijskega programa"),
    (48, "Študentje drugih univerz brez poročanja EVŠ"),
    (49, "Pavzerji skupnih študijskih programov"),
]

ENROLMENTSOURCES = [
    ("studis_preenrolment", "Študis - predvpis"),
    ("studis_unconfirmed", "Študis - v postopku"),
    ("studis_confirmed", "Študis - potrjen"),
]


class GroupSizeHint(models.Model):
    def __str__(self):
        return "{0}: {1} ({2})".format(self.method, self.group, self.size)

    method = models.CharField(
        max_length=128, help_text="Method used to calculate the size"
    )
    size = models.IntegerField(default=0, help_text="Calculated size of the group")
    group = models.ForeignKey(timetable.models.Group, on_delete=models.CASCADE)

    @staticmethod
    def strategy(group, methods, strategy_name):
        """
        Return new group size based on methods and strategy_name. Strategy name can be one
        of the following.
         - first: take the first hint. When there is no first hint None is returned.
         - first-non-zero: the first non-zero group size hint is considered. When no non-zero
           hint is given None is returned.
         - max: take the max hint. When no hint is given None is returned.
         - max-non-zero: take the max non-zero hint. When no hint is given group size is not updated.
         - max-group: take the maximum value from current group size and max hint.

        If strategy_name is none of the above it raises KeyError exception.
        """

        def non_zero(hints):
            return [h for h in hints if h.size != 0]

        def first(group, hints):
            return hints[0].size

        def first_non_zero(group, hints):
            return first(group, non_zero(hints))

        def mymax(group, hints):
            return max(h.size for h in hints)

        def max_non_zero(group, hints):
            return mymax(group, non_zero(hints))

        def max_group(group, hints):
            return max(group.size, mymax(group, hints))

        strategies = {
            "first": first,
            "first-non-zero": first_non_zero,
            "max": mymax,
            "max-non-zero": max_non_zero,
            "max-group": max_group,
        }
        hints = [
            GroupSizeHint.objects.get(group=group, method=method)
            for method in methods
            if GroupSizeHint.objects.filter(group=group, method=method).exists()
        ]
        strategy = strategies[strategy_name]
        try:
            return strategy(group, hints)
        except ValueError:  # max of the empty sequence
            return None
        except IndexError:  # list index out of range (first element of empty sequence)
            return None

    @staticmethod
    def size_from_old_group(group, groupset, enrollment_types=[4, 26]):
        """
        Calculate group size hint from old groups and write site in the
        table GroupSizeHint with method "group from #groupset with enrollment types #enrollement_types".
        Old group is matched by the short group name.
        :param groupset: used to get enrollments.
        :param group: group object we are calculating size hint for.
        :param enrollment_types: types of enrolments to consider. See ENROLMENTTYPES list for details.
        :return: None
        """
        logger.info("Calculating size hints from old groups")
        logger.debug("groupset: {0}".format(groupset))
        logger.debug("enrollment types: {0}".format(enrollment_types))
        method = "group from {0} with enrollment types {1}".format(
            groupset, enrollment_types
        )
        old_group = groupset.groups.get(short_name=group.short_name)
        logger.debug("oldgroup: {0}".format(old_group))
        students = old_group.students.all()
        logger.debug("got students: {0}".format(students))
        matched_students = set()
        for enrollment in StudentEnrollment.objects.filter(
            groupset=groupset, student__in=students
        ):
            matched_students.add(enrollment.student)
        logger.debug("matched students: {0}".format(students))
        size = len(matched_students)
        logger.debug("Matched students size: {0}".format(size))
        GroupSizeHint.objects.filter(group=group, method=method).delete()
        GroupSizeHint(group=group, size=size, method=method).save()
        logger.info("Size hint calculated")

    @staticmethod
    def size_from_enrollments(
        group, groupset, enrollment_types=[4, 26], excluded_students=[], method=None
    ):
        """
        Calculate size from enrollments. The subject and study and classyear are inferred from the group (on
        which actitivities it is, group short name). Then enrollments to the given groupset
        and study and classyear of the given type are considered. Method is
        "enrollments from #groupset for types #types".
        :param group: group object we are calculating size hint for.
        :param groupset: enrollments are gathered from here.
        :param enrollment_types: which types of enrollments to consider, defaults to [4, 26]. See ENROLLMENTTYPES.
        if enrollment_types is None, all enrollment types are considered.
        :param excluded_students: students to exclude. For instance students from exchange groups.
        :param method: method name. If not used it will be auto generated from enrollment_types and groupset
        :return: None
        """
        logger.info("Calculating size hints from enrollments")
        logger.debug("group: {0}".format(group))
        logger.debug("groupset: {0}".format(groupset))
        logger.debug("enrollment types: {0}".format(enrollment_types))
        if method is None:
            method = "enrollments from {0} for types {1}".format(
                groupset, enrollment_types
            )
        group_subjects = set()
        group_study_short_name = group.study
        try:
            classyear = int(group.classyear)
        except ValueError:
            classyear = 8
        logger.debug("group study: {0}".format(group_study_short_name))
        logger.debug("group classyear: {0}".format(classyear))
        for a in group.activities.all():
            group_subjects.add(a.activity.subject)
        logger.debug("group_subjects: {0}".format(group_subjects))
        base_enrollments = StudentEnrollment.objects.filter(
            groupset=groupset,
            subject__in=group_subjects,
        )
        logger.debug(f"Base size: {base_enrollments.count}")
        if group_study_short_name == "PAD":
            se = base_enrollments.filter(study__short_name="PAD")
            # se = base_enrollments.exclude(
            #    enrollment_type__in=[4, 26]
            # )
            pass
        else:
            se = base_enrollments.filter(
                study__short_name=group_study_short_name,
                classyear=classyear,
                enrollment_type__in=[4, 26],
            )
        if enrollment_types is not None and group_study_short_name != "PAD":
            se = se.filter(enrollment_type__in=enrollment_types)
        students = set()
        for e in se:
            students.add(e.student)
        students = students - set(excluded_students)
        size = len(students)
        logger.debug("students: {0}".format(students))
        logger.debug("size: {0}".format(size))
        GroupSizeHint.objects.filter(group=group, method=method).delete()
        GroupSizeHint(group=group, size=size, method=method).save()
        logger.info("Size hint calculated")


class Activity(timetable.models.Activity):
    subject = models.ForeignKey(
        "Subject", related_name="activities", on_delete=models.CASCADE
    )
    lecture_type = models.ForeignKey(
        "LectureType", related_name="activities", null=False, on_delete=models.CASCADE
    )

    @classmethod
    def from_timetable_activity(cls, timetable_activity):
        """
        Args:
            timetable_activity (timetable.models.Activity): The parent class activity.

        Returns:
            (friprosveta.models.Activity): The subclass activity.
        """
        return cls.objects.get(activity_ptr=timetable_activity)

    def id_string(self):
        return "{0}_{1}".format(self.name, "LJ")

    @property
    def studies(self):
        studies = []
        for group in self.groups.all():
            if group.study not in studies:
                studies.append(group.study)
        return studies

    def najave(self, timetable_set=None):
        """
        Return all najave for this activity for a given timetable set.
        :param timetable_set: if None, first timetable set for this timetable is used.
        :return: queryset if TeacherSubjectCycle entries.
        """
        if timetable_set is None:
            timetable_set = (
                self.activityset.timetable_set.first().timetable_sets.first()
            )
        return frinajave.models.TeacherSubjectCycles.objects.filter(
            timetable_set=timetable_set,
            subject_code=self.subject.code,
            lecture_type=self.lecture_type_id,
            cycles__gt=0,
        )

    def preetified_najave(self, timetable_set=None):
        najave = self.najave(timetable_set)
        ret = []
        for e in najave:
            teacher = Teacher.objects.get(code=e.teacher_code)
            subject = Subject.objects.get(code=e.subject_code)
            lecture_type = LectureType.objects.get(pk=e.lecture_type)
            instruction_type = dict(frinajave.models.INSTRUCTION_STYLE)[
                e.instruction_type
            ]
            ret.append((teacher, subject, lecture_type, instruction_type, e.cycles))
        return ret

    def najave_class_size(self, timetable_set):
        return sum(najava.number_of_students for najava in self.najave(timetable_set))

    def groups_class_size(self):
        return sum(group.size for group in self.groups.all())

    def cycles(self, teacher_code, lecture_type_id, timetable_set):
        entries = frinajave.models.TeacherSubjectCycles.objects.filter(
            timetable_set=timetable_set,
            subject_code=self.subject.code,
            lecture_type=lecture_type_id,
            teacher_code=teacher_code,
        )
        cycles = 0
        for entry in entries:
            cycles += entry.cycles
        return int(round(cycles))

    @property
    def nacini_izvajanja(self):
        nacini = set()
        for ar in self.realizations.all():
            ar1 = friprosveta.models.ActivityRealization.objects.get(pk=ar.id)
            nacini.add(ar1.tip_skupin)
        return list(nacini)

    def get_studis_izvajanja(self, year, najave=None):
        subject_izvajanja = self.subject.get_studis_izvajanja(year, najave)

    def create_realizations_from_najave(self, timetable_set=None, force=False):
        """
        Create realizations (empty) from najave. No previous realizations must exists.
        Only teachers are assigned to newly created objects.
        :param timetable_set: create realizations from najave for the given timetable set.
        If none the first timetable set that contains activityset for the current activity is used.
        :param force: delete previous realizations before creating new ones.
        :return: list of new realizations
        """
        logger.info("Creating realizations from najave for {0}".format(self))
        logger.debug("tt_set: {0}".format(timetable_set))
        logger.debug("force: {0}".format(force))

        if not force:
            assert self.realizations.count() == 0
        else:
            self.realizations.filter(activity__type=self.type).delete()
            logger.debug("Removed old realizations")

        if timetable_set is None:
            timetable_set = (
                self.activityset.timetable_set.first().timetable_sets.first()
            )
            logger.debug("Chaged timetable_set value to {0}".format(timetable_set))

        cycles = frinajave.models.TeacherSubjectCycles.realizations(
            self.subject.code, timetable_set, [self.lecture_type]
        )
        logger.debug("Got cycles {0}".format(cycles))
        for key, value in cycles.items():
            logger.debug("Processing entry {0}, {1}".format(key, value))
            lecture_type_short_name, instruction_style = key
            dict_key = lecture_type_short_name, instruction_style[1]
            d = dict(frinajave.models.ACTIVITY_TEACHERS_SIZE)
            intended_size = d[dict_key][1]
            logger.debug("Calculated intended size {0}".format(intended_size))
            for teachers_on_realization in value:
                teachers = []
                for teacher_code in teachers_on_realization:
                    for code in teacher_code.split(","):
                        try:
                            teacher = Teacher.objects.get(code=code)
                            teachers.append(teacher)
                        except Teacher.DoesNotExist as e:
                            logger.exception(
                                "Teacher with code {0} does not exists".format(code)
                            )
                            raise
                        except Teacher.MultipleObjectsReturned as e:
                            logger.exception(
                                "Multiple teachers with code {0}".format(code)
                            )
                            raise

                ar = ActivityRealization(
                    activity=self,
                    intended_size=intended_size,
                )
                ar.save()
                ar.teachers.add(*teachers)
                ar.save()
                self.teachers.add(*teachers)
                logger.debug("Add teachers {0}".format(teachers))
        logger.info("Created realizations from najave")


class Study(models.Model):
    def __str__(self):
        return self.short_name

    short_name = models.CharField(max_length=32)
    name = models.TextField()

    def enrolledStudents(self, timetable):
        return friprosveta.models.Student.objects.filter(
            enrolled_subjects__study=self,
            enrolled_subjects__groupset=timetable.groupset,
        ).distinct()

    def enrolledStudentsClassyear(self, timetable, classyear):
        return friprosveta.models.Student.objects.filter(
            enrolled_subjects__study=self,
            enrolled_subjects__groupset=timetable.groupset,
            enrolled_subjects__classyear=classyear,
        ).distinct()

    def subjects(self, timetable, classyear):
        return friprosveta.models.Subject.objects.filter(
            enrolled_students__study=self,
            enrolled_students__groupset=timetable.groupset,
            enrolled_students__classyear=classyear,
        ).distinct()


class ActivityRealization(timetable.models.ActivityRealization):
    class Meta:
        proxy = True

    @property
    def students(self):
        """
        Return the set of students enrolled on this realization.
        """
        return Student.objects.filter(groups__in=list(self.groups.all()))

    @property
    def tip_skupin(self):
        """Try to gues whether group is small or big.
        :return: entry in REALIZATIONSIZES
        """
        n = self.n_students
        d = {i[0]: i for i in REALIZATIONSIZES}
        n_teachers = self.teachers.count()
        if n < 24 and n_teachers == 1:
            return d["MAJHNE"]
        elif n >= 24 and n_teachers == 2:
            return d["ASISTENTA"]
        elif n >= 24:  # demonstratorjev ni nujno v bazi, ne bodo pisani
            return d["DEMONSTRATOR"]
        return d["DRUGO"]  # npr. 2 asistenta za majhno skupino.

    def assign_groups(self, up_to_size=None, mix_studies=False, add_pad=True):
        """
        Assign groups to this realization. Groups are taken from its activity. Fill it up to up_to_size.
        If up_to_size is not given it is filled up to intended_size property on the realization.
        If add_pad is true, always add students from PAD study.
        Unassigned means that:
        1) Group is listed in the activity.
        2) Group is not assigned to any realization from this activity.
        Some rules are respected:
        1) Is groups from some studies are already on the realizion, only groups belonging to the same
        studies are added.
        2) If no groups are assigned to the realization then only groups from one study are added. The
        study which has most unassigned groups is considered a candidate.
        3) Groups that are candidates are ordered by their group number and assigned untill no group can
        be assigned any longer.
        :param up_to_size: fill realization until this size is reached.
        :return: list of groups newly added to the realization.
        """
        studies_sorting_weight = {
            "BUN-RI": 1,
            "BVS-RI": 2,
            "BMA-RI": 3,
            "BDR-RI": 4,
            "BUN-RM": 5,
            "BUN-MM": 6,
            "BUN-UI": 7,
            "BMA-RM": 8,
            "BMA-MM": 9,
            "BMA-PRI": 10,
            "BMA-KO": 11,
        }
        if up_to_size is None:
            up_to_size = self.intended_size
        unassigned_groups = self.activity.groups.all()
        logger.debug("UG: {}".format(unassigned_groups))
        other_activity_realizations = self.activity.realizations.exclude(pk=self.id)
        unassigned_groups = list(
            unassigned_groups.exclude(realizations__in=other_activity_realizations)
        )
        logger.debug("UG: {}".format(unassigned_groups))
        if self.groups.exists():
            # Add only groups from studies already on realization
            mix_studies = True
            ok_studies = set([g.study for g in self.groups.all()])
            unassigned_groups = [g for g in unassigned_groups if g.study in ok_studies]
        # Order according to classyear and study (tuple). Inside order by group num
        d = defaultdict(list)
        for g in unassigned_groups:
            d[(g.classyear, g.study)].append(g)
        logger.debug("D: {}".format(d))
        for e in d:
            d[e] = sorted(d[e], key=attrgetter("groupnum"))
        # Now calculate available students for each entry in d
        # and sort it according to available students
        # In s there are tuples ((#classyear, #study), #available_size))
        s_pos = 0
        d_pos = 0
        s = sorted(
            [(e, sum(g.size for g in d[e])) for e in d], key=itemgetter(1), reverse=True
        )
        # Now sort according to the study sorting weight...
        s = sorted(
            [(e, sum(g.size for g in d[e])) for e in d],
            key=lambda e: (studies_sorting_weight.get(e[0][1], 100), e[0][0]),
        )
        logger.debug("Type: {}".format(self.activity.type))
        logger.debug("To add: {}".format(s))
        logger.debug("Size: {}".format(self.group_size))
        logger.debug("Up to size: {}".format(up_to_size))
        logger.debug("Spos: {}".format(s_pos))
        logger.debug("Len(s): {}".format(len(s)))

        while self.group_size < up_to_size and s_pos < len(s):
            available_size = up_to_size - self.group_size
            entry = s[s_pos]
            group = d[entry[0]][d_pos]
            logger.debug("Entry: {}".format(entry))
            logger.debug("Group: {}".format(entry))
            logger.debug("AS: {}".format(available_size))
            if group.size <= available_size:
                self.groups.add(group)
            d_pos += 1
            # Is no more groups from this study/classyear, move on
            if d_pos >= len(d[entry[0]]):
                # If we should not move to the next study stop
                if not mix_studies:
                    break
                s_pos += 1
                d_pos = 0


class Location(timetable.models.Location):
    class Meta:
        proxy = True

    @property
    def shortname(self):
        return self.name if len(self.name.split()) == 1 else self.name.split()[0]


class Teacher(timetable.models.Teacher):
    class Meta:
        proxy = True

    @property
    def subjects(self):
        return Subject.objects.filter(
            id__in=self.activities.values_list("subject", flat=True).distinct()
        )

    @property
    def owned_subjects(self):
        return self.my_subjects.filter(
            Q(subjectheadteachers__end__isnull=True)
            | Q(subjectheadteachers__end__lt=datetime.datetime.now())
        )

    @property
    def others_subjects(self):
        return self.subjects.exclude(
            Q(subject__heads__exact=self),
            Q(subject__subjectheadteachers__end__isnull=True)
            | Q(subject__subjectheadteachers__end__lt=datetime.datetime.now()),
        )

    @property
    def activities(self):
        return Activity.objects.filter(teachers__exact=self)

    @property
    def owned_activities(self):
        return Activity.objects.filter(
            Q(teachers__exact=self),
            Q(subject__heads__exact=self),
            Q(subject__subjectheadteachers__end__isnull=True)
            | Q(subject__subjectheadteachers__end__lt=datetime.datetime.now()),
        )

    @property
    def subordinate_activities(self):
        return Activity.objects.filter(
            Q(subject__heads__exact=self),
            Q(subject__subjectheadteachers__end__isnull=True)
            | Q(subject__subjectheadteachers__end__lt=datetime.datetime.now()),
        )

    @property
    def others_activities(self):
        return self.activities.exclude(
            Q(subject__heads__exact=self),
            Q(subject__subjectheadteachers__end__isnull=True)
            | Q(subject__subjectheadteachers__end__lt=datetime.datetime.now()),
        )

    def busy_hours(self, tt, levels=["CANT", "HATE"]):
        """
        When teacher is busy in a given timetable.
        Teacher is considered busy if:
        1) he is teaching.
        2) he has a time preference stating that he would rather not teach
        with weight more than the given weight.
        Weights have to be normalized first.
        Returns a set of tuples (hour,weight), weight ranges from 0 to 1.
        Weight 1: busy busy.
        Weight 0.5: relatively busy...
        """

        def add_busy_hours(busy_hours, start, duration, day, weight=1):
            start_index = timetable.models.WORKHOURS.index((start, start))
            for hour in timetable.models.WORKHOURS[
                start_index : start_index + duration
            ]:
                busy_hours[day].add((hour[0], weight))

        preferences = timetable.models.TeacherTimePreference.objects.filter(
            preferenceset=tt.preferenceset, level__in=levels, teacher=self
        )
        allocations = timetable.models.Allocation.objects.filter(
            timetable=tt, activityRealization__teachers=self
        )

        busy_hours = {day[0]: set() for day in timetable.models.WEEKDAYS}
        for allocation in allocations:
            add_busy_hours(
                busy_hours, allocation.start, allocation.duration, allocation.day
            )
        for preference in preferences:
            add_busy_hours(
                busy_hours,
                preference.start,
                preference.duration,
                preference.day,
                preference.adjustedWeight(),
            )
        return busy_hours

    def free_hours(self, tt, weight=0):
        busy = self.busy_hours(tt)
        free = {
            day[0]: set(list(zip(*timetable.models.WORKHOURS))[0])
            for day in timetable.models.WEEKDAYS
        }

        for day in busy:
            for (hour, busy_weight) in busy[day]:
                if busy_weight >= weight and hour in free[day]:
                    free[day].remove(hour)

        return free


class Student(models.Model):
    def __str__(self):
        return "{0} {1} ({2})".format(self.name, self.surname, self.studentId)

    name = models.CharField(max_length=128)
    surname = models.CharField(max_length=128)
    studentId = models.CharField(max_length=8, unique=True)
    groups = models.ManyToManyField(timetable.models.Group, related_name="students")
    follows = models.ManyToManyField(
        timetable.models.ActivityRealization, related_name="followers"
    )

    # Get study from student enrollments
    def study(self, timetable):
        studies = defaultdict(int)
        # for group in self.groups.all():
        #    studies[group.study] += 1
        for e in StudentEnrollment.objects.filter(
            student=self, groupset=timetable.groupset
        ):
            studies[e.study] += 1
        # Default study is "BUN-RI"
        (study, m) = ("BUN-RI", -1)
        for (s, v) in studies.items():
            if v > m:
                (study, m) = (s, v)
        return study.short_name

    def enrolledSubjects(self, timetable):
        """
        Return a list of enrolled subjects for a given timetable.
        """
        return friprosveta.models.Subject.objects.filter(
            enrolled_students__student=self,
            enrolled_students__groupset=timetable.groupset,
        ).distinct()

    def realizations(self, tt):
        """
        Return a list of the realizations the given student is attending.
        """
        return tt.realizations.filter(groups__students=self)

    def allocations(self, tt):
        """
        Return a list of the allocations the given student is attending.
        """
        return tt.allocations.filter(activityRealization__groups__students=self)

    def busy_hours(self, tt):
        """
        Returns a dict of form (day, hours) : [allocation list].
        """
        busy = defaultdict(list)
        for a in self.allocations(tt):
            for hour in a.hours:
                busy[(a.day, hour)].append(a)
        return busy

    def is_available(self, tt, allocation, busy_hours=None):
        if busy_hours is None:
            busy_hours = self.busy_hours(tt)
        return all(
            (allocation.day, hour) not in busy_hours for hour in allocation.hours
        )

    def overlaps(self, tt, busy_hours=None):
        """
        Return overlaps as a set of tuples (day, hour, overlapping_allocations).
        """
        if busy_hours is None:
            busy_hours = self.busy_hours(tt)
        overlaps = set()
        for key, allocations in busy_hours.items():
            if len(allocations) > 1:
                overlaps.add((*key, tuple(allocations)))
        return overlaps

    @classmethod
    def find_substitution(cls, tt, allocation_from, allocation_to, group_type):
        """
        Find all students on the given allocation that are contained in the
        groups which shortname contains the string group_type and are
        free at the time of the allocation allocation_to.
        """
        substitutions = set()
        realization = allocation_from.activityRealization
        groups = realization.groups.filter(short_name__contains=group_type)
        for group in groups:
            for student in group.students.all():
                if cls.is_available(student, tt, allocation_to):
                    substitutions.add(student)
        return substitutions

    def my_groups(self, allocation):
        """
        Return a QuerySet containing students's groups for the given allocation.
        """
        realization = allocation.activityRealization
        realization.groups.filter(students=self)

    @classmethod
    def from_user(cls, user):
        """Get a `Student` object from a `User`.

        Args:
            user (User): The user to fetch student data for.
        Returns:
            Student: Student object.
        Raises:
            Student.DoesNotExist: If there is no such student.
            IOError: If something goes wrong with the API.
        """
        # email is more correct than username, so use that
        email = user.username

        # this isn't really testable, but let's avoid overengineering for now
        if settings.STUDENT_MAPPER_PRODUCTION:
            # initialise if no cached values
            print("REAL")
            mapping = cache.get("cached_user_student_map")
            if mapping is None:
                s = Studenti()
                data = s.get_confirmed_enrollments(
                    datetime.datetime.utcnow().isoformat()[:10], unfinished=True
                )
                if not data:
                    raise IOError("Error getting api data.")
                mapping = {
                    a["upn"].strip(): a["vpisna_stevilka"].strip()
                    for a in data
                    if a["upn"] is not None
                }
                cache.set("cached_user_student_map", mapping)

            student_id = mapping.get(
                email, "this string is definitely not a student id"
            )

            return Student.objects.get(studentId=student_id)
        else:
            return Student.objects.get(
                name__iexact=user.first_name, surname__iexact=user.last_name
            )


class StudentEnrollment(models.Model):
    """
    Relate student with his subjects.
    """

    def __str__(self):
        return "{0}; {1} ({2}); {3} {4}".format(
            self.student, self.subject, self.subject.code, self.classyear, self.study
        )

    groupset = models.ForeignKey(
        timetable.models.GroupSet,
        related_name="enrolled_students",
        on_delete=models.CASCADE,
    )
    student = models.ForeignKey(
        Student, related_name="enrolled_subjects", on_delete=models.CASCADE
    )
    subject = models.ForeignKey(
        "Subject", related_name="enrolled_students", on_delete=models.CASCADE
    )
    study = models.ForeignKey(
        "Study",
        related_name="enrolled_students",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    classyear = models.IntegerField(default=0)
    enrollment_type = models.CharField(max_length=4, choices=ENROLMENTTYPES)
    regular_enrollment = models.BooleanField(default=True)
    source = models.CharField(max_length=64, null=True, choices=ENROLMENTSOURCES)


class Kaprica(models.Model):
    group = models.OneToOneField(
        timetable.models.Group, primary_key=True, on_delete=models.CASCADE
    )
    regular = models.BooleanField(default=True)


class Timetable(timetable.models.Timetable):
    class Meta:
        proxy = True

    @property
    def activities(self):
        return Activity.objects.filter(activityset__timetable=self).distinct()

    @property
    def teachers(self):
        return Teacher.objects.filter(
            activity_realizations__activity__activityset__timetable=self
        ).distinct()

    def teachers_type(self, type):
        return Teacher.objects.filter(
            activities__activityset__timetable=self, activities__type=type
        ).distinct()

    @property
    def subjects(self):
        return Subject.objects.filter(
            activities__activityset__timetable=self
        ).distinct()

    @property
    def students(self):
        """
        Return all students enrolled (based on enrollments to subjects).
        """
        return friprosveta.models.Student.objects.filter(
            enrolled_subjects__subject__in=self.subjects,
            enrolled_subjects__groupset=self.groupset,
        ).distinct()

    def startendcodes(self):
        return self.start, self.end, list(self.subjects.values_list("code", flat=True))


class LectureType(models.Model):
    """
    Represents a type of a lecture and its duration.
    """

    def __str__(self):
        return "{0} ({1})".format(self.short_name, self.duration)

    name = models.CharField(max_length=128, unique=True)
    short_name = models.CharField(max_length=4, unique=True)
    duration = models.IntegerField()


class Subject(models.Model):
    def __str__(self):
        return self.name

    code = models.CharField(max_length=16, blank=True, unique=True)
    name = models.CharField(max_length=256)
    heads = models.ManyToManyField(
        Teacher,
        through="SubjectHeadTeachers",
        symmetrical=False,
        related_name="subjects",
    )
    students = models.ManyToManyField(
        Student, through="StudentEnrollment", symmetrical=False, related_name="subjects"
    )
    managers = models.ManyToManyField(Teacher, related_name="managed_subjects")
    short_name = models.CharField(max_length=32, blank=True, default="")

    def get_studis_studies(self, year, najave, studij):
        """Return the list of tuples (classyear, study) for this subject."""
        studies = []
        for izvajanje, predmetnik in self.get_studis_predmetnik(year, studij, najave):
            studies.append(
                (
                    najave.get_classyear(predmetnik),
                    najave.get_study_short_name(predmetnik),
                )
            )
        return studies

    def make_short_name(self):
        """
        Create short_name from the long one.
        """
        if self.short_name == "":
            ignore = ["IN", "V", "Z", "S"]
            self.short_name = "".join(
                [
                    s[0]
                    for s in filter(
                        lambda s: s not in ignore, self.name.upper().split()
                    )
                ]
            )
            self.save()
        return self.short_name

    def studiesOnTimetables(self, timetables):
        # TODO: should I read this from Studij??
        studies = []
        for activity in self.activities.filter(
            type="P", activityset__timetable__in=timetables
        ):
            for study in activity.studies:
                if study not in studies:
                    studies.append(study)
        return studies

    def get_enrolled_students(self, timetable):
        """
        Return a Queryset of enrolled students for the given timetable.
        """
        return friprosveta.models.Student.objects.filter(
            enrolled_subjects__subject=self,
            enrolled_subjects__groupset=timetable.groupset,
        ).distinct()

    def enrolled_students_for_study(self, timetable, study):
        """
        Return a Queryset representing enrolled students on a given study
        for a given timetable.
        :param timetable: given timetable
        :param study: given study
        :return: Queryset of applicable students
        """
        return self.get_enrolled_students(timetable).filter(
            enrolled_subjects__study=study
        )

    def enrolled_students_study_classyear(self, timetable, study, classyear):
        return (
            self.enrolled_students_for_study(timetable, study)
            .filter(
                enrolled_subjects__classyear=classyear,
            )
            .distinct()
        )

    def unallocated_groups(self, type, timetable):
        """
        Get unallocated groups for activity of the given type in the given timetable.
        :param type:
        :param timetable:
        :return: a set of unallocated groups. Unallocated means it is not assigned
        to any realization or it is assgned to the realization without teachers.
        """
        group_set = set()
        for activity in self.activities.filter(
            type=type, activityset=timetable.activityset
        ):
            for group in activity.groups_without_realization(timetable.groupset):
                group_set.add(group)
            for group in activity.groups_on_realizations_without_teachers(
                timetable.groupset
            ):
                group_set.add(group)
        return group_set

    def number_of_unallocated_groups(self, type, timetable):
        group_set = self.unallocated_groups(type, timetable)
        return len(group_set)

    def number_of_unallocated_students(self, type, timetable):
        """
        How many students are there in not assigned groups.
        :param type:
        :param timetable:
        :return:
        """
        group_set = self.unallocated_groups(type, timetable)
        return sum((group.size for group in group_set))

    def cyclesForTeacher(self, teacher, type, tt):
        """
        Return the number of hours of given type for a given teacher for a given timetable.
        """
        return (
            tt.realizations.filter(
                activity__type=type, activity__activity__subject=self, teachers=teacher
            )
            .distinct()
            .count()
        )

    def teachers(self, timetable):
        """
        Return all teachers on realizations in the
        given timetable for the given subject.
        :param timetable: given timetable
        :return: a Queryset of teachers.
        """
        subject_activities = self.activities.filter(activityset=timetable.activityset)
        return friprosveta.models.Teacher.objects.filter(
            id__in=subject_activities.values_list("teachers", flat=True).distinct()
        )

    def allCycles(self, timetable, types):
        """
        Return the dictionary: teacher->[type,hours]] for given types.
        """
        teachers = self.teachers(timetable)
        ret = dict()
        for teacher in teachers:
            if teacher not in ret:
                ret[teacher] = []
            for type in types:
                teachercycles = self.cyclesForTeacher(teacher, type, timetable)
                if teachercycles > 0:
                    ret[teacher].append((type, teachercycles))
        return ret

    def id_string(self):
        return "{0}({1})".format(self.name, self.code)

    def get_studis_izvajanja(self, year, najave=None):
        """
        Get a list of izvajanja for this subject for the given year.
        :param year: the year in which winter semester is started. For year 2017/2018 it is
        2017.
        :param najave: if najave is not None it is used. Object from friprosveta.studis
        :return: data returned from studis
        """
        if najave is None:
            from friprosveta.studis import Najave

            najave = Najave(year)
        return [
            e for e in najave.get_izvajanja() if e["sifra_predmeta"] == str(self.code)
        ]

    def get_studis_predmetnik(self, year, studij=None, najave=None):
        """
        Get a tuple (izvajanje, predmetnik) for every izvajanje of this subject in the given year.
        The data is read from Studis.
        :param year:
        :return: a list of tuples (izvajanje, predmetnik) for the given subject/year combination.
        """
        if najave is None:
            from friprosveta.studis import Najave

            najave = Najave(year)
        if studij is None:
            from friprosveta.studis import Studij

            studij = Studij(year)
        studijsko_drevo = studij.get_studijsko_drevo()
        izvajanja = self.get_studis_izvajanja(year, najave=najave)
        return [
            (izvajanje, najave.get_predmetnik(izvajanje, studijsko_drevo))
            for izvajanje in izvajanja
        ]

    def update_or_create_subgroups_from_hints(
        self, activityset, methods, strategy_name, empty_groups=False, groups=None
    ):
        """
        Create or update subgroups for lab work (LV and AV) from groups on lectures (considered top groups).
        :param activityset: fetch the activities from the given activity set.
        :param method: use the given method string for reading group size hints.
        :param strategy_name: how to calculate group size. See GroupSizeHint.strategy for detail explanation.
        :param empty_groups: is true, subgroups is size 0 are also created.
        :param groups: names of top-level groups for which to compute subgroups for. If it is None (default)
        then all top level groups for the subject are processed.

        Useful for assigning activities on the correct day for students from other faculties
        when their number is not known in advance.
        :return:
        """

        def split_into_sizes(entire_size, sizes):
            """
            Split entire_size into chunks, each of size in sizes. Use as big chunks as possible.
            :param entire_size:
            :param sizes:
            :return: array of sizes.
            """
            sizes.append(1)  # Make sure every split is successful
            pos = 0
            splits = []
            remaining_size = entire_size
            while remaining_size > 0:
                if sizes[pos] <= remaining_size:
                    remaining_size -= sizes[pos]
                    splits.append(sizes[pos])
                else:
                    pos += 1
            return splits

        def create_groups(sizes, parent_group, type):
            """
            Create subgroups of parent group with sizes from sizes list of type type.
            :param sizes: list of sizes of groups.
            :param parent_group: name, short_name and parent and groupset are taken from this one.
            :param type: type of activity this group is on. Is used when constructing short_name and name.
            :return: list of created groups.
            """
            groups = []
            base_name = parent_group.name
            base_short_name = parent_group.short_name
            for i in range(1, len(sizes) + 1):
                size = sizes[i - 1]
                name = "{0}, {1}, skupina {2}".format(base_name, type, i)
                short_name = "{0}_{2}_{1:02d}".format(base_short_name, i, type)
                g = Group.objects.update_or_create(
                    short_name=short_name,
                    parent=parent_group,
                    groupset=parent_group.groupset,
                    defaults={"size": size, "name": name},
                )[0]
                groups.append(g)
            return groups

        """Create necessary groups for subject from hints"""
        top_groups = (
            self.activities.filter(activityset=activityset, type="P")
            .first()
            .groups.all()
        )
        if groups is None:
            groups = top_groups
        else:
            top_groups = [g for g in top_groups if g in groups]
        types = set(
            self.activities.filter(activityset=activityset)
            .exclude(type="P")
            .values_list("type", flat=True)
        )
        sizes = {"LV": [15, 3, 2, 1], "AV": [30, 5, 3, 2, 1]}
        for group in top_groups:
            for type in types:
                # set all sizes to 0, so that additional (not needed) groups will have size set to 0
                # Others will be set by the create_groups method
                activities = self.activities.filter(activityset=activityset, type=type)
                for activity in activities:
                    for tmp in activity.groups.filter(
                        short_name__startswith=group.short_name
                    ):
                        tmp.size = 0
                        tmp.save()
                gsh_size = GroupSizeHint.strategy(group, methods, strategy_name)
                if gsh_size is None:
                    ...
                if "PAD" in group.short_name:
                    splits = split_into_sizes(gsh_size, [3, 2, 1])
                else:
                    splits = split_into_sizes(gsh_size, sizes[type])
                # Create empty group
                if gsh_size == 0 and empty_groups:
                    splits.append(0)
                groups = create_groups(splits, group, type)
                for activity in activities:
                    activity.groups.add(*groups)

    def create_obligatory_top_level_groups_from_studis_predmetnik(
        self, year, tt, studij=None, najave=None
    ):
        def group_name(predmetnik):
            """Return tuple (name, short_name)."""
            assert len(predmetnik) == 5, "Predmetnik not complete " + str(predmetnik)
            short_name = "{0}_{1}-{2}".format(
                predmetnik[5]["short_title"],
                predmetnik[1]["short_title"],
                predmetnik[2]["short_title"],
            )
            name = "{0}, {1}, {2}".format(
                predmetnik[5]["title"]["sl"],
                predmetnik[2]["title"]["sl"],
                predmetnik[1]["title"]["sl"],
            )
            # Smer
            if predmetnik[3]["short_title"] is not None:
                short_name += f"-{predmetnik[3]['short_title']}"
                name += f", smer {predmetnik[3]['title']['sl']}"
            return (short_name, name)

        def get_study(predmetnik):
            """
            Return friprosveta.models.Study object from
            STUDIS predmetnik entry.
            :param predmetnik: given predmetnik entry.
            :return: corresponding study.
            """
            logger.debug("Entering get_study")
            study_short_name = "{0}-{1}".format(
                predmetnik[1]["short_title"],
                predmetnik[2]["short_title"],
            )
            logger.debug("Study short name: {}".format(study_short_name))
            logger.debug("Exiting get_study")
            return Study.objects.get(short_name=study_short_name)

        #            return Study.objects.get(short_name=study_short_name)

        predmetnik = self.get_studis_predmetnik(year, studij=studij, najave=najave)
        obligatory_predmetnik = [e for e in predmetnik if e[0]["obvezen"]]
        for izvajanje, predmetnik in obligatory_predmetnik:
            sname, name = group_name(predmetnik)
            study = get_study(predmetnik)
            group_size = self.enrolled_students_for_study(tt, study).count()
            logger.debug(
                "Obligatory group sname, name, study: {} ; {} ; {}".format(
                    sname, name, study
                )
            )
            g, created = Group.objects.update_or_create(
                name=name,
                short_name=sname,
                parent=None,
                groupset=tt.groupset,
                defaults={"size": group_size},
            )
            for activity in tt.activities.filter(type="P", subject=self):
                activity.groups.add(g)

    def create_non_obligatory_top_level_groups_from_studis_predmetnik(
        self, year, tt, studij=None, najave=None
    ):
        logger.info(
            "Entering create_non_obligatory_top_level_groups_from_studis_predmetnik"
        )

        def group_name(predmetnik):
            """Return tuple (name, short_name)."""
            logger.debug("Entering group name")
            logger.debug("Predmetnik len: {}".format(len(predmetnik)))
            logger.debug("Test")
            logger.debug(predmetnik)
            assert len(predmetnik) == 5, "Predmetnik not complete " + str(predmetnik)
            short_name = "{0}_{1}-{2}".format(
                predmetnik[5]["short_title"],
                predmetnik[1]["short_title"],
                predmetnik[2]["short_title"],
            )
            name = "{0}, {1}, {2}".format(
                predmetnik[5]["title"]["sl"],
                predmetnik[2]["title"]["sl"],
                predmetnik[1]["title"]["sl"],
            )
            # Smer
            if predmetnik[3]["short_title"] is not None:
                short_name += f"-{predmetnik[3]['short_title']}"
                name += f", smer {predmetnik[3]['title']['sl']}"

            return short_name, name

        groupset = tt.groupset
        predmetnik = self.get_studis_predmetnik(year, studij=studij, najave=najave)
        logger.debug("Got predmetnik: {}".format(predmetnik))
        lecture_activities = tt.activities.filter(type="P", subject=self)
        for e, predmetnik in [e for e in predmetnik if not e[0]["obvezen"]]:
            logger.debug("Processing {}".format(e))
            try:
                sname, name = group_name(predmetnik)
                logger.debug("SN: {}, N: {}".format(sname, name))
            except Exception as e:
                logger.debug("Failed to get group name, predmetnik is not complete")
                continue
            parent_group, created = Group.objects.get_or_create(
                name=name,
                short_name=sname,
                parent=None,
                groupset=groupset,
                defaults={"size": 0},
            )
            logger.debug("{} {}".format(parent_group, created))
            append = self.short_name
            if append.find("(") > -1:
                append = append[: append.find("(")]
            sname += "_{0}({1})".format(append, self.code)
            name = "{0}, {1}".format(name, self.name)
            logger.debug("GSN: {}, GN: {}".format(sname, name))
            g, created = Group.objects.get_or_create(
                name=name,
                short_name=sname,
                parent=parent_group,
                groupset=groupset,
                defaults={"size": 0},
            )
            logger.debug("{}, {}".format(g, created))
            for activity in lecture_activities:
                logger.debug("Adding to activity {}".format(activity))
                activity.groups.add(g)
        padalci_top_level, created = Group.objects.get_or_create(
            name="Vsi padalci",
            short_name="VSI_PADALCI",
            parent=None,
            groupset=groupset,
            defaults={"size": 0},
        )
        padalci, created = Group.objects.get_or_create(
            name="{} padalci".format(self.code),
            short_name="{}_PAD".format(self.code),
            parent=padalci_top_level,
            groupset=groupset,
            defaults={"size": 0},
        )

        logger.debug(
            "Got top level padalci group: {}, created: {}".format(
                padalci_top_level, created
            )
        )
        for activity in lecture_activities:
            activity.groups.add(padalci)
        logger.info(
            "Exiting create_non_obligatory_top_level_groups_from_studis_predmetnik"
        )

    def create_top_level_groups_from_studis_predmetnik(
        self, year, tt, studij=None, najave=None
    ):
        self.create_obligatory_top_level_groups_from_studis_predmetnik(
            year, tt, studij=studij, najave=najave
        )
        self.create_non_obligatory_top_level_groups_from_studis_predmetnik(
            year, tt, studij=studij, najave=najave
        )

    def is_obligatory(self, year, studij=None, najave=None):
        """Is thi subject obligatory on some study for the given year?"""
        predmetnik = self.get_studis_predmetnik(year, studij=studij, najave=najave)
        return len([e for e in predmetnik if e[0]["obvezen"]]) > 0


class SubjectHeadTeachers(models.Model):
    def __str__(self):
        sd = None
        ed = None
        if self.start is not None:
            sd = self.start.date()
        if self.end is not None:
            ed = self.end.date()
        return "{} - {} - ({}-{})".format(self.teacher, self.subject, sd, ed)

    start = models.DateTimeField(blank=False, null=False)
    end = models.DateTimeField(blank=True, null=True)
    subject = models.ForeignKey("Subject", on_delete=models.CASCADE)
    teacher = models.ForeignKey("Teacher", on_delete=models.CASCADE)


class Cathedra(models.Model):
    def __unicode__(self):
        return "{0}".format(self.name)

    name = models.CharField(max_length=256)
    heads = models.ManyToManyField(
        timetable.models.Teacher, related_name="head_of_cathedras"
    )
    najave_deputies = models.ManyToManyField(
        timetable.models.Teacher, related_name="cathedras_handled", blank=True
    )
    members = models.ManyToManyField(
        timetable.models.Teacher, related_name="cathedras", blank=True
    )
