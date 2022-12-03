from optparse import make_option

from django.core.management.base import BaseCommand, CommandError

import friprosveta

from .unitime import ExportAll


class Command(BaseCommand):
    """
    Export data to UniTime.
    """

    help = """Export data from the Django database to Unitime.
Usage: unitime_export [--export=export] timetable_slug oldtimetable_slug \
campus term year
Campus: the name of the university campus (UL FRI)
Term: the name of the current term (Zimski semster)
Year: the name of the current year in YYYY format (2021).
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

    def add_arguments(self, parser):
        """Command arguments."""
        parser.add_argument(
            "--export", help="What to export", dest="export", default="xml_all"
        )
        parser.add_argument("slug", help="Timetable slug.")
        parser.add_argument("old_slug", help="Previous year timetable slug.")
        parser.add_argument("campus", help="Campus name, for instance 'UL FRI'.")
        parser.add_argument("term", help="Term name, for instance 'zimski semester'.")
        parser.add_argument(
            "year", help="Current year in YYYY format, for instance 2021.'"
        )

    def handle(self, *args, **options):
        timetable = friprosveta.models.Timetable.objects.get(slug=options["slug"])
        old_timetable = friprosveta.models.Timetable.objects.get(
            slug=options["old_slug"]
        )
        campus, term, year = options["campus"], options["term"], options["year"]
        ExportAll.export(
            timetable, old_timetable, campus, term, year, options["export"]
        )
