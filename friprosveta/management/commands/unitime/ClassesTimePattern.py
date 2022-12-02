import datetime

from timetable.models import WORKHOURS, ActivityRealization, Classroom, Teacher

from .common import Database, PreferenceLevel, allocation_days

# 7 8 9 10 11 12 13 14 15 16 17 18 19 20
default_lecture_time_pattern = (
    (PreferenceLevel.StronglyDiscouraged * 1)
    + (PreferenceLevel.StronglyPreferred * 7)
    + PreferenceLevel.Discouraged * 2
    + PreferenceLevel.StronglyDiscouraged * 3
)

default_exercise_time_pattern = (
    (PreferenceLevel.Discouraged * 1)
    + (PreferenceLevel.StronglyPreferred * 8)
    + PreferenceLevel.Discouraged * 2
    + PreferenceLevel.StronglyDiscouraged * 2
)


def create_time_patterns(tt):
    """
    Create time patterns used by FRI.
    Used time patterns (number_of_meetings_per_week/minutes_per_meeting):
    - 1x180, 1x120, 1x60
    - 2x60
    - 2x120
    - 3x60
    - 4x60
    It is not possible to set up a time pattern consisting of
    one 60 and one 120 minute meeting.
    This has to be simulated using 3x60 time pattern and use
    distribution preference to keep two classes together.
    Maybe it would be for the best to set all classes to nx60
    time pattern and use distribution constraints to merge classes together.
    Although this is probably not optimal.
    """

    patterns = [
        (1, 240),
        (1, 180),
        (1, 120),
        (1, 60),
        (2, 60),
        (2, 120),
        (3, 60),
        (4, 60),
    ]
    db = Database()
    session_id = db.get_session_id(tt.start)
    db.execute("DELETE FROM time_pattern_time")
    db.execute("DELETE FROM time_pattern_days")
    db.execute("DELETE FROM time_pattern_dept")
    db.execute("DELETE FROM time_pattern")

    for meetings, duration in patterns:
        name = "{0}x{1}".format(meetings, duration)
        unique_id = db.get_next_id()
        query = """INSERT INTO time_pattern
                    (uniqueid, name, mins_pmt, slots_pmt, nr_mtgs, visible,
                    break_time, session_id, type)
                    VALUES ({5}, '{0}', {1}, {2}, {3}, 1, 0, {4}, 0)
                    """.format(
            name, duration, duration / 5, meetings, session_id, unique_id
        )
        db.execute(query)
        for day in allocation_days:
            day_code = allocation_days[day]
            query = """INSERT INTO time_pattern_days
                        (uniqueid, day_code, time_pattern_id)
                        VALUES ({0}, {1}, {2})
                        """.format(
                db.get_next_id(), day_code, unique_id
            )
            db.execute(query)

        for start, _ in WORKHOURS:
            start_hour, start_minute = map(int, start.split(":"))
            start_slot = start_hour * 12 + start_minute / 5
            if start_hour + duration / 60 > 20:
                continue
            query = """INSERT INTO time_pattern_time
                        (uniqueid, start_slot, time_pattern_id)
                        VALUES ({0}, {1}, {2})
                        """.format(
                db.get_next_id(), start_slot, unique_id
            )
            db.execute(query)
    db.close()


