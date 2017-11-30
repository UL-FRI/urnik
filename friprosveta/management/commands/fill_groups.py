'''
Created on 10. jan. 2013

@author: polz
'''

from django.core.management.base import BaseCommand
import friprosveta.models as fm
import friprosveta
from collections import defaultdict


class Command(BaseCommand):
    """
    Put students into groups for a given timetable.
    """

    help = """Usage: fill_groups [--subject=subject_code] timetable_slug [write_to_db, default False]
Example: fill_groups "FRI 2013/2014, zimski semester" True"""

    def add_arguments(self, parser):
        parser.add_argument(
            'timetable_slug', nargs=1)
        parser.add_argument(
            'write_to_db', nargs='?',
            type=bool, default=False)
        parser.add_argument(
            '--subject', nargs=1,
            dest='subject_code',
            help='Fill groups for the given subject only.')

    def handle(self, *args, **options):
        WRITE_TO_DB = options['write_to_db']
        tt = fm.Timetable.objects.get(slug=options['timetable_slug'][0])
<<<<<<< HEAD
        subjects = tt.subjects.all()
        if "subject_code" in options and options['subject_code'] != None:
            subjects = tt.subjects.filter(code=options["subject_code"])
        # self.stdout.write(str(subjects))
=======
        
        subjects = tt.subjects.all() 
        if "subject_code" in options and options['subject_code']!=None:
            subjects = tt.subjects.filter(code=options["subject_code"][0]) 
        self.stdout.write(str(subjects))
>>>>>>> 41401e0709ce05bdbcb597a7f122453c55e6e25c
        self.fillGroupsBySize(tt, subjects, WRITE_TO_DB)
        self.printGroupSurnames(tt)

    def fillGroupsBySize(self, tt, subjects, write_to_db=False, clear=False):
        for subject in subjects.all():
<<<<<<< HEAD
            groups_by_activitytype = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
=======
            print("Processing {}".format(subject))
            groups_by_activitytype = dict()
