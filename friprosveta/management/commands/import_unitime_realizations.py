from optparse import make_option
from django.core.management.base import BaseCommand, CommandError
from timetable.models import ActivityRealization, Allocation, Classroom
from friprosveta.models import Teacher, Timetable, Subject, Activity, LectureType
from unitime.common import Database


class Command(BaseCommand):
    help = """Create realizations and allocations from unitime
Usage: import_unitime_realizations timetable_slug unitime_solution_id"""

    def handle(self, *args, **options):
        if len(args) != 2:
            raise CommandError(Command.help)
        tt = Timetable.objects.get(slug=args[0])
        solution = int(args[1])
        # import_unitime_realizations(tt, solution)
        import_unitime_realizations(tt, solution)


def import_unitime_activities(tt, solution):
    """Read all Unitime allocations for the given solution.
    Read all scheduling subparts for these allocations and create activities and
    corresponding realizations and alocations.
    """
    day_mapping = {64: "MON", 32: "TUE", 16: "WED", 8: "THU",
                   4: "FRI", 2: "SAT", 1: "SUN"}
    itype_type_mapping = {10: 'P', 30: 'LV', 20: 'AV'}
    db = Database()
    query = ("SELECT c.uniqueid, slot, days, r.external_uid, "
             "di.external_uid, ss.uniqueid, ss.min_per_week, ss.itype "
             "FROM assignment AS a "
             "JOIN assigned_rooms AS ar ON (a.uniqueid = ar.assignment_id) "
             "JOIN assigned_instructors AS ai ON (a.uniqueid = ai.assignment_id) "
             "JOIN  departmental_instructor AS di ON "
             "(di.uniqueid = ai.instructor_id) "
             "JOIN class_ AS c ON (c.uniqueid = a.class_id) "
             "JOIN room AS r ON (r.uniqueid = ar.room_id) "
             "JOIN scheduling_subpart AS ss ON (ss.uniqueid = c.subpart_id) "
             "WHERE solution_id={0}").format(solution)
    db.execute(query)
    allocations = db.fetchallrows()
    # Subparts represent allocations
    subpart_data = dict()
    subpart_ids = set()
    for _, _, _, _, teacher_id, subpart_id, mpw, itype in allocations:
        subpart_ids.add(subpart_id)
        if subpart_id not in subpart_data:
            subpart_data[subpart_id] = (itype, mpw, [teacher_id])
        else:
            subpart_data[subpart_id][2].append(teacher_id)
    # For each subpart id we create one activity
    for subpart_id in subpart_ids:
        # First we have to determine the subject for the subpart
        query = """SELECT co.external_uid FROM scheduling_subpart AS ss
        JOIN instr_offering_config AS ioc ON (ss.config_id=ioc.uniqueid)
        JOIN course_offering AS co ON (co.instr_offr_id=ioc.instr_offr_id)
        WHERE ss.uniqueid={0}""".format(subpart_id)
        db.execute(query)
        assert db.rowcount == 1, "There should be exactly one subject per subpart"
        subject = Subject.objects.get(pk=db.fetchnextrow()[0])
        itype, minutes, teacher_ids  = subpart_data[subpart_id]
        teachers = [Teacher.objects.get(pk=teacher_id) for teacher_id in teacher_ids]
        type_short_name = itype_type_mapping[itype]
        lecture_type = LectureType.objects.get(short_name=type_short_name)
        activity = Activity(
            subject=subject,
            lecture_type=lecture_type,
            name=subject.name + "_" + type_short_name,
            short_name=subject.shortName,
            activityset=tt.activityset,
            type=type_short_name,
            duration=minutes/60,
            )
        activity.save()
        for teacher in teachers:
            activity.teachers.add(teacher)
        # Get all allocations and iterate through all class ids 
        # Classes represent realizations
        activity_allocations = [a for a in allocations if a[5]==subpart_id]
        class_ids = set([a[0] for a in activity_allocations])
        for class_id in class_ids:
            class_allocations = [a for a in activity_allocations if a[0] == class_id]
            class_teacher_ids = [a[4] for a in class_allocations]
            class_teachers = [Teacher.objects.get(pk=teacher_id) for teacher_id in class_teacher_ids]
            slot, day, room_id = class_allocations[1:1+3]
            day = day_mapping[day]
            hour = slot/12
            # minute = slot % 12 * 5
            # V resnici se pri nama vedno zacne ob uri in ne 15 cez
            minute = 0
            allocation_time = "{0:02d}:{1:02d}".format(hour, minute)
            room = Classroom.objects.get(id=room_id)
            realization = ActivityRealization(activity=activity)
            realization.save()
            realization.teachers.add(*class_teachers)
            Allocation(timetable=tt,
                       activityRealization=realization,
                       classroom=room,
                       day=day,
                       start=allocation_time).save()