def time_patterns(tt):
    """
    Time pattern is different here than with staff.
    One character in time pattern here represents the affinity towards
    one entire time slot. How many time slot (and which) there are is
    determined with time pattern itself, which is defined in Unitime.
    We have 12 time slots per day for 2-hour lecture, 11 for 3-hour
    and 13 for 1-hour.
    They represents lectures between 07:00 and 20:00 (end).
    """
    create_time_patterns(tt)
    db = Database()

    start_range = db.get_id_range()[0]  # TODO: what about end_range?
    next_id = start_range
    durationids = {
        4: "SELECT uniqueid FROM time_pattern WHERE name='1x240'",
        3: "SELECT uniqueid FROM time_pattern WHERE name='1x180'",
        2: "SELECT uniqueid FROM time_pattern WHERE name='1x120'",
        1: "SELECT uniqueid FROM time_pattern WHERE name='1x60'",
    }
    for (key, val) in durationids.items():
        db.execute(val)
        assert (
            db.rowcount == 1
        ), "Only one time pattern shoud exist for \
duration {0}".format(
            key
        )
        durationids[key] = db.fetch_next_row()[0]
    for subject in tt.subjects.all():
        lecture = subject.activities.filter(type="P", activityset=tt.activityset)
        if len(lecture) == 0:
            continue

        lecture = lecture[0]
        for activity in subject.activities.filter(activityset=tt.activityset).exclude(
            duration=0
        ):
            subpart_id = None
            for activityRealization in activity.realizations.all():
                class_id_query = (
                    "SELECT uniqueid FROM class_ WHERE " "external_uid={0}"
                ).format(activityRealization.id)
                db.execute(class_id_query)
                if db.rowcount == 0:
                    continue

                class_id = db.fetch_next_row()[0]
                subpart_id_query = (
                    "SELECT subpart_id FROM class_ " "WHERE external_uid={0}"
                ).format(activityRealization.id)
                db.execute(subpart_id_query)
                if db.rowcount == 0:
                    continue
                subpart_id = db.fetch_next_row()[0]
                delete_preference_queries = (
                    ("DELETE FROM timetable.time_pref " "WHERE owner_id={0}").format(
                        class_id
                    ),
                    ("DELETE FROM timetable.time_pref " "WHERE owner_id={0}").format(
                        subpart_id
                    ),
                )
                for delete_preference_query in delete_preference_queries:
                    db.execute(delete_preference_query)
            if subpart_id is not None:
                pattern = default_exercise_time_pattern
                if activity.type == "P":
                    pattern = default_lecture_time_pattern
                add_preference_query = (
                    "INSERT INTO timetable.time_pref "
                    "(owner_id, pref_level_id, preference, "
                    "time_pattern_id, uniqueid) "
                    "VALUES ({0}, 1, '{1}', {2}, {3})"
                ).format(
                    subpart_id,
                    pattern[: 14 - activity.duration] * 5,
                    durationids[activity.duration],
                    next_id,
                )
                db.execute(add_preference_query)
                next_id += 1
    db.close()


def import_allocations_from_fet(timetable):
    """
    Change time pattern to existing classes in FET (they must already exist),
    so that the only available time for that class is in the time slot
    allocated by FET.
    """
    data = Database()
    start_range = data.get_id_range()[0]  # What about end_range?
    next_id = start_range
    index_days = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4}
    durationids = {
        3: "SELECT uniqueid FROM time_pattern WHERE name='1 x 180'",
        2: "SELECT uniqueid FROM time_pattern WHERE name='1 x 120'",
        1: "SELECT uniqueid FROM time_pattern WHERE name='1 x 60'",
    }
    for (key, val) in durationids.items():
        data.execute(val)
        assert (
            data.rowcount == 1
        ), "Only one time pattern shoud exist for duration {0}".format(key)
        durationids[key] = data.fetch_next_row()[0]
    for subject in tt.subjects.all():
        for activity in subject.activities.filter(activityset=tt.activityset):
            for activityRealization in activity.realizations.all():
                allocations = activityRealization.allocations.filter(
                    timetable=timetable
                )
                if len(allocations) == 0:
                    continue
                assert (
                    len(allocations) == 1
                ), "There are more allocations for the realization {0}: {1}".format(
                    activityRealization, allocations
                )
                class_id_query = (
                    "SELECT uniqueid FROM class_ " "WHERE external_uid={0}"
                ).format(activityRealization.id)
                data.execute(class_id_query)
                if data.rowcount == 0:
                    continue
                class_id = data.fetch_next_row()[0]

                delete_preference_query = (
                    "DELETE FROM timetable.time_pref " "WHERE owner_id={0}"
                ).format(class_id)
                data.execute(delete_preference_query)
                preference_day_length = 14 - activity.duration
                preference = "2" * preference_day_length * 7

                for allocation in allocations:
                    hour_index = int(allocation.start[:2]) - 7
                    day_index = index_days[allocation.day]
                    start_index = preference_day_length * day_index + hour_index
                    preference = (
                        preference[:start_index]
                        + PreferenceLevel.Required
                        + preference[start_index + 1 :]
                    )
                add_preference_query = (
                    "INSERT INTO timetable.time_pref "
                    "(owner_id, pref_level_id, preference, "
                    "time_pattern_id, uniqueid) "
                    "VALUES ({0}, 1, '{1}', {2}, {3})"
                ).format(
                    class_id,
                    preference,
                    durationids[activityRealization.activity.duration],
                    next_id,
                )

                data.execute(delete_preference_query)
                data.execute(add_preference_query)
                next_id += 1
    data.close()


