from .common import PreferenceLevel, Database, allocation_days, WORKHOURS

# 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22

default_lecture_time_pattern = (
    (PreferenceLevel.Prohibited * 1)
    + (PreferenceLevel.Preferred * 1)
    + (PreferenceLevel.Preferred * 4)
    + (PreferenceLevel.Preferred * 1)
    + (PreferenceLevel.Discouraged * 1)
    + (PreferenceLevel.Prohibited * 7)
)

default_exercise_time_pattern = (
    (PreferenceLevel.StronglyDiscouraged * 1)
    + (PreferenceLevel.Preferred * 6)
    + (PreferenceLevel.Preferred * 2)
    + PreferenceLevel.Discouraged * 2
    +
    # PreferenceLevel.StronglyDiscouraged * 1 +
    PreferenceLevel.Prohibited * 4
)

neutral_preference = PreferenceLevel.Neutral * 15


def create_default_time_patterns(tt):
    patterns = [
        (1, 720),
        (1, 240),
        (1, 180),
        (1, 120),
        (1, 60),
    ]
    db = Database()
    session_id = db.get_session_id(tt.start)
    db.execute("DELETE FROM time_pattern_time")
    db.execute("DELETE FROM time_pattern_days")
    db.execute("DELETE FROM time_pattern_dept")
    db.execute("DELETE FROM time_pattern")

    for meetings, duration in patterns:
        name = "{1}".format(meetings, duration)
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


def combine_time_preferences(preference1, preference2):
    """More restrictive preference should win here.
    So if one prefence says prohibited and other preferred, it should be prohibited.
    Exception is neutral preference, which is lowest.
    """
    order = [
        PreferenceLevel.Prohibited,
        PreferenceLevel.Required,
        PreferenceLevel.StronglyDiscouraged,
        PreferenceLevel.Discouraged,
        PreferenceLevel.Preferred,
        PreferenceLevel.StronglyPreferred,
        PreferenceLevel.Neutral,
    ]
    assert len(preference1) == len(
        preference2
    ), "Preferences should be of the same length\n{0}\n{1}".format(
        preference1, preference2
    )
    merged = ""
    for i in range(len(preference1)):
        p1 = preference1[i]
        p2 = preference2[i]
        if p1 == p2 and p1 == PreferenceLevel.Preferred:
            merged += PreferenceLevel.StronglyPreferred
        elif p1 == p2 and p1 == PreferenceLevel.Discouraged:
            merged += PreferenceLevel.StronglyDiscouraged
        else:
            merged += sorted([p1, p2], key=lambda e: order.index(e))[0]
    return merged


def default_time_pattern(tt):
    """
    Add default time pattern to each class.

    Time pattern is different here than with staff.
    One character in time pattern here represents the affinity towards
    one entire time slot. How many time slot (and which) there are is
    determined with time pattern itself, which is defined in Unitime.
    We have 12 time slots per day for 2-hour lecture, 11 for 3-hour
    and 13 for 1-hour.
    They represents lectures between 07:00 and 20:00 (end).
    """
    # TODO: this fucks of the timetable! Use it only once at the beginning.
    # create_default_time_patterns(tt)
    type_itype_mapping = {"P": 10, "LV": 30, "AV": 20}
    db = Database()
    next_id = db.get_next_id()
    durationids = {
        4: "SELECT uniqueid FROM time_pattern WHERE name='240'",
        3: "SELECT uniqueid FROM time_pattern WHERE name='180'",
        2: "SELECT uniqueid FROM time_pattern WHERE name='120'",
        1: "SELECT uniqueid FROM time_pattern WHERE name='60'",
    }
    for (key, val) in durationids.items():
        db.execute(val)
        assert (
            db.rowcount == 1
        ), "Only one time pattern shoud exist for duration {0}".format(key)
        durationids[key] = db.fetch_next_row()[0]
    for subject in tt.subjects.all():
        for activity in tt.activities.filter(subject=subject):
            itype = type_itype_mapping[activity.type]
            query = """SELECT ss.uniqueid FROM scheduling_subpart AS ss JOIN 
            instr_offering_config AS ioc ON (ss.config_id=ioc.uniqueid)
            JOIN course_offering AS co ON (co.instr_offr_id=ioc.instr_offr_id)
            WHERE co.external_uid={0} AND ss.itype={1}""".format(
                subject.id, itype
            )
            db.execute(query)

            # assert db.rowcount == 1, "There should be exactly one sheduling subpart for activity {0}".format(activity)
            if db.rowcount != 1:
                print(activity.subject, activity.subject.code, activity.type)
                continue

            subpart_id = db.fetch_next_row()[0]
            if subpart_id is None:
                continue
            #             query = """SELECT uniqueid FROM class
            #             WHERE class_.subpart_id={0}""".format(subpart_id)
            #             db.execute(query)
            #             for class_id in db.fetch_all_rows():
            #                 # Do NOT delete the preference for class: leave them intact
            #                 delete_class_preference_query = ("DELETE FROM timetable.time_pref "
            #                                                  "WHERE owner_id={0}").format(class_id),
            #                 db.execute(delete_class_preference_query)
            database_preference = PreferenceLevel.Neutral * (14 - activity.duration) * 7
            preference_query = (
                "SELECT preference FROM timetable.time_pref WHERE owner_id={0}".format(
                    subpart_id
                )
            )
            db.execute(preference_query)
            for preference in db.fetch_all_rows():
                preference = preference[0]
                if len(database_preference) == len(preference):
                    database_preference = combine_time_preferences(
                        database_preference, preference
                    )
            pattern = default_exercise_time_pattern
            if activity.type == "P":
                pattern = default_lecture_time_pattern
            pattern = (
                pattern[: 14 - activity.duration] * 5
                + PreferenceLevel.Prohibited * (14 - activity.duration) * 2
            )
            pattern = combine_time_preferences(pattern, database_preference)
            delete_subpart_preferrence_query = (
                "DELETE FROM timetable.time_pref " "WHERE owner_id={0}"
            ).format(subpart_id)
            db.execute(delete_subpart_preferrence_query)

            add_preference_query = (
                "INSERT INTO timetable.time_pref "
                "(owner_id, pref_level_id, preference, "
                "time_pattern_id, uniqueid) "
                "VALUES ({0}, 1, '{1}', {2}, {3})"
            ).format(
                subpart_id,
                # pattern[:14-activity.duration]*5,
                pattern,
                durationids[activity.duration],
                next_id,
            )
            db.execute(add_preference_query)
            next_id = db.get_next_id()
    db.commit()
    db.close()
