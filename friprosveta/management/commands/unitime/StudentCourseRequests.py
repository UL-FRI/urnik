from friprosveta.models import StudentEnrollment


def student_course_requests(timetable, campus, term, year):
    entries = []
    enrollments = StudentEnrollment.objects.filter(groupset=timetable.groupset)
    # Hack: enroll external students to subjects to indicate
    # they can not have lectures at the time
    external_studies_short_names = ['BUN-RM', 'BUN-UI', 'BM-KO', 'BM-RM',
                                    'BUN-KO', 'BM-PRI', 'BM-MM', 'BUN-MM']
    classes = [1, 2, 3]
    for student in timetable.students:
        demands = []
        external = False
        for enrollment in enrollments.filter(student=student):
            subject = enrollment.subject
            # Subject is not in the current timetable
            if subject not in timetable.subjects:
                continue
            # Ignore 'evidencno vpisani' students
            if enrollment.study.short_name in ['EV']:
                continue
            demands += [
                "courseOffering",
                {
                    "subjectArea": "{0}".format(subject.code),
                    "courseNumber": "101",
                },
                []
            ]
            if enrollment.study.short_name in external_studies_short_names and \
                    external is False and enrollment.classyear in classes:
                external = True
                subject_name = 'z_{0}_{1}'.format(enrollment.classyear,
                                                  enrollment.study.short_name)
                demands += [
                    "courseOffering",
                    {
                        "subjectArea": "{0}".format(subject_name.lower()),
                        "courseNumber": "101",
                    },
                    []
                ]
        entry = [
            "student",
            {"key": str(student.id)},
            [
                "updateCourseRequests",
                {"commit": "true"},
                demands,
                "updateDemographics",
                {},
                [
                    "name",
                    {"first": student.name, "last": student.surname},
                    [],
                    "acadArea",
                    {"abbv": "CS", "classification": student.study(timetable)},
                    []
                ]
            ]
        ]
        entries += entry
    enrollments = [
        "request",
        {"campus": campus, "term": term, "year": year},
        entries
    ]
    return enrollments
