from friprosveta.models import LectureType, Student, Subject, Teacher
from timetable.models import ActivityRealization, Allocation, Classroom, Group
from unitime.models import Solution, StudentClassEnrl, TimePattern, TimePref

from ..unitime.common import (
    Database,
    PreferenceLevel,
    day_mapping,
    index_days,
    itype_type_mapping,
)


def students_for_assignment(assignment, solution_id):
    """
    Return students enrolled into unitime assignment.
    """
    students = []
    cl = assignment.class_field
    enrolments = StudentClassEnrl.objects.filter(class_field=assignment.class_field)
    for enrolment in enrolments:
        fristudent = Student.objects.get(pk=enrolment.student.external_uid)
        students.append(fristudent)
    return students


def realization_from_assignment(assignment, tt):
    """
    Return FRI realization for unitime assignment. If no subject
    exists, return None.
    """
    cl = assignment.class_field
    realization_id = cl.external_uid
    return ActivityRealization.objects.get(pk=realization_id)

    subpart = cl.subpart
    offering = subpart.config.instr_offr
    course_offerings = offering.courseoffering_set.all()
    assert course_offerings.count() == 1
    course_offering = course_offerings.get()
    subject_code = course_offering.subject_area.subject_area_abbreviation
    try:
        subject = Subject.objects.get(code=subject_code)
        minutes_per_week = subpart.min_per_wk
        type_short_name = itype_type_mapping[subpart.itype.itype]
        lecture_type = LectureType.objects.get(short_name=type_short_name)
        urooms = assignment.rooms.all()
        assert urooms.count() == 1
        room = Classroom.objects.get(pk=urooms.get().external_uid)
        hour = assignment.slot / 12
        start = "{0:02d}:{1:02d}".format(hour, 0)
        day = day_mapping[assignment.days]
        activities = tt.activities.filter(
            type=lecture_type.short_name,
            duration=minutes_per_week / 60,
            subject=subject,
        )
        assert activities.count() == 1
        activity = activities.get()
        alloc = Allocation.objects.get(
            timetable=tt, day=day, start=start, classroom=room
        )

        return alloc.activityRealization
    except Exception as e:
        print(e, day, start, room)
        return None


def enroll_students(assignment, solution_id, tt):
    students = students_for_assignment(assignment, solution_id)
    realization = realization_from_assignment(assignment, tt)
    activity = realization.activity
    group_name = "g_{0}_{1}".format(realization.id, assignment.uniqueid)
    group_short_name = "g_{0}".format(realization.id)
    parent = Group.objects.get(short_name="UT")
    group = Group.objects.get_or_create(
        name=group_name, short_name=group_short_name, groupset=tt.groupset
    )[0]
    group.parent = parent
    group.save()
    # realization.groups.clear()
    realization.groups.add(group)
    activity.groups.add(group)
    group.students.clear()
    group.students.add(*students)
    group.size = len(students)
    group.save()


def read_unitime_allocations(tt, solution):
    """Read all Unitime allocations for the given solution.
    Return tuple (subject, type, teachers, room, day, start)"""
    solution = Solution.objects.get(uniqueid=solution)
    assignments = solution.assignment_set.all()
    ret = []
    for assignment in assignments:
        instructors = assignment.instructors.all()
        teachers = [Teacher.objects.get(pk=i.external_uid) for i in instructors]
        urooms = assignment.rooms.all()
        assert urooms.count() <= 1
        try:
            room = Classroom.objects.get(pk=urooms.get().external_uid)
        except:
            room = None
        hour = assignment.slot / 12
        start = "{0:02d}:{1:02d}".format(hour, 0)
        day = day_mapping[assignment.days]
        activity = assignment.class_field
        subpart = activity.subpart
        minutes_per_week = subpart.min_per_wk
        type_short_name = itype_type_mapping[subpart.itype.itype]
        lecture_type = LectureType.objects.get(short_name=type_short_name)
        offering = subpart.config.instr_offr
        course_offerings = offering.courseoffering_set.all()
        assert course_offerings.count() == 1
        course_offering = course_offerings.get()
        subject_code = course_offering.subject_area.subject_area_abbreviation
        try:
            subject = Subject.objects.get(code=subject_code)
        except:
            print("No subject with code {0}".format(subject_code))
            continue
        ret.append(
            (subject, lecture_type, teachers, room, day, start, minutes_per_week)
        )
    return ret


def fix_current_allocations(lecture_type, solution):
    """
    Fix current allocations in Unitime for all
    lectures of the given type."""
    data = Database()
    itype_type_mapping = {10: "P", 30: "LV", 20: "AV"}
    solution = Solution.objects.get(uniqueid=solution)
    assignments = solution.assignment_set.all()
    durationids = {
        d: TimePattern.objects.get(name=str(d * 60)).uniqueid for d in [1, 2, 3, 4]
    }
    next_id = 0
    for assignment in assignments:
        instructors = assignment.instructors.all()
        teachers = [Teacher.objects.get(pk=i.external_uid) for i in instructors]
        urooms = assignment.rooms.all()
        assert urooms.count() == 1
        room = Classroom.objects.get(pk=urooms.get().external_uid)
        hour = assignment.slot / 12
        start = "{0:02d}:{1:02d}".format(hour, 0)
        day = day_mapping[assignment.days]
        activity = assignment.class_field
        subpart = activity.subpart
        minutes_per_week = subpart.min_per_wk
        duration = minutes_per_week / 60
        type_short_name = itype_type_mapping[subpart.itype.itype]
        if type_short_name != lecture_type.short_name:
            continue
        preference_day_length = 14 - duration
        preference = "2" * (preference_day_length * 7)
        hour_index = int(start[:2]) - 7
        day_index = index_days[day]
        start_index = preference_day_length * day_index + hour_index
        preference = (
            preference[:start_index]
            + PreferenceLevel.Required
            + preference[start_index + 1 :]
        )
        subject_code = assignment.class_name.split()[0]
        next_id = data.get_next_id()
        TimePref.objects.filter(owner_id=activity.uniqueid).delete()
        time_preference = TimePref(
            owner_id=activity.uniqueid,
            pref_level_id=1,
            preference=preference,
            time_pattern_id=durationids[duration],
            uniqueid=next_id,
        )
        time_preference.save()


def check_sync_with_timetable(
    tt, unitime_allocations, solution_id, lecture_types=["P"]
):
    # allocs = read_unitime_allocations(tt, solution_id)
    allocs = unitime_allocations
    allocs_dict = {
        (start, day, classroom.short_name): (s, lt, ts)
        for s, lt, ts, classroom, day, start in allocs
    }

    for start, day, classroom in allocs_dict:
        subject, lecture_type, teachers = allocs_dict[(start, day, classroom)]
        if lecture_type.short_name not in lecture_types:
            continue
        try:
            tt_alloc = tt.allocations.get(
                day=day, start=start, classroom__shortName=classroom
            )
        except:
            print(start, day, classroom, subject, "not in timetable")
        if tt_alloc.activityRealization.activity.activity.subject != subject:
            print(start, day, classroom, subject, "not in timetable")

    for allocation in tt.allocations.all():
        activity = allocation.activityRealization.activity.activity
        start = allocation.start
        day = allocation.day
        classroom = allocation.classroom.short_name
        subject = activity.subject
        if activity.lecture_type.short_name not in lecture_types:
            continue
        if (start, day, classroom) not in allocs_dict:
            print(start, day, classroom, subject, "not in Unitime!")
