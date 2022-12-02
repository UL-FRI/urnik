import sys
from collections import namedtuple

import friprosveta
import friprosveta.models
import timetable
import timetable.models


def add_number_of(l, s):
    return [[s, str(len(l))]] + l


# import django2fet
# hackity hack -----------------------------------

# novi = friprosveta.models.Timetable.objects.get(name="FRI2012/2013, zimski semester")
# stari = timetable.models.Timetable.objects.get(name='FRI2011/2012, zimski semester')

# noviPredavanja = novi.activities.filter(type='P')
# stariPredavanja = stari.activities.filter(type='P')
# stariPredavanja = stariPredavanja.filter(activity__locations__name__contains="Ljubljana").distinct()

# m = dict()
# for predavanjeNovo in noviPredavanja.all():
#  predavanjaStaro = stariPredavanja.filter(activity__subject__code=predavanjeNovo.activity.subject.code).distinct()

#  if len(predavanjaStaro.all()) > 0:
#    for predavanjeStaro in predavanjaStaro.all():
# print "P:", predavanjeStaro
# print "R:", predavanjeStaro.realizations.all()

#      if len(predavanjeStaro.realizations.all()) == 0: continue
#      assert len(predavanjeStaro.realizations.all()) == 1
#      if predavanjeStaro.realizations.all()[0].id not in m:
#        m[predavanjeStaro.realizations.all()[0].id] = [predavanjeNovo.realizations.all()[0]]
#      else:
#        m[predavanjeStaro.realizations.all()[0].id].append(predavanjeNovo.realizations.all()[0])
# -------------------------------------


# ignore_subjects = ['63240', '63232', '63748', '63245', '63247', '63757', '63759', '63813', '63809', '63812', '63743', '63803', '63805', '63815', '63807', '63817']
ignore_subjects = []
rewrite_subjects = {"63746": "63223"}


class Group:
    def __init__(self, name, size, study, group):
        self.name = name
        self.size = size
        self.study = study
        self.students = list()
        self.group = group
        self.types = []

    def is_enrolled(self, student):
        return student in self.students

    def enrol(self, student):
        # assert len(self.students) < self.size
        assert student not in self.students
        self.students.append(student)
        if len(self.students) > self.size:
            self.size += 1
            self.group.size += 1
            # self.group.save()
            print("Increase size of {0} by 1".format(self.name))

    def remove(self, student):
        if student in self.students:
            self.students.remove(student)
            # self.group.students.remove(student)

    def current_size(self):
        return len(self.students)

    def __str__(self):
        return "ID: {3}: {0}, {1}, {2}".format(
            self.name, self.size, self.students, id(self.students)
        )


def group_types(groups):
    types = []
    for group in groups:
        if group.type not in types:
            types.append(group.type)
    return types


def get_year_for_group(group):
    return int(group.name.split("_")[0])


def get_study_for_group(group_short_name):
    """Get a study from a group stort name."""
    if len(group_short_name.split("_")) < 2:
        return "UNKNOWN"
    study_name = group_short_name.split("_")[1]
    return study_name


def parse_groups(current_timetable):
    """Creata a groupname -> group
    and subject code -> group *class Group above in this file*
    mapping for the current timetable."""
    subject_group = dict()
    groupname_group = dict()
    realizations = []

    for subject in current_timetable.subjects.all():
        for activity in subject.activities.filter(
            activityset=current_timetable.activityset
        ):

            for realization in activity.realizations.all():
                assert realization not in realizations
                realizations.append(realization)

            for group in activity.groups.all():
                if group.short_name not in groupname_group:
                    groupname_group[group.short_name] = Group(
                        group.short_name,
                        group.size,
                        get_study_for_group(group.short_name),
                        group,
                    )
                    # Add all students to this group
                    for student in group.students.all():
                        groupname_group[group.short_name].enrol(student.studentId)

                if activity.type not in groupname_group[group.short_name].types:
                    groupname_group[group.short_name].types.append(activity.type)

                if subject.code.strip() not in subject_group:
                    subject_group[subject.code.strip()] = []

                if (
                    groupname_group[group.short_name]
                    not in subject_group[subject.code.strip()]
                ):
                    subject_group[subject.code.strip()].append(
                        groupname_group[group.short_name]
                    )
    return groupname_group, subject_group, realizations