>>>>>>> 41401e0709ce05bdbcb597a7f122453c55e6e25c
            self.stdout.write("{} {}".format(subject.shortName, subject.code))
            debugGroupDict = dict()
            fooGroupList = list()
            existing_students = defaultdict(set)
            for activity in subject.activities.filter(activityset=tt.activityset):
                for group in activity.groups.filter(groupset=tt.groupset).distinct():
                    l = groups_by_activitytype[activity.type][group.classyear][group.study]
                    debugTuple = (group.shortName, activity.type, group.classyear, group.study)
                    if group in l:
                        fooGroupList.append(debugTuple)
                    else:
                        l.append(group)
                        for student in group.students.all():
                            if student in existing_students[activity.type]:
                                self.stderr.write("Student {0} je v vec skupinah {1} pri {2}".format(
                                    student, activity.type, subject))
                            existing_students[activity.type].add(student)
                    deblist = debugGroupDict.get(debugTuple, [])
                    deblist.append((activity, group))
                    debugGroupDict[debugTuple] = deblist
            for fg in fooGroupList:
                self.stderr.write("Skupina {0} je vsaj dvakrat na {1} {2} {3}".format(*fg))
                for i in debugGroupDict[fg]:
                    self.stderr.write("    {} {} {} {}".format(
                        i[0].id, i[0].shortName, i[1].id, i[1].shortName))
            # enroll "normal" students
            normal_enrollment_types = [4, 26]
            subject_enrollments = fm.StudentEnrollment.objects.filter(
                subject=subject,
                groupset=tt.groupset)
            expected_students = set([fm.Student.objects.get(id=i) for i in
                subject_enrollments.values_list('student_id', flat=True)])
            normal_enrollments = subject_enrollments.filter(
                enrollment_type__in=normal_enrollment_types)
            extra_enrollments = subject_enrollments.exclude(
                enrollment_type__in=normal_enrollment_types)
            extra_students = set([fm.Student.objects.get(id=i) for i in
                extra_enrollments.values_list('student_id', flat=True)])
            # self.stderr.write("{} extra:{}".format(subject.code, extra_enrollments.count()))
            for t, groups_by_year in groups_by_activitytype.items():
                self.stdout.write(t)
                students_to_remove = existing_students[t] - expected_students
                self.stdout.write("        to remove:{}".format(students_to_remove))
                for classyear, groups_by_study in groups_by_year.items():
                    self.stdout.write("  "+str(classyear))
                    for study_name, groups in groups_by_study.items():
                        self.stdout.write("    "+str(study_name))
                        try:
                            study = fm.Study.objects.get(shortName=study_name)
                            if study_name == 'PAD':
                                new_students = extra_students.copy()
                            else:
                                new_students = set()
                                for student_id in normal_enrollments.filter(
                                            study=study, classyear=int(classyear)
                                        ).values_list('student_id', flat=True):
                                    new_students.add(fm.Student.objects.get(id=student_id))
                            n_expected = len(new_students)
                            new_students -= existing_students[activity.type]
                            new_students = list(new_students)
                        except Exception as e:
                            self.stderr.write(u"Problem finding students for {0}-{1}: {2}".format(classyear, study_name, e))
                            n_expected = 0
                            new_students = []
                        self.stdout.write("        new:{}".format(new_students))
                        groups.sort(key=str)
                        i_s = 0
                        check_sum = 0
                        for group in groups:
                            g_students = set(group.students.all())
                            i_g = len(g_students)
                            for student in students_to_remove:
                                if student in g_students:
                                    if write_to_db:
                                        group.students.remove(student)
                                    i_g -= 1
                            while i_g < group.size and i_s < len(new_students):
                                if write_to_db:
                                    group.students.add(new_students[i_s])
                                i_s += 1
                                i_g += 1
                            check_sum += group.size
                            self.stdout.write(
                                "       --{} {} {} {} {}".format(
                                    group.shortName, i_s, i_g,
                                    group.size, group.id))
                        if n_expected != check_sum:
                            self.stderr.write("Wrong group size: {} {} ({}){} {} known:{} expected:{}".format(
                                classyear, study_name, subject.code, subject, t, n_expected, check_sum))
                            if n_expected > check_sum:
                                self.stderr.write("    groups too small")
                            else:
                                self.stderr.write("    groups too large")
                            for group in groups:
                                self.stderr.write("    {}: {} ?= {}".format(
                                    group.shortName, group.size, group.students.count()))

    def printGroupSurnames(self, tt):
        l = []
        for group in tt.groupset.groups.all():
            s = list(group.students.order_by("surname", "name").all())
            if len(s) > 0:
            #    print "    ", s[0].surname[:5], s[-1].surname[:5]
                l.append((str(group).split()[0], u"" + s[0].surname + u" " + s[0].name, s[-1].surname + " " + s[-1].name, len(s), group.size))
            else:
                l.append((str(group).split()[0], u"-", u"-", 0, group.size))
        d = {}
        l.sort()
        lastName = l[0][0]
        d[lastName] = (l[0][1], 1, l[0][2], 1, l[0][3], l[0][4])
        for i, (shortName, s1, s2, n, gn) in enumerate(l[1:]):
            s1_, l1_, s2_, l2_, n_, gn_ = d[lastName]
            firstdiff = 0
            while firstdiff+1 < min(len(s2_), len(s1)) and s2_[firstdiff] == s1[firstdiff]:
                firstdiff += 1
            d[shortName] = (s1, firstdiff+1, s2, firstdiff+1, n, gn)
            d[lastName] = (s1_, l1_, s2_, firstdiff+1, n_, gn_)
            lastName = shortName
        s1_, l1_, s2_, l2_, n_, gn_ = d[lastName]
        d[lastName] = (s1_, l1_, s2_, 1, n_, gn_)
        for k in sorted(d):
            s1, l1, s2, l2, n, gn = d[k]
            self.stdout.write(u"{0}: {1} .. {2} ({3} - {4})".format(k, s1[:l1], s2[:l2], n, gn))
