# -*- coding: utf-8 -*-

from itertools import combinations
from collections import defaultdict
from django.db import models
from timetable.models import TimetableSet
from friprosveta.models import LectureType

INSTRUCTION_STYLE = (
    (1, 'Enojni'),
    (2, 'Dva asistenta'),
    (3, 'Z demonstratorjem'),
)

# When no instruction style is given use the default one
DEFAULT_INSTRUCTION_STYLE = 1

# How many teachers and students per activity type / instruction style.
# The number 0 stands for infinite.
ACTIVITY_TEACHERS_SIZE = {
                ('AV', 'Enojni'): (1, 30),
                ('LV', 'Enojni'): (1, 18),
                ('LV', 'Dva asistenta'): (2, 30),
                ('LV', 'Z demonstratorjem'): (1, 30),
                ('P', 'Enojni'): (0, 0)}


class TeacherSubjectCycles(models.Model):
    """
    How many cycles are allocated for a given teacher for a given subject
    for a given type in the given timetable.
    """
    def __str__(self):
        return ("Id: {5}, teacher: {0}, subject: {1}, lecture type: {2}, instruction type: {6}"
                "cycles {4}, timetable_set: {3}".format(
                    self.teacher_code,
                    self.subject_code,
                    self.lecture_type,
                    self.timetable_set,
                    self.cycles, self.id, self.instruction_type))

    teacher_code = models.CharField(max_length=16, blank=False)
    subject_code = models.CharField(max_length=16, blank=False)
    timetable_set = models.ForeignKey(TimetableSet)
    instruction_type = models.IntegerField(choices=INSTRUCTION_STYLE,
                                           null=True)
    lecture_type = models.IntegerField()
    cycles = models.DecimalField(max_digits=18,
                                 decimal_places=3,
                                 default=0.000)
    comment = models.TextField(blank=True)

    @property
    def number_of_students(self):
        """
        Return the number of students on this entry.
        :return: numbber of students for this najave entry.
        """
        types = dict(INSTRUCTION_STYLE)
        lt = LectureType.objects.get(pk=self.lecture_type)
        key = (lt.short_name, types[self.instruction_type])
        size = ACTIVITY_TEACHERS_SIZE[key][1]
        # When two teachers are teaching, then count only half size
        # since there will be two entries in najave, one for each
        # teacher.
        # TODO: hardcoded value for instruction type
        half = self.instruction_type == 2
        ret = size * self.cycles
        if half:
            ret /= 2
        return round(ret)

    @staticmethod
    def group_teachers(teacher_cycles, teachers_in_group_num):
        """Teacher_cycles is a list of entries [teacher, cycles].
        Num_teachers is a number of teachers per group.
        Return a list of lists of length num_teachers, each inner list
        representing a group of teachers. The teachers are grouped so
        that every appears on the right number of cycles.
        """
        def sort_cycles(cycles):
            """
            Sort teacher_cycles list by cycles (not ascending).
            :param cycles: list of lists of type [teacher, cycles]
            :return: sorted list of lists.
            """
            return sorted(cycles, key=lambda cycle: -cycle[1])

        cycles_sum = sum([cycle[1] for cycle in teacher_cycles])
        assert cycles_sum > 0, "There should be at least one cycle"
        assert cycles_sum % 1 == 0, "Cycles should sum into integer"
        teachers_groups = []
        # Sort teachers by the number of cycles they have to teach
        teacher_cycles = sort_cycles(teacher_cycles)
        while len(teacher_cycles) >= teachers_in_group_num:
            teachers_in_group = teacher_cycles[:teachers_in_group_num]
            teachers_groups.append([teacher[0] for teacher in teachers_in_group])
            for entry in teachers_in_group:
                entry[1] -= 1
                if entry[1] == 0:
                    teacher_cycles.remove(entry)
            teacher_cycles = sort_cycles(teacher_cycles)
        assert len(teacher_cycles) == 0, "Unable to assign teachers to realizations"
        return teachers_groups

    @staticmethod
    def projected_class_size(subject_code, timetable_set):
        instruction_styles_dict = dict(INSTRUCTION_STYLE)
        lab_type_short_names = ['AV', 'LV']
        lab_types = LectureType.objects.filter(short_name__in=lab_type_short_names)
        lab_type_ids = [lab_type.id for lab_type in lab_types]

        ret = defaultdict(int)
        for cycle in TeacherSubjectCycles.objects.filter(
                timetable_set=timetable_set,
                subject_code=subject_code,
                cycles__gt=0,
                lecture_type__in=lab_type_ids):
            lt = LectureType.objects.get(id=cycle.lecture_type)
            i_style = instruction_styles_dict[cycle.instruction_type]
            class_size = ACTIVITY_TEACHERS_SIZE[(lt.short_name, i_style)][1]
            ret[lt.short_name] += class_size * cycle.cycles

        if not ret.values():
            return 0
        return min([int(size) for size in ret.values()])

    @staticmethod
    def group_to_integer_cycles(teacher_cycles):
        """Teacher_cycles is a list of entries [teacher_code, cycles].
        Sometimes they are not integers but they always sum into one. 
        Group them into integer cycles (merge two teachers if necessary).
        """
        non_integer_teacher_cycles = []
        integer_teacher_cycles = []
        for tc in teacher_cycles:
            integer, decimal = int(tc[1]), tc[1]%1
            if decimal:
                if integer > 0:
                    integer_teacher_cycles.append([tc[0], integer])
                non_integer_teacher_cycles.append([tc[0], decimal])
            else:
                integer_teacher_cycles.append(tc)
        assert sum([c for t,c in non_integer_teacher_cycles]) % 1 == 0, "Non-integer parts should sum into integer"
        while non_integer_teacher_cycles:
            for length in range(2, len(non_integer_teacher_cycles)+1):
                for comb in combinations(non_integer_teacher_cycles, length):
                    # If this combination sums into integer cycle merge appropriate teachers
                    s = sum([c for _, c in comb])
                    if s % 1 == 0:
                        merged = ",".join([t for t,c in comb])
                        integer_teacher_cycles.append([merged, int(s)])
                        for e in comb:
                            non_integer_teacher_cycles.remove(e)
                        break
        return integer_teacher_cycles

    @staticmethod
    def realizations(subject_code, timetable_set, lecture_types=None):
        """
        Generate realizations for the given subject and timetable set.
        :param subject_code: given subject.
        :param timetable_set: given timetable set.
        :param lecture_types: array of LectureTypes. If none all are considered.
        :return: dictionary with key tuple (#lecture_type_short_name, #instruction_type)
        and values list of lists, each inner list represents teachers on one
        realization. Teachers are given as a string of comma separated teacher codes.
        """
        najave = TeacherSubjectCycles.objects.filter(
            timetable_set=timetable_set,
            subject_code=subject_code,
            cycles__gt=0)
        if lecture_types is not None:
            lecture_types_ids = [e.id for e in lecture_types]
            najave = najave.filter(lecture_type__in=lecture_types_ids)
        ret = dict()
        for lecture_type in LectureType.objects.all():
            for instruction_style in INSTRUCTION_STYLE:
                if (lecture_type.short_name, instruction_style[1]) not in ACTIVITY_TEACHERS_SIZE:
                    continue
                teachers_per_group_num, _ = ACTIVITY_TEACHERS_SIZE[(lecture_type.short_name, instruction_style[1])]
                rs = najave.filter(lecture_type=lecture_type.id, instruction_type=instruction_style[0])
                # Do nothing if queryset is empty
                if not rs:
                    continue
                # Make all integer cycles integer type (it is decimal)
                for r in rs:
                    if r.cycles % 1 == 0:
                        r.cycles = int(r.cycles)
                if teachers_per_group_num == 0:
                    # Infinite teachers, one cycle
                    assert sum([r.cycles for r in rs]) == 1, ("Percentages should sum into one for subject {0}, "
                                                             "lecture_type {1}, instruction style {2}".format(subject_code, lecture_type, instruction_style))
                    # All teachers will be grouped into one big entry, since cycles are summed into 1
                    teachers_per_group_num = 1
                entries = [[r.teacher_code, r.cycles] for r in rs]
                grouped_entries = TeacherSubjectCycles.group_to_integer_cycles(entries)

                groups = TeacherSubjectCycles.group_teachers(grouped_entries, teachers_per_group_num)
                ret[(lecture_type.short_name, instruction_style)] = groups
        return ret