def subject_studies(subject_code, subject_group):
    groups = subject_group[subject_code.strip()]
    # print groups
    studies = []
    for group in groups:
        group_study = get_study_for_group(group.name)
        if group_study not in studies:
            studies.append(group_study)
    return studies


def fix_regular_subjects_enrollments(
    current_timetable, regular_subjects_map, new_study
):
    """
    Za predmete na študijih kjer ni izbirnosti pogleda, kateri študentje obiskujejo vse predmete na
    danem študiju/letniku. Te potem pusti pri miru, ostalim pa popravi vpis, in sicer jim spremeni študij
    na newStudy.

    Sintaksa za regular_subjects_map je sledeča:

    regular_subjects_map  = {
     (1, "BUN-RI"): [63201, 63202, 63203, 63204, 63205],
     (1, "BVS-RI"): [63701, 63702, 63703, 63704, 63705],
     (2, "BUN-RI"): [63211, 63212, 63213, 63214, 63215,],
    }
    """
    print(regular_subjects_map)

    def change_enrollment_study(enrollments, newstudy):
        for enrollment in enrollments:
            enrollment.study = newstudy
            enrollment.save()

    for ((classyear, study), regular_subjects) in regular_subjects_map.items():
        print("Changing {0} {1}".format(study, classyear))
        study = friprosveta.models.Study.objects.get(short_name=study)

        regular_subjects_list = list(
            friprosveta.models.Subject.objects.filter(code__in=regular_subjects)
        )
        students_on_all_regular_subjects = friprosveta.models.Student.objects.filter(
            enrolled_subjects__groupset=current_timetable.groupset,
            enrolled_subjects__classyear=classyear,
            enrolled_subjects__study=study,
        ).distinct()
        students_not_on_any_regular_subject = friprosveta.models.Student.objects.filter(
            enrolled_subjects__groupset=current_timetable.groupset,
            enrolled_subjects__classyear=classyear,
            enrolled_subjects__study=study,
        ).distinct()

        for subject in friprosveta.models.Subject.objects.filter(
            code__in=regular_subjects
        ):
            enrolled_students = subject.enrolled_students_study_classyear(
                current_timetable, study, classyear
            )
            students_on_all_regular_subjects = students_on_all_regular_subjects.filter(
                enrolled_subjects__groupset=current_timetable.groupset,
                enrolled_subjects__classyear=classyear,
                enrolled_subjects__study=study,
                enrolled_subjects__subject=subject,
            )
            students_not_on_any_regular_subject = (
                students_not_on_any_regular_subject.exclude(id__in=enrolled_students)
            )

        print("On all: {0}".format(students_on_all_regular_subjects.count()))
        print("Nowhere: {0}".format(students_not_on_any_regular_subject.count()))

        for student in students_not_on_any_regular_subject:
            student_enrollments_on_study = student.enrolled_subjects.filter(
                groupset=current_timetable.groupset, study=study, classyear=classyear
            )
            change_enrollment_study(student_enrollments_on_study, new_study)

        for subject in friprosveta.models.Subject.objects.filter(
            code__in=regular_subjects
        ):
            students_only_on_subject = subject.enrolled_students_study_classyear(
                current_timetable, study, classyear
            ).exclude(id__in=students_on_all_regular_subjects)

            for student in students_only_on_subject:
                student_enrollments_on_study = student.enrolled_subjects.filter(
                    groupset=current_timetable.groupset,
                    study=study,
                    classyear=classyear,
                )
                print("Changed {0}".format(student_enrollments_on_study.count()))
                change_enrollment_study(student_enrollments_on_study, new_study)