def import_unitime_realizations(tt, solution):
    """Import realizations from UniTime for already available activities.
    All current realizations will be deleted.
    Explanation: our Activity roughly corresponds to the scheduling subpart
    entry in the UniTime database table.
    Our realization roughly corresponds to the entry in the UniTime
    class_ table.

    Algorithm looks as follows:
    - take an activity from out timetable
    - find corresponding scheduling subpart entry in unitime
    - find corresponding class_ entries
    - create realization and (if it exists) also allocation.
    """
    day_mapping = {64: "MON", 32: "TUE", 16: "WED", 8: "THU",
                   4: "FRI", 2: "SAT", 1: "SUN"}
    db = Database()
    type_itype_mapping = {'P': 10, 'LV': 30, 'AV': 20, 'TUT': 35}

    for activity in tt.activities.all():
        print
        print "Processing {0}".format(activity)
        # find corresponding scheduling subpart
        subject = activity.subject
        itype = type_itype_mapping[activity.type]
        query = """SELECT ss.uniqueid FROM scheduling_subpart AS ss JOIN
        instr_offering_config AS ioc ON (ss.config_id=ioc.uniqueid)
        JOIN course_offering AS co ON (co.instr_offr_id=ioc.instr_offr_id)
        WHERE co.external_uid={0} AND ss.itype={1}""".format(subject.id, itype)
        db.execute(query)
        if db.rowcount != 1:
            print(u"Error while processing {0}".format(activity.name))
            print("Only one scheduling subaprt per activity is supported.")
            print
            continue
        scheduling_subpart_id = db.fetchnextrow()[0]
        query = """SELECT uniqueid, external_uid FROM class_ WHERE
        subpart_id={0}""".format(scheduling_subpart_id)
        db.execute(query)
        rows = db.fetchallrows()
        # class_ids = [e[0] for e in db.fetchallrows()]
        # realization_ids = [e[1] for e in db.fetchallrows()]
        # print class_ids, realization_ids
        # First delete all current realizations
        # activity.realizations.all().delete()
        for class_id, realization_id in rows: #zip(class_ids, realization_ids):
            query = (
                "SELECT slot, days, r.external_uid, "
                "di.external_uid FROM assignment AS a "
                "JOIN assigned_rooms AS ar ON (a.uniqueid = ar.assignment_id) "
                "LEFT OUTER JOIN assigned_instructors AS ai ON (a.uniqueid = ai.assignment_id) "
                "LEFT OUTER JOIN  departmental_instructor AS di ON "
                "(di.uniqueid = ai.instructor_id) "
                "JOIN class_ AS c ON (c.uniqueid = a.class_id) "
                "JOIN room AS r ON (r.uniqueid = ar.room_id) "
                "WHERE solution_id={0} AND c.uniqueid={1}").format(solution, class_id)
            db.execute(query)
            if db.rowcount == 0:
                print "No class"
                continue
            rows = db.fetchallrows()
            teacher_ids = [e[3] for e in rows if e[3] is not None]
            teachers = [Teacher.objects.get(id=teacher_id) for teacher_id in teacher_ids]
            slot, day, room_id, _ = rows[0]
            day = day_mapping[day]
            hour = slot/12
            minute = slot % 12 * 5
            # V resnici se pri nama vedno zacne ob uri in ne 15 cez
            minute = 0
            allocation_time = "{0:02d}:{1:02d}".format(hour, minute)
            room = Classroom.objects.get(id=room_id)
            try: 
                #realization = ActivityRealization(activity=activity, id=realization_id)
                #realization.save()
                realization = ActivityRealization.objects.get(pk=realization_id)
                for teacher in teachers:
                    realization.teachers.add(teacher)
                print realization
            except Exception:
                print "No matching realization for {0}".format(realization_id)

            realization.allocations.all().delete()
            Allocation(timetable=tt,
                       activityRealization=realization,
                       classroom=room,
                       day=day,
                       start=allocation_time).save()
    db.close()
