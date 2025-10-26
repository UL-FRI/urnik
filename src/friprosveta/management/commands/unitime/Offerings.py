import friprosveta
from frinajave.models import ACTIVITY_TEACHERS_SIZE, TeacherSubjectCycles
from friprosveta.models import StudentEnrollment
from unitime.models import Class, CourseOffering

from .common import type_itype_mapping


def classes_for_subject(subject_code, itype):
    """Return a list of UniTime Class objects
    that correspond to the subject with the given code and itype."""
    co = CourseOffering.objects.filter(
        subject_area__subject_area_abbreviation=subject_code
    )
    if co.count() != 1:
        return []
    co = co.get()
    return Class.objects.filter(
        subpart__config__instr_offr=co.instr_offr, subpart__itype__itype=itype
    ).distinct()


def offerings(tt, campus, term, year):
    entries = []
    # TODO: this could be wrong when a timetable in included in multiple timetable sets
    tt_set = tt.timetable_sets.first()
    rewrite = {
        "P": "Lec",
        "LV": "Lab",
        "SEM": "Sem",
        "AV": "Rec",
    }
    ignore_types = ["lab."]
    activityset = tt.activityset
    for subject in tt.subjects.all():
        lecture = subject.activities.filter(type="P", activityset=activityset)
        if len(lecture) == 0:
            continue
        lecture = lecture[0]
        enrolled_limit = StudentEnrollment.objects.filter(
            groupset=tt.groupset, subject__code=subject.code
        ).count()
        # enrolled_limit = lecture.size
        projected_limit = TeacherSubjectCycles.projected_class_size(
            subject.code, tt_set
        )
        subparttypes = dict()
        configs = dict()
        configs[1] = ([], [])  # We have only one config
        suffix_map = {1: "", 2: "a", 3: "b"}
        for activity in subject.activities.filter(activityset=activityset).order_by(
            "-duration"
        ):
            # Erase all activity realizations and create new ones
            # Use their id as external id in UniTime
            # So we can find corresponding subpart in UniTime
            activity.realizations.all().delete()
            if activity.type in ignore_types:
                continue
            if activity.type not in subparttypes:
                subparttypes[activity.type] = 1
            else:
                subparttypes[activity.type] += 1
            itype = type_itype_mapping[activity.type]
            classes = classes_for_subject(subject.code, itype)
            id_pool = {c.class_suffix: c.external_uid for c in classes}
            # print id_pool
            if None in id_pool:
                id_pool[""] = id_pool[None]

            (subparts, classes) = configs[1]  # We have only one config
            suffix_append = suffix_map[subparttypes[activity.type]]
            subparts += [
                "subpart",
                {
                    "type": rewrite[activity.type],
                    "suffix": suffix_append,
                    "minPerWeek": str(60 * activity.duration),
                },
                [],
            ]
            suffix = 1
            try:
                subject_teachers = TeacherSubjectCycles.realizations(
                    subject.code, tt.timetable_sets.first()
                )
                for key in subject_teachers.keys():
                    if key[0] != activity.type:
                        continue
                    instruction_style = key[1]
                    class_size = ACTIVITY_TEACHERS_SIZE[
                        (activity.type, instruction_style[1])
                    ][1]
                    if class_size == 0:
                        class_size = (
                            enrolled_limit if enrolled_limit else projected_limit
                        )
                    for teacher_codes in subject_teachers[key]:
                        instructors = []
                        teachers = []
                        for entry in teacher_codes:
                            for teacher_code in entry.split(","):
                                teacher = friprosveta.models.Teacher.objects.get(
                                    code=teacher_code
                                )
                                teachers.append(teacher)
                                instructors += [
                                    "instructor",
                                    {
                                        "id": str(teacher.id),
                                        "fname": teacher.user.first_name,
                                        "lname": teacher.user.last_name,
                                        "share": "100",
                                        "lead": "true",
                                    },
                                    [],
                                ]
                        # Now create corresponding realization
                        ar = friprosveta.models.ActivityRealization(activity=activity)
                        ar.save()
                        # Add corresponding teachers
                        ar.teachers.add(*teachers)
                        # class_id = randint(10000000, 1000000000)
                        # class id should be the same as id of our realization
                        class_id = ar.pk
                        usuffix = "{0}{1}".format(suffix, suffix_append)
                        if usuffix in id_pool:
                            class_id = id_pool[usuffix]
                        classes += [
                            "class",
                            {
                                "id": str(class_id),
                                "type": rewrite[activity.type],
                                "suffix": usuffix,
                                "limit": str(class_size),
                                "displayInScheduleBook": "true",
                            },
                            instructors,
                        ]
                        suffix += 1
            except Exception:
                pass
            configs[1] = (subparts, classes)  # We have only one config
        courseconfig = []
        for config in configs.keys():
            (subparts, classes) = configs[config]
            courseconfig += [
                "config",
                {
                    "name": str(config),
                    "limit": str(enrolled_limit if enrolled_limit else projected_limit),
                },
                subparts + classes,
            ]
        course = [
            "course",
            {
                "id": str(subject.id),
                "subject": "{0}".format(subject.code),
                "courseNbr": "101",  # TODO: kaj točno je to?
                "controlling": "true",  # TODO: kaj je to?
                "title": subject.name,
            },
            [],
        ]
        offering = [
            "offering",
            {
                "id": str(subject.id),
                "offered": "True",
                "action": "insert",  # TODO: kaj je to?
            },
            course + courseconfig,
        ]
        entries += offering
    offerings = ["offerings", {"campus": campus, "term": term, "year": year}, entries]
    return offerings