# vpisna: vpisna številka
# Sifra: šifra predmeta
# semester: zemski (Z) ali letni (L), irrelavant za naju
# letnik: letnik študenta
# skupina: študij
# kraj: vedno Lj?
# predmet: ime predmeta
# ime_priimek: ime in priimek
# vpisan: T ali F , za naju ni važno (že pofiltriramo ven)
def enrol_students_in_database(students, subject_group, current_timetable):
    for student in friprosveta.models.Student.objects.all():
        for group in student.groups.filter(
            groupset__timetables__exact=current_timetable
        ).distinct():
            student.groups.remove(group)
            student.save()

    for student in students:
        study = student.skupina.strip()
        if len(study.split("-")) == 3:
            study = study[:-3]

        if student.kraj.strip() in ["SE"]:
            study = study + " SE"

        year = int(student.letnik.strip())
        student_id = student.vpisna.strip()
        subject = student.sifra.strip()
        name_surname = student.ime_priimek.strip()
        student_name = name_surname.split()[0]
        student_surname = " ".join(name_surname.split()[1:])
        if subject in ignore_subjects:
            continue
        if subject in rewrite_subjects:
            subject = rewrite_subjects[subject]
        if subject not in subject_group:
            print(friprosveta.models.Subject.objects.filter(code=subject), subject)
            ignore_subjects.append(subject)
            continue
        studies = subject_studies(subject, subject_group)
        if study not in studies:
            print(study, studies)
            continue
        assert study in studies

        (databaseStudent, created) = friprosveta.models.Student.objects.get_or_create(
            name=student_name, surname=student_surname, studentId=student_id
        )
        print(
            student_name,
            student_surname,
            study,
            year,
            student_id,
            subject,
            studies,
            created,
        )
        types = ["P"]
        for t in types:
            all_groups = subject_group[subject]
            groups = filter(
                lambda group: group.study == study
                and t in group.types
                and get_year_for_group(group) == year,
                subject_group[subject],
            )
            already_enrolled = False
            for group in groups:
                num = group.group.students.filter(studentId=student_id).count()
                assert num <= 1
                if num == 1:
                    already_enrolled = True
            if already_enrolled:
                continue
            if len(groups) == 0:
                continue
            for group in groups:
                found_group = False
                if group.is_enrolled(student.vpisna.strip()):
                    found_group = True
                    break
                if (group.current_size() < group.size) and (
                    not group.is_enrolled(student.vpisna.strip())
                ):
                    group.enrol(student.vpisna.strip())
                    databaseStudent.groups.add(group.group)
                    databaseStudent.save()
                    found_group = True
                    break
                else:
                    pass
            if not found_group:
                print("NOT FOUND!!!!!!!!!!!!!!!")
                print(map(lambda g: g.group, groups))
                mingroup = min(
                    filter(lambda group: group.study == study, groups),
                    key=lambda group: group.group.size,
                )
                print(
                    "Group for student {0} ({1}) for subject {2} ({3}) not found ".format(
                        student.ime_priimek.strip(),
                        student.vpisna.strip(),
                        subject,
                        student.predmet.strip(),
                    )
                )
                print(group.group.size)
                if True:
                    print("OK")
                    mingroup.group.size = group.group.size + 1
                    mingroup.group.save()
                    mingroup.size = group.size + 1
                    mingroup.enrol(student.vpisna.strip())