def import_allocations_as_new_timetable(timetable):
    """
    Day pattern:
    - MON: 64
    - TUE: 32
    - WED: 16
    - THU: 8
    - FRI: 4
    - SAT: 2
    - SUN: 1
    Time pattern: specify the start of the activity. Start is specified as 5
    minut slot, starting from midnight.
    Data is inserted in table named 'assignment' in unitime database.
    """
    data = Database()
    start_range = data.get_id_range()[0]  # What about end range?
    next_id = start_range
    # time_pattern_id in unitime database
    durationids = {
        3: "SELECT uniqueid FROM time_pattern WHERE name='1 x 180'",
        2: "SELECT uniqueid FROM time_pattern WHERE name='1 x 120'",
        1: "SELECT uniqueid FROM time_pattern WHERE name='1 x 60'",
    }

    for (key, val) in durationids.items():
        data.execute(val)
        assert (
            data.rowcount == 1
        ), "Only one time pattern shoud exist for duration {0}".format(key)
        durationids[key] = data.fetch_next_row()[0]

    # date_pattern_id in unitime database
    date_pattern_id_query = (
        "SELECT uniqueid FROM date_pattern " "WHERE name='{0}'"
    ).format("Standard")
    data.execute(date_pattern_id_query)
    if data.rowcount == 0:
        return
    date_pattern_id = data.fetch_next_row()[0]
    type_convert = {"P": "Lec", "LV": "Lab", "AV": "Rec"}
    # create a sollution
    created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # TODO: it should be unique id from solver_group table
    owner_id = 2555904
    solution_query = (
        "INSERT INTO solution (uniqueid, created, valid, commited, creator, "
        "owner_id) VALUES ({0}, '{1}', 1, 0, '{2}', {3})"
    ).format(next_id, created, "Urnik FRI", owner_id)
    print(solution_query)
    data.execute(solution_query)
    solution_id = next_id
    data.commit()
    next_id += 1
    for subject in timetable.subjects:
        for activity in subject.activities.filter(activityset=timetable.activityset):
            arcount = 0
            for activityRealization in activity.realizations.all():
                arcount += 1
                allocations = activityRealization.allocations.filter(
                    timetable=timetable
                )
                if len(allocations) == 0:
                    continue
                assert (
                    len(allocations) == 1
                ), "There are more allocations for the realization {0}: {1}".format(
                    activityRealization, allocations
                )
                # class_id in unitime database
                class_id_query = (
                    "SELECT uniqueid FROM class_ " "WHERE external_uid={0}"
                ).format(activityRealization.id)
                data.execute(class_id_query)
                if data.rowcount == 0:
                    continue
                class_id = data.fetch_next_row()[0]
                # TODO: We only delete entries if we are updating
                # existing unitime timetable
                # delete_preference_query = (
                #     ("DELETE FROM timetable.time_pref "
                #      "WHERE owner_id={0}").format(class_id))
                # data.execute(delete_preference_query)
                for allocation in allocations:
                    # days in unitime database
                    day_index = allocation_days[allocation.day]
                    # slot in unitime database
                    hour = int(allocation.start[:2])
                    minute = int(15)
                    slot = hour * 12 + minute / 5
                    # time_pattern_id in database
                    d = activityRealization.activity.duration
                    time_pattern = durationids[d]
                    class_name = "{0}_{1} {2} {3} ".format(
                        subject.short_name,
                        activity.id,
                        type_convert[activity.type],
                        arcount,
                    )
                    add_allocation_query = (
                        "INSERT INTO timetable.assignment "
                        "(uniqueid, days, slot,  time_pattern_id, "
                        "solution_id, class_id, class_name, date_pattern_id) "
                        "VALUES ({0}, {1}, {2}, {3}, {4}, {5}, '{6}', {7})"
                    ).format(
                        next_id,
                        day_index,
                        slot,
                        time_pattern,
                        solution_id,
                        class_id,
                        class_name,
                        date_pattern_id,
                    )
                    print(add_allocation_query)
                    data.execute(add_allocation_query)
                    data.commit()
                    assignment_id = next_id
                    next_id += 1
                    # TODO: assigned teachers
                    for teacher in allocation.teachers.all():
                        teacher_id_query = (
                            "SELECT uniqueid FROM departmental_instructor "
                            "WHERE external_uid={0}"
                        ).format(teacher.id)
                        data.execute(teacher_id_query)
                        if data.rowcount == 0:
                            continue
                        teacher_id = data.fetch_next_row()[0]
                        assign_teacher_query = (
                            "INSERT INTO assigned_instructors "
                            "(assignment_id, instructor_id) "
                            "VAlUES ({0}, {1})"
                        ).format(assignment_id, teacher_id)
                        data.execute(assign_teacher_query)
                    # TODO: assigned rooms
                    room_id_query = (
                        "SELECT uniqueid FROM room " "WHERE external_uid={0}"
                    ).format(allocation.classroom.id)
                    data.execute(room_id_query)
                    if data.rowcount == 0:
                        continue
                    room_id = data.fetch_next_row()[0]
                    assign_room_query = (
                        "INSERT INTO assigned_rooms (assignment_id, room_id) "
                        "VAlUES ({0}, {1})"
                    ).format(assignment_id, room_id)
                    data.execute(assign_room_query)
    data.commit()
    data.close()


