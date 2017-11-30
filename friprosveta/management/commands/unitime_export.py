from optparse import make_option
from django.core.management.base import BaseCommand, CommandError

import friprosveta
import unitime.ExportAll


class Command(BaseCommand):
    '''
    Export data to UniTime.
    '''
    help = """Export data from the Django database to Unitime.
Usage: unitime_export [--export=export] timetable_slug oldtimetable_slug \
campus term year
Campus: the name of the university campus (UL FRI)
Term: the name of the current term (Zimski semster)
Year: the name of the current year (2015). \
The format must be YYYY.
Possible exports are:
- all_xml (export all xmls)
- all_database (export all data to unitime database)
- AcademicAreas (xml)
- Majors (xml)
- Minors (xml)
- Departments (xml)
- BuildingsAandRooms (xml)
- Staff (xml)
- SubjectAreas (xml)
- Offerings (xml)
- Students (xml)
- StudentAccommodations (xml)
- StudentGroups (xml)
- LastLikeCourseDemands (xml)
- StudentEnrollments (xml)
- StudentCourseRequests (xml)
- StaffTimePreferences (database)
- RoomTimePreferences (database)
- RoomFeatures (database)
- ClassRoomPreferences (database)
- ClassesTimePatterns (database)

Default export value is xml_all.
"""
    option_list = BaseCommand.option_list + \
        (make_option(
            '--export',
            type='string',
            dest='export',
            default='xml_all',
            help='What to export'),
         )

    def handle(self, *args, **options):
        if len(args) != 5:
            raise CommandError(Command.help)
        timetable = friprosveta.models.Timetable.objects.get(slug=args[0])
        old_timetable = friprosveta.models.Timetable.objects.get(slug=args[1])
        campus, term, year = args[2:]
        unitime.ExportAll.export(timetable, old_timetable,
                                 campus, term, year, options['export'])