# vpisna: vpisna številka
# Sifra: šifra predmeta
# semester: zemski (Z) ali letni (L), irrelavant za naju
# letnik: letnik študenta
# skupina: študij
# kraj: vedno Lj?
# predmet: ime predmeta
# ime_priimek: ime in priimek
# vpisan: T ali F , za naju ni važno (že pofiltriramo ven)
def enrol_students(students, subject_group):
    for student in students:

        study = student.skupina.strip()
        if len(study.split("-")) == 3:
            study = study[:-3]

        year = int(student.letnik.strip())

        subject = student.sifra.strip()
        if subject in ignore_subjects:
            continue

        if subject in rewrite_subjects:
            subject = rewrite_subjects[subject]

        # print student
        # print subject
        assert subject in subject_group

        studies = subject_studies(subject, subject_group)
        assert study in studies

        types = ["P", "LV", "AV"]
        for t in types:
            groups = filter(
                lambda group: group.study == study
                and t in group.types
                and get_year_for_group(group) == year,
                subject_group[subject],
            )

            if len(groups) == 0:
                continue
            for group in groups:
                found_group = False
                # print group, group.currentSize(), group.size, group.isEnroled(student.sifra.strip())
                if group.is_enrolled(student.vpisna.strip()):
                    found_group = True
                    break

                if (group.current_size() < group.size) and (
                    not group.is_enrolled(student.vpisna.strip())
                ):
                    # print "Enroling"
                    group.enrol(student.vpisna.strip())
                    found_group = True
                    break
                else:
                    pass

            if not found_group:
                print("NOT FOUND!!!!!!!!!!!!!!")
                print("Groups: " + groups)
                mingroup = min(
                    filter(lambda group: group.study == study, groups),
                    key=lambda group: group.group.size,
                )
                print(
                    "Group for student {0} ({1}) for subject {2} ({3}) not found ".format(
                        student.ime_priimek.strip(),
                        student.vpisna.strip(),
                        subject,
                        student.predmet.strip(),
                    )
                )
                print(group.group.size)
                # if raw_input("Should I increase size of the group {0} by one (y/n)? ".format(mingroup)) == 'y':
                if True:
                    print("OK")
                    mingroup.group.size = group.group.size + 1
                    mingroup.group.save()
                    mingroup.size = group.size + 1
                    mingroup.enrol(student.vpisna.strip())

        # raw_input("Student processed")


def get_enrolled_students(realization, groupname_group):
    students = set()
    for group in realization.groups.all():
        mygroup = groupname_group[group.short_name]
        students = students.union(set(mygroup.students))
    return students


def get_enroled_students_database(realization, students_cache, groupset=None):
    """
    Return a set of students enrolled to a realization.

    Students are obtained by iterating over groups on realization and
    returning union of students in groups.

    If a groupset is given, students enrelled to the group with the same name in
    the given groupset are returned.
    """

    subject = realization.activity.activity.subject
    students = set()
    if realization not in students_cache:
        for group in realization.groups.all():

            if groupset is not None:
                # A group is a match if it has a same short name and is on the same subject
                matched_groups = groupset.groups.filter(
                    short_name=group.short_name, activities__in=subject.activities.all()
                )
                if matched_groups.count() != 1:
                    continue
                else:
                    group = matched_groups.get()

            # TODO: če generacija ne gre skozi
            if group.study == "IZ" or group.study == "EV":
                continue

            group_students = set(
                group.students.all().values_list("studentId", flat=True).distinct()
            )
            students = students.union(group_students)
        students_cache[realization] = students
    return students_cache[realization]


def realizations_must_not_overlap_new(
    currentTimetable, groupname_group, realizations, razor=2
):
    not_overlap_pairs = []
    for realization1 in realizations:
        for realization2 in realizations:
            if realization1.id >= realization2.id:
                continue
            sr1 = get_enrolled_students(realization1, groupname_group)
            sr2 = get_enrolled_students(realization2, groupname_group)
            problematic = sr1.intersection(sr2)
            if len(problematic) > razor:
                not_overlap_pairs.append((len(problematic), realization1, realization2))


