def lastLikeCourseDemands(tt, tt_old, campus, term, year):
    entries = []
    current_subject_codes = [subject.code for subject in tt.subjects]
    for student in tt_old.students:
        demands = []
        for subject in student.enrolledSubjects(tt_old):
            if subject.code in current_subject_codes:
                demands += [
                    "studentCourse",
                    {
                        "subject": subject.code,
                        "courseNumber": "101"
                    },
                    [],
                ]
        entry = [
            "student",
            {"externalId": str(student.id)},
            demands
        ]
        entries += entry

    offerings = [
        "lastLikeCourseDemand",
        {"campus": campus, "term": term, "year": year},
        entries
    ]
    return offerings