def export_allocations_as_new_timetable(solution, timetable):
    """
    Export from solution timetable in unitime to new timetable.
    Day pattern:
    - MON: 64
    - TUE: 32
    - WED: 16
    - THU: 8
    - FRI: 4
    - SAT: 2
    - SUN: 1
    Time pattern: specify the start of the activity. Start is specified as 5
    minut slot, starting from midnight.
    Data is inserted in table named 'assignment' in unitime database.
    """
    day_converter = {
        64: "MON",
        32: "TUE",
        16: "WED",
        8: "THU",
        4: "FRI",
        2: "SAT",
        1: "SUN",
    }
    data = Database()

    # query = ("SELECT uniqueid, class_id, slot, days FROM "
    #          "assignment WHERE solution_id={0}").format(solution)
    # data.execute(query)

    query = (
        "SELECT c.external_uid, slot, days, r.external_uid, "
        "di.external_uid FROM assignment AS a "
        "JOIN assigned_rooms AS ar ON (a.uniqueid = ar.assignment_id) "
        "JOIN assigned_instructors AS ai ON (a.uniqueid = ai.assignment_id) "
        "JOIN  departmental_instructor AS di ON "
        "(di.uniqueid = ai.instructor_id) "
        "JOIN class_ AS c ON (c.uniqueid = a.class_id) "
        "JOIN room AS r ON (r.uniqueid = ar.room_id) "
        "WHERE solution_id={0}"
    ).format(solution)
    data.execute(query)
    rows = data.fetch_all_rows()
    for realization_id, slot, day, room_id, teacher_id in rows:
        day = day_converter[day]
        hour = slot / 12
        minute = slot % 12 * 5
        # V resnici se zacne ob uri
        minute = 0
        allocation_time = "{0:02d}:{1:02d}".format(hour, minute)
        realization = ActivityRealization.objects.get(id=realization_id)
        room = Classroom.objects.get(id=room_id)
        teacher = Teacher.objects.get(id=teacher_id)
        print(realization, allocation_time, day, room, teacher)
    data.close()