def realizations_must_not_overlap_database(
    current_timetable, razor, razor_dict={}, groupset=None, skip_pairs=[]
):
    """
    skip_pairs: a list of tuples of lecture types, which should be ignored.
    If lecture <-> lecture overlaps are to be ignored, then it should be
    set to [('P', 'P')].
    """
    not_overlap_pairs = []
    student_cache = dict()
    for realization1 in current_timetable.realizations.filter():
        rs = current_timetable.realizations.filter(id__gt=realization1.id)
        for realization2 in rs:
            type1 = realization1.activity.type
            type2 = realization2.activity.type
            if type1 == type2 and type1 == "P":
                print("Skipping lectures overlaps!!!")
                continue
            skip = False
            for pair in skip_pairs:
                if sorted((type1, type2)) == sorted(pair):
                    skip = True
                    break
            if skip:
                continue
            r = razor_dict.get(
                (realization1.activity.type, realization2.activity.type), None
            )
            if r is None:
                r = razor_dict.get(
                    (realization2.activity.type, realization1.activity.type), razor
                )
            sr1 = get_enroled_students_database(realization1, student_cache, groupset)
            sr2 = get_enroled_students_database(realization2, student_cache, groupset)
            problematic = sr1.intersection(sr2)
            if len(problematic) > r:
                not_overlap_pairs.append((len(problematic), realization1, realization2))

    l = []
    for i in not_overlap_pairs:
        l.append(
            [
                "ConstraintActivitiesNotOverlapping",
                None,
                [
                    ["Weight_Percentage", "100"],
                    ["Number_of_Activities", "2"],
                    ["Activity_Id", str(i[1].id)],
                    ["Activity_Id", str(i[2].id)],
                ],
            ]
        )
    return l


def realizations_must_not_overlap(assignments, classes, razor=2):
    not_overlap_pairs = []
    for ar1 in assignments.keys():
        st1 = assignments[ar1]
        ns1 = len(classes[ar1.activity.activity.subject.code])
        for ar2 in assignments.keys():
            a1 = ar1.activity.activity
            a2 = ar2.activity.activity

            if ar1.id >= ar2.id or (a1.type == "P" and a2.type == "P"):
                continue
            st2 = assignments[ar2]
            ns2 = len(classes[ar2.activity.activity.subject.code])

            number_of_problematic_students = len(st1 & st2)

            if (
                number_of_problematic_students > razor
                or number_of_problematic_students > min(ns1, ns2) / 4
            ):
                not_overlap_pairs.append((number_of_problematic_students, ar1, ar2))
                #    timetable.models.ActivityRealization.get(id=int(ar1.id)),
                #    timetable.models.ActivityRealization.get(id=int(ar2.id))))
                # print ar1, "<==>", ar2
    return not_overlap_pairs


def students_groups_classes(l):
    students = dict()
    student_study = dict()
    classes_study = dict()
    groups_students = dict()
    classes = {}
    classnames = {}
    for i in l:
        student_key = (i.vpisna, i.letnik, i.skupina)
        student_subjects = students.get(student_key, set())
        student_subjects.add(i.sifra)

        skupina = i.skupina.strip()
        # Hadnling za UN-RI-XY : odstrani -XY del, ker ga v bazi nimamo
        if len(i.skupina.split("-")) == 3:
            skupina = skupina[:-3].strip()

        if i.vpisna not in student_study:
            student_study[i.vpisna] = (i.letnik, skupina)

        # print i.vpisna, student_study[i.vpisna] , (i.letnik, skupina)
        assert student_study[i.vpisna] == (i.letnik, skupina)

        c = i.sifra
        classnames[c] = i.predmet[:-1]
        s = classes.get(c, set())
        s.add(i.vpisna)
        classes[c] = s

        group_name = "{0}_{1}".format(i.letnik, skupina)
        cs = classes_study.get((c, group_name), set())
        cs.add(i.vpisna)
        # print (c, group_name)
        classes_study[(c, group_name)] = cs

        gs = groups_students.get(group_name, set())
        gs.add(i.vpisna)
        groups_students[group_name] = gs
    return students, groups_students, student_study, classes_study, classnames, classes


def get_number_of_students_for_realization(realization, groupname):
    ret = 0
    for group in realization.groups.all():
        if group.short_name.startswith(groupname):
            ret += group.size

    # print "{0}, {1} -> {2}".format(realization, groupname, ret)
    return ret


