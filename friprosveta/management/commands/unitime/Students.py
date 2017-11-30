from friprosveta.management.commands.unitime.CreateXML import createXML
from friprosveta.models import StudentEnrollment


def students(tt, campus, term, year):
    entries = []
    export_groups_for_studies = ['BUN-RM', 'BM-RM', 'BUN-UI', 'BUN-MM', 'BM-PRI', 'BM-KO']
    # Timetable from last year
    for student in tt.students.all():
        academicAreas = [
            "studentAcadAreaClass",
            dict(),
            [
                "acadAreaClass",
                {
                    "academicArea": "CS",
                    "academicClass": student.study(tt).replace(' ', '_')},
                [],
            ]
        ]
        majors = [
            "studentMajors",
            dict(),
            [
                "major",
                {
                    "academicArea": "CS",
                    "code": student.study(tt).replace(' ', '_')},
                [],
            ]
        ]
        minors = [
            "studentMinors",
            dict(),
            []
        ]
        student_groups = []
        exported_groupnames = []
        for enrollment in StudentEnrollment.objects.filter(
                groupset=tt.groupset,
                student=student):
            groupname = "{1}_{0}".format(enrollment.study.short_name,
                                         enrollment.classyear)
            if groupname in exported_groupnames:
                continue
            if enrollment.study.short_name in export_groups_for_studies:
                entry = [
                    'studentGroup',
                    {'group': groupname},
                    []
                ]
                student_groups += entry
                exported_groupnames.append(groupname)
        if StudentEnrollment.objects.filter(
             groupset=tt.groupset,
             student=student,
             regular_enrollment=False).count() > 0:
            entry = [
                'studentGroup',
                {'group': 'IZ'},
                []
            ]
            student_groups += entry
        groups = [
            "studentGroups",
            dict(),
            student_groups
        ]
        entry = [
            "student",
            {
                "externalId": str(student.id),
                "firstName": student.name,
                "lastName": student.surname,
                "middleName": "",
                "email": u"neznani@student.uni-lj.si",
            },
            academicAreas + majors + minors + groups
        ]
        entries += entry

    students = [
        "students",
        {"campus": campus, "term": term, "year": year},
        entries
    ]
    return students

if __name__ == "__main__":
    doc = createXML(students())
    print(doc.toprettyxml(indent="  ").encode('utf8').encode('utf8'))
