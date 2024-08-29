import os
import re
from collections import defaultdict
from xml.etree import ElementTree as ET

from django.core.management.base import BaseCommand

from friprosveta.models import ActivityRealization, Teacher, Timetable
from timetable.models import WEEKDAYS, WORKHOURS, Allocation, Classroom

def allocations_from_csv(f, timetable, name_filter=".*"):
    day_dict = {}
    for i in WEEKDAYS:
        day_dict[i[1]] = i[0]
    l = []
    with open(f) as f:
        reader = csv.DictReader(f)
        for d in reader:
            aid = d["Activity Id"]
            aday = d["Day"]
            ahour = d["Hour"]
            aroom = d["Room"]
            try:
                realization = ActivityRealization.objects.get(id=int(aid))
                if re.match(name_filter, realization.activity.short_name):
                    a = Allocation()
                    a.activityRealization = realization
                    a.start = ahour
                    a.day = day_dict[aday]
                    a.classroom = Classroom.objects.get(
                        short_name=aroom, classroomset=timetable.classroomset
                )
                    a.timetable = timetable
                    l.append(a)
            except Exception as e:
                print("Error allocating activity ", aid)
                print(e)
    return l


def single_timetable_csv(d, timetable, fet_timetable_name, clear=True, name_filter=".*"):
    fet_dir = d
    al = allocations_from_csv(
        open(os.path.join(fet_dir, (fet_timetable_name + "_activities.xml"))),
        timetable,
        name_filter,
    )
    #    allocationTeachersFromFile(open(fet_dir + fetTimetableName + '_teachers.xml'), al)
    if clear:
        Allocation.objects.filter(timetable=timetable).delete()
    for i in al:
        i.save()


class Command(BaseCommand):
    """
    Import the output of FET into a timetable
    """

    help = """Usage: fetcsv2django fet_csv_file.csv [django_timetable_slug] [allocation_name_filter]

example1: ./django/urnik/fetcsv2django.py urnik_fu_fmf_zelje-single_timetable.csv" fri-2012-zimski-osnova" ".*_P"
"""

    def add_arguments(self, parser):
        parser.add_argument("fet_csv_file", nargs=1)
        parser.add_argument("django_timetable_slug", nargs="?")
        parser.add_argument("allocation_name_filter", nargs="?", default=".*")

    def handle(self, *args, **options):
        fet_csv_file = options["fet_csv_file"][0]
        name_filter = options["allocation_name_filter"]
        dest_timetable_slug = options["dest_timetable_slug"]
        timetable = Timetable.objects.get(slug=dest_timetable_slug)
        single_timetable_csv(fet_csv_file, timetable, clear=True, name_filter=name_filter)

        # roomsNotAvailableTimetableName = "FE"
        # roomsNotAvailableGroupActivityID = 331
        # if roomsNotAvailableTimetableName is not None:
        #    timetable = Timetable.objects.get(name=roomsNotAvailableTimetableName)
        #    if timetable is None:
        #        timetable = Timetable(name=roomsNotAvailableTimetableName)
        #        timetable.save()
        #    rl = roomsNotAvailableFromFile(open(fetDir + fetTimetableName + '_data_and_timetable.fet'))
        #    roomNotAvailableGroupActivity = GroupActivity.objects.get(id=roomsNotAvailableGroupActivityID)
        #    roomsNotAvailableToTimetable(rl, timetable, roomNotAvailableGroupActivity, clear=clearNotAvailableTimetable)