def assign_students_to_realizations(
    tt, students, groups_students, student_study, classes_study, classnames, classes
):
    subject_codes = classnames.keys()
    # Realizacije na katere so študenti vpisani
    # ključ je realizacija, pod njo pa dictionary:
    # Ključ je letnik, smer, vrednost pa seznam študentov, ki smo jih že dodelili na tole.
    assignments = dict()

    exercises = ["LV", "AV", "LAB", "P"]
    for subject_code in subject_codes:
        activities = friprosveta.models.Activity.objects.filter(
            activityset=tt.activityset,
            subject__code=subject_code,
            type__in=exercises,
            locations__name__contains="Ljubljana",
        ).distinct()
        if len(activities) == 0:
            # print "No activity for subject {0}".format(subject_code)
            continue

        # print "Subject {0}: enrolled {1}".format(subject_code, len(classes[subject_code]))
        for student_code in classes[subject_code]:
            (year, study) = student_study[student_code]
            group_name = "{0}_{1}".format(year, study)
            # print "Student {0}, {1}".format(student_code, group_name)
            for activity in activities:
                # print "Processing {0}, {1}".format(activity, activity.subject.name)
                activity_realizations = (
                    timetable.models.ActivityRealization.objects.filter(
                        activity=activity, groups__short_name__contains=group_name
                    ).distinct()
                )
                # print "Realizations for group {0} for {1}".format(group_name, activity), activity_realizations
                # assert len(activity_realizations) > 0
                # print "Realizations", activity_realizations
                realization_found = False
                for realization in activity_realizations:
                    enroled_students = assignments.get(realization, set())
                    enroled_students_from_study = filter(
                        lambda student: student in groups_students[group_name],
                        assignments.get(realization, set()),
                    )

                    assignments[realization] = enroled_students
                    free_space = get_number_of_students_for_realization(
                        realization, group_name
                    )
                    if len(enroled_students_from_study) >= free_space:
                        # print "Processing {0} for {1}: no more space".format(subject_code, group_name)
                        continue
                        # raise  Exception ("Processing {0}: more than {1} students of {2} enrolled".format(subject_code, free_space, group_name))

                    # print enroled_students
                    # print enroled_students_from_study
                    assert student_code not in enroled_students
                    enroled_students.add(student_code)
                    realization_found = True
                    break
                if not realization_found:
                    # raise  Exception ("Processing {0}: no more room ({1} enrolled)".format(subject_code, len(classesStudy[(subject_code, group_name)])))
                    pass
                    # print "Student {0} ({1}), {2}: no more room ({3} enrolled)".format(student_code, group_name, activity.name, len(classesStudy[(subject_code, group_name)]))
    return assignments


def realizations_must_not_overlap_thirdversion(assignments, classes, razor=2):
    not_overlap_pairs = []
    for ar1 in assignments.keys():
        st1 = assignments[ar1]
        ns1 = len(classes[ar1.activity.activity.subject.code])
        for ar2 in assignments.keys():
            a1 = ar1.activity.activity
            a2 = ar2.activity.activity

            if ar1.id >= ar2.id or (a1.type == "P" and a2.type == "P"):
                continue
            st2 = assignments[ar2]
            ns2 = len(classes[ar2.activity.activity.subject.code])

            number_of_problematic_students = len(st1 & st2)

            if (
                number_of_problematic_students > razor
                or number_of_problematic_students > min(ns1, ns2) / 4
            ):
                not_overlap_pairs.append((number_of_problematic_students, ar1, ar2))
                #    timetable.models.ActivityRealization.get(id=int(ar1.id)),
                #    timetable.models.ActivityRealization.get(id=int(ar2.id))))
                # print ar1, "<==>", ar2
    return not_overlap_pairs


def notoverlap_gregor(tt, l, threshold=2):
    (
        students,
        groups_students,
        student_study,
        classes_study,
        classnames,
        classes,
    ) = students_groups_classes(l)
    assignments = assign_students_to_realizations(
        tt, students, groups_students, student_study, classes_study, classnames, classes
    )
    return realizations_must_not_overlap(assignments, classes, threshold)


