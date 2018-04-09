def student_enrollments(timetable, campus, term, year):
    entries = []
    for student in timetable.students:
        demands = []
        for subject in student.enrolledSubjects(timetable):
            demands += [
                "class",
                {
                    "subject": "{0}".format(subject.code),
                    "courseNbr": "101"
                },
                [],
            ]
        entry = [
            "student",
            {
                "externalId": str(student.id),
            },
            demands
        ]
        entries += entry
    enrollments = [
        "studentEnrollments",
        {"campus": campus, "term": term, "year": year},
        entries
    ]
    return enrollments
