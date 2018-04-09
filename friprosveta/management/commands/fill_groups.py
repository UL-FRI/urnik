from django.core.management.base import BaseCommand
from django.db import transaction

import friprosveta
import friprosveta.models as fm


class Command(BaseCommand):
    """
    Put students into groups for a given timetable.
    """

    help = """Usage: fill_groups [--subject=subject_code] timetable_slug [write_to_db, default False] [unenroll_first, default False]
Example: fill_groups "FRI 2013/2014, zimski semester" True"""

    def add_arguments(self, parser):
        parser.add_argument(
            'timetable_slug', nargs=1)
        parser.add_argument(
            'write_to_db', nargs='?',
            type=bool, default=False)
        parser.add_argument(
            'unenroll_first', nargs='?',
            type=bool, default=False)
        parser.add_argument(
            '--subject', nargs=1,
            dest='subject_code',
            help='Fill groups for the given subject only.')

    def handle(self, *args, **options):
        WRITE_TO_DB = options['write_to_db']
        print(WRITE_TO_DB)
        UNENROLL_FIRST = options['unenroll_first']
        tt = fm.Timetable.objects.get(slug=options['timetable_slug'][0])

        subjects = tt.subjects.all()
        if "subject_code" in options and options['subject_code'] != None:
            print(options["subject_code"][0])
            subjects = tt.subjects.filter(code=options["subject_code"][0])
        self.stdout.write(str(subjects))
        self.fill_groups_by_size(tt, subjects, WRITE_TO_DB, UNENROLL_FIRST)
        self.print_group_surnames(tt)

    @transaction.atomic
    def fill_groups_by_size(self, tt, subjects, write_to_db=False, unenroll_first=False):
        # study = fm.Study.objects.get(short_name=group.study)
        # students = study.enrolledStudentsClassyear(tt, int(group.classyear)).order_by("surname", "name").all()
        # group.students.clear()
        # for s in students:
        #    group.students.add(s)
        # group.size = len(students)
        # group.save()
        for subject in subjects.all():
            groups_by_activitytype = dict()
            self.stdout.write("{} {}".format(subject.short_name, subject.code))
            debug_group_dict = dict()
            foo_group_list = list()
            for activity in subject.activities.filter(activityset=tt.activityset):
                #    print "  ", activity.short_name
                for group in activity.groups.filter(groupset=tt.groupset).distinct():
                    #        print "  ->", group.short_name
                    dy = groups_by_activitytype.get(activity.type, {})
                    groups_by_activitytype[activity.type] = dy  # get a reference to groups by year
                    ds = dy.get(group.classyear, {})
                    dy[group.classyear] = ds  # get a reference to groups by study
                    l = ds.get(group.study, [])
                    ds[group.study] = l
                    debugTuple = (group.short_name, activity.type, group.classyear, group.study)
                    if group in l:
                        foo_group_list.append(debugTuple)
                    else:
                        l.append(group)
                    deblist = debug_group_dict.get(debugTuple, [])
                    deblist.append((activity, group))
                    debug_group_dict[debugTuple] = deblist
            for fg in foo_group_list:
                self.stderr.write("Skupina {0} je vsaj dvakrat na {1} {2} {3}".format(*fg))
                for i in debug_group_dict[fg]:
                    self.stderr.write("    {} {} {} {}".format(i[0].id, i[0].short_name, i[1].id, i[1].short_name))
            # enroll "normal" students
            normal_enrollment_types = [4, 26]
            subject_enrollments = friprosveta.models.StudentEnrollment.objects.filter(
                subject=subject,
                groupset=tt.groupset)
            normal_enrollments = subject_enrollments.filter(enrollment_type__in=normal_enrollment_types)
            extra_enrollments = subject_enrollments.exclude(enrollment_type__in=normal_enrollment_types)
            # self.stderr.write("{} extra:{}".format(subject.code, extra_enrollments.count()))
            for t, groups_by_year in groups_by_activitytype.items():
                self.stdout.write(t)
                for classyear, groups_by_study in groups_by_year.items():
                    self.stdout.write("  " + str(classyear))
                    for study_name, groups in groups_by_study.items():
                        self.stdout.write("    " + str(study_name))
                        try:
                            study = fm.Study.objects.get(short_name=study_name)
                            if study_name == 'PAD':
                                students = set(extra_enrollments.values_list('student', flat=True))
                            else:
                                students = set(normal_enrollments.filter(
                                    study=study, classyear=int(classyear)
                                ).values_list('student', flat=True))
                        except Exception as e:
                            self.stderr.write(
                                "Problem finding students for {0}-{1}: {2}".format(classyear, study_name, e))
                            students = set()
                        # students now contains all the students for this type of groups
                        self.stdout.write("        {}".format(students))
                        groups.sort(key=str)
                        former_students = set()
                        new_students = set()
                        current_students = set()
                        for group in groups:
                            if unenroll_first:
                                former_students = former_students + set(group.students.all())
                            else:
                                g_set = set(group.students.values_list('id', flat=True))
                                current_students = current_students.union(g_set.intersection(students))
                                former_students = former_students.union(g_set.difference(students))
                        new_students = students - current_students
                        # former_students should be removed from the groups.
                        # new_students should be added to some group.
                        i_s = 0
                        check_sum = 0
                        new_students = fm.Student.objects.filter(id__in=new_students).order_by('surname', 'name')
                        former_students = fm.Student.objects.filter(id__in=former_students).order_by('surname', 'name')
                        # new_students = sorted(new_students, key=lambda x: (x.surname, x.name))
                        print("NEW:", new_students, "DESIRED:", students, "CURRENT:", current_students, "FORMER:",
                              former_students)
                        for group in groups:
                            group_students = list(group.students.all())
                            for student in group_students:
                                if student in former_students:
                                    if write_to_db:
                                        group.students.remove(student)
                            i_g = group.students.count()
                            while i_g < group.size and i_s < len(new_students):
                                if write_to_db:
                                    group.students.add(new_students[i_s])
                                    group.students.add(new_students[i_s])
                                i_s += 1
                                i_g += 1
                            self.stdout.write("       --{} {} {} {} {}".format(
                                group.short_name, i_s, i_g, group.size, group.id))
                            check_sum += group.size
                        if len(students) != check_sum:
                            self.stderr.write("Wrong group size: {} {} ({}){} {} known:{} expected:{}".format(
                                classyear, study_name, subject.code, subject, t, len(students), check_sum))
                            if len(students) > check_sum:
                                self.stderr.write("    groups too small")
                            else:
                                self.stderr.write("    groups too large")
                            for group in groups:
                                self.stderr.write("    {}: {}".format(group.short_name, group.size))
                        # assert len(students) == check_sum

    def print_group_surnames(self, tt):
        l = []
        for group in tt.groupset.groups.all():
            s = list(group.students.order_by("surname", "name").all())
            if len(s) > 0:
                #    print "    ", s[0].surname[:5], s[-1].surname[:5]
                l.append((
                    str(group).split()[0], "" + s[0].surname + " " + s[0].name, s[-1].surname + " " + s[-1].name,
                    len(s), group.size))
            else:
                l.append((str(group).split()[0], "-", "-", 0, group.size))
        d = {}
        l.sort()
        last_name = l[0][0]
        d[last_name] = (l[0][1], 1, l[0][2], 1, l[0][3], l[0][4])
        for i, (short_name, s1, s2, n, gn) in enumerate(l[1:]):
            s1_, l1_, s2_, l2_, n_, gn_ = d[last_name]
            firstdiff = 0
            while firstdiff + 1 < min(len(s2_), len(s1)) and s2_[firstdiff] == s1[firstdiff]:
                firstdiff += 1
            d[short_name] = (s1, firstdiff + 1, s2, firstdiff + 1, n, gn)
            d[last_name] = (s1_, l1_, s2_, firstdiff + 1, n_, gn_)
            last_name = short_name
        s1_, l1_, s2_, l2_, n_, gn_ = d[last_name]
        d[last_name] = (s1_, l1_, s2_, 1, n_, gn_)
        for k in sorted(d):
            s1, l1, s2, l2, n, gn = d[k]
            self.stdout.write("{0}: {1} .. {2} ({3} - {4})".format(k, s1[:l1], s2[:l2], n, gn))