def max_overlap(c1, c2):
    return intersection(c1, c2)


def avg_overlap(c1, c2):
    overlap = float(len(intersection(c1, c2)))
    return max(overlap / len(c1), overlap / len(c2))


def notoverlap_polz(tt, students, threshold=1):
    l = []
    studentdict = {}
    group_dict = {"UN-RI-IN": "UN-RI", "UN-RI-PO": "UN-RI", "UN-RI-RS": "UN-RI"}
    qwerkyset = set()
    for i in students:
        nskupina = group_dict.get(unicode(i.skupina), unicode(i.skupina.strip()))
        studentgroup = studentdict.get((i.letnik, nskupina), {})
        studentgroupsubject = studentgroup.get(i.sifra, set())
        studentgroupsubject.add(i)
        studentgroup[i.sifra] = studentgroupsubject
        studentdict[(i.letnik, nskupina)] = studentgroup
    # print studentdict.keys()
    for r1 in tt.realizations.all():
        for r2 in tt.realizations.filter(id__gt=r1.id):
            yeargroups1 = set()
            yeargroups2 = set()
            for g in r1.groups.all():
                i = g
                while i.parent is not None:
                    i = i.parent
                (year, group) = i.short_name.split("_")
                yeargroups1.add((year, group))
            for g in r2.groups.all():
                i = g
                while i.parent is not None:
                    i = i.parent
                (year, group) = i.short_name.split("_")
                yeargroups2.add((year, group))
            overlap = 0
            for studygroup in yeargroups1 & yeargroups2:
                n = min_realization_overlap(r1, r2, studentdict, studygroup, qwerkyset)
                overlap = max(overlap, n)
            if overlap >= threshold:
                l.append((overlap, r1, r2))
                # print l[-1]
    return l


def min_realization_overlap(r1, r2, students, studygroup, qwerkyset):
    otherssize = [0, 0]
    rsize = [0, 0]
    s1 = set()
    s2 = set()
    for i, (r, s) in enumerate([(r1, s1), (r2, s2)]):
        sifra = r.activity.activity.subject.code
        for g in r.groups.filter(short_name__startswith="{0}_{1}".format(*studygroup)):
            rsize[i] += g.size
            if rsize[i] > 0 and studygroup in students:
                for student in students[studygroup].get(sifra, []):
                    s.add(student.vpisna)
            else:
                if rsize[i] > 0:
                    pass
    #                print "  posebni:", studygroup, rsize[i]
    for i, activity in enumerate([r1.activity, r2.activity]):
        for r in activity.realizations.exclude(id=r1.id):
            for g in r.groups.filter(
                short_name__startswith="{0}_{1}".format(*students)
            ):
                # print " others:", g
                otherssize[i] += g.size()
    if (
        len(s1) != rsize[0] + otherssize[0]
        and (studygroup, r1.activity.id) not in qwerkyset
    ):
        qwerkyset.add((studygroup, r1.activity.id))
    #    print studygroup, r1
    #    print "  {0} estudent:{1}, najave:{2}".format(r1.activity.name, len(s1), rsize[0])
    if (
        len(s2) != rsize[1] + otherssize[1]
        and (studygroup, r2.activity.id) not in qwerkyset
    ):
        qwerkyset.add((studygroup, r2.activity.id))
    #    print studygroup, r2
    #    print "  {0} estudent:{1}, najave:{2}".format(r2.activity.short_name, len(s2), rsize[1])
    # assert len(s1) == rsize[0] and len(s2) == rsize[1]

    n1 = 0
    others1 = 0
    n2 = 0  # ljudje v studygroup, ki so na r2
    others2 = 0  # vsa mesta na aktivnosti2 za studygroup - n2
    overlap = len(s1 & s2)  # studentje v studygroup, ki so na obeh predmetih
    return max(0, -(max(*otherssize) - overlap))


def max_realization_overlap(r1, r2):
    pass


def avg_realization_overlap(r1, r2):
    pass


def must_not_overlap(r, thresh=10):
    l1 = []
    for i in r:
        if i[0] > thresh:
            l1.append(i)
    return l1


def read_files(
    fnames,
    Line=namedtuple(
        "Line",
        [
            "vpisna",
            "upn",
            "sifra",
            "semester",
            "letnik",
            "skupina",
            "kraj",
            "ime_priimek",
            "predmet",
            "vpisan",
            "tip_vpisa",
        ],
    ),
):
    l = []
    for fname in fnames:
        print("opening file")
        f = open(fname)
        print("file opened")
        l1 = unicode(f.read(), "utf-16")
        print("read data")
        # s = l1.encode('utf8')
        s = l1
        for i in s.split("\n")[1:]:
            if i != "":
                l.append(Line(*i.split("\t")))
        f.close()
    return l


def overlaps_list(pairs):
    l = []
    for k, iar, jar in pairs:
        nl = [["Activity_Id", str(iar.id)], ["Activity_Id", str(jar.id)]]
        l.append(
            [
                "ConstraintActivitiesNotOverlapping",
                None,
                [["Weight_Percentage", "100"]]
                + add_number_of(nl, "Number_of_Activities"),
            ]
        )
    return l


def get_main_group_for_study_class_year(study_shortname, classyear, current_timetable):
    groups = set()
    for group in current_timetable.groups.filter(parent=None).distinct():
        if group.study == study_shortname and int(group.classyear) == int(classyear):
            groups.add(group)
    assert (
        len(groups) == 1
    ), "Exactly one top-level group per study/classyear/timetable should exist ({0}, {1}, {2}): {3}".format(
        study_shortname, classyear, current_timetable, groups
    ).encode(
        "utf-8"
    )
    return groups.pop()


def get_subjects_for_group(group):
    subjects = set()
    for activity in group.activities.all():
        subjects.add(activity.activity.subject)
    return list(subjects)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("example usage:")
        print(
            '  ./crossections.py (enrol|calculate) "FRI2012/2013, zimski semester" [../../estudent/*LJ*12_10_2011.txt ...]'
        )
        exit(1)

    timetableName = sys.argv[2]
    # timetableName = "FRI2011/2012, letni semester"
    currentTimetable = friprosveta.models.Timetable.objects.get(name=timetableName)

    action = sys.argv[1]

    l = read_files(sys.argv[3:])
    # l = read_files(["/home/gregor/Dokumenti/Raziskovanje/urnik/git/urnik/estudent/FRI_obv_pr_LJ_LET_30_1_2012.txt"])

    lf = filter(lambda x: x.vpisan[0] == "T", l)
    (groupname_group, subject_group, realizations) = parse_groups(currentTimetable)

    if action == "enrol":

        print("Enroling")
        enrolStudentsToSubjects(lf, currentTimetable)

        regular_studies_years = ((1, "BUN-RI"), (2, "BUN-RI"), (1, "BVS-RI"))
        regular_studies_top_groups = dict(
            (
                entry,
                get_main_group_for_study_class_year(
                    entry[1], entry[0], currentTimetable
                ),
            )
            for entry in regular_studies_years
        )
        regular_studies_subjects = dict(
            (key, get_subjects_for_group(group))
            for key, group in regular_studies_top_groups.iteritems()
        )
        regular_subjects_map = regular_studies_subjects

        padstudy = friprosveta.models.Study.objects.get(short_name="PAD")
        fix_regular_subjects_enrollments(
            currentTimetable, regular_subjects_map, padstudy
        )

    elif action == "calculate":
        x = realizations_must_not_overlap_database(currentTimetable, razor=7)

        # print len(x), len(x[0])
        # xmlout = django2fet.l2El(['Insanity', None, x])
        # django2fet.indent(xmlout)
        # print ET.tostring(xmlout, encoding='UTF-8')
        # ET.tostring(realizationsMustNotOverlapNew(currentTimetable, groupname_group, realizations))
        # print x
