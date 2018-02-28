#!/usr/bin/python
# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand

import os
from xml.etree import ElementTree as ET
from collections import defaultdict
import re
from timetable.models import WEEKDAYS, WORKHOURS, Allocation, Classroom
from friprosveta.models import Teacher, ActivityRealization, Timetable

def roomsNotAvailableToTimetable(constraints, timetable, activity, clear=False):
    if clear:
        Allocation.objects.filter(timetable=timetable).delete()
    for i in constraints:
        roomname = i.find('Room').text
        print(roomname)
        classroom = Classroom.objects.get(short_name=roomname, classroomset=timetable.classroomset)
        print(classroom.short_name)
        prev_hindex = None
        start_h = None
        prev_day = None
        dayDict = {}
        for d in WEEKDAYS:
            dayDict[d[1]] = d[0]
        duration = 0
        for t in i.findall('Not_Available_Time'):
            day = t.find('Day').text
            hour = t.find('Hour').text
            # print "  " + day + " at " + hour
            hindex = WORKHOURS.index((hour, hour))
            duration += 1
            if hindex-1 != prev_hindex or prev_day != day:
                if start_h is not None:    
                    a = Allocation()
                    a.activity = activity
                    a.timetable = timetable
                    a.classroom = classroom
                    a.day = dayDict[prev_day]
                    a.start = start_h
                    a.duration = duration
                    print(a)
                    a.save()
                start_h = hour
                duration = 0;
            prev_hindex = hindex
            prev_day = day
        if start_h is not None:
            a = Allocation()
            a.activity = activity
            a.timetable = timetable
            a.classroom = classroom
            a.day = dayDict[day]
            a.start = start_h
            a.duration = duration
            print(a)
            a.save()
    pass


def allocationsFromActivitiesFile(f, timetable, name_filter = ".*"):
    activitiesTimetable = ET.parse(f).getroot()
    dayDict = {}
    for i in WEEKDAYS:
        dayDict[i[1]] = i[0]
    l = []
    for xa in activitiesTimetable.findall('Activity'):
        aid = xa.find('Id').text
        aday = xa.find('Day').text
        ahour = xa.find('Hour').text
        aroom = xa.find('Room').text
        try:
            realization = ActivityRealization.objects.get(id = int(aid))
            if re.match(name_filter, realization.activity.short_name):
                a = Allocation()
                a.activityRealization = realization
                a.start = ahour
                a.day = dayDict[aday]
                a.classroom = Classroom.objects.get(short_name=aroom, classroomset=timetable.classroomset)
                a.timetable = timetable
                l.append(a)
        except Exception as e:
            print("Error allocating activity ", aid)
            print(e)
    return l

def allocationTeachersFromFile(f, allocations):
    teachersTimetable = ET.parse(f).getroot()
    teacherDict = defaultdict(list)
    for xt in teachersTimetable.findall('Teacher'):
        n = xt.attrib['name']
        #TODO enolicne sifre!
        t = Teacher.objects.filter(sifra = n[n.rindex('(')+1:-1], veljavnost=1)[0]
        for d in xt.findall('Day'):
            for h in d.findall('Hour'):
                for r in h.findall('Room'):
                    print((d.attrib['name'], h.attrib['name'], r.attrib['name']))
                    teacherDict[(d.attrib['name'], h.attrib['name'], r.attrib['name'])].append(t)
                    
    for a in allocations:
        try:
            teachers = teacherDict[(a.get_day_display(), a.start, a.classroom.short_name)]
            a.save()
            a.teachers = teachers
        except KeyError as e:
            print("coultn'd find ", (a.day, a.start, a.classroom.short_name))
            print(e)
            pass
        
def roomsNotAvailableFromFile(f):
    fet = ET.parse(f).getroot()
    constraints = fet.find('Space_Constraints_List').findall('ConstraintRoomNotAvailableTimes')
    return constraints

def bestTimetables(d, nbest, base_timetable, fetTimetableName, name_filter = ".*"):
    l = []
    for i in os.listdir(d):
        try:
            f = open(os.path.join(d, i, fetTimetableName + '_soft_conflicts.txt'))
            for j in f.readlines():
                r = re.match(r'Total soft conflicts: (.*)', j) 
                if r:
                    l.append((float(r.group(1)), i))
        except Exception as e:
            print("Error", e)
            pass
    activitySet = base_timetable.activityset
    groupSet = base_timetable.groupset
    preferenceSet = base_timetable.preferenceset
    classroomSet = base_timetable.classroomset
    (start, end) = base_timetable.start, base_timetable.end
    respected = base_timetable.respects.all()
    l.sort()
    for i, di in enumerate(l[:nbest]):
        timetable = Timetable.objects.get_or_create(name=base_timetable.name + '-' + str(i+1) + '-' + di[1],
            defaults={'activityset': activitySet, 'groupset':groupSet, 'preferenceset': preferenceSet, 'classroomset': classroomSet, 'start': start, 'end': end})[0]
        fetDir = os.path.join(d, di[1])
        al = allocationsFromActivitiesFile(open(os.path.join(fetDir, (fetTimetableName + '_activities.xml'))), timetable, name_filter)
    #    allocationTeachersFromFile(open(fetDir + fetTimetableName + '_teachers.xml'), al)
        timetable.respects.clear()
        for r in respected:
            timetable.respects.add(r)
        timetable.save()
        Allocation.objects.filter(timetable=timetable).delete()
        for j in al:
            j.save()

def singleTimetable(d, timetable, fetTimetableName, clear=True, name_filter = ".*"):
    fetDir = d
    al = allocationsFromActivitiesFile(open(os.path.join(fetDir, (fetTimetableName + '_activities.xml'))), timetable, name_filter)
    #    allocationTeachersFromFile(open(fetDir + fetTimetableName + '_teachers.xml'), al)
    if clear:
        Allocation.objects.filter(timetable=timetable).delete()
    for i in al:
        i.save()

class Command(BaseCommand):
    '''
    Import the output of FET into a timetable
    '''
    help = """Usage: fet2django fet_timetable_dir [django_timetable_name] [n_best] [allocation_name_filter]
For multiple timetables, the number of best timetables must be specified
Each of the multiple timetables will have their rank appended to the name of the basic timetable
If no timetable name is specified for a -single timetable, a new timetable will be created using the directory as a name.
example1: ./django/urnik/fet2django.py urnik_fu_fmf_zelje-single "FRI2011/2012, zimski semester" ".*_P"
example2: ./django/urnik/fet2django.py urnik_fu_fmf_zelje-multi "FRI2011/2012, zimski semester" 3 ".*_P"""

    def add_arguments(self, parser):
        parser.add_argument('fet_timetable_dir', nargs=1)
        parser.add_argument('django_timetable_name', nargs='?')
        parser.add_argument('n_best', nargs='?',
                            type=int, default=1)
        parser.add_argument('allocation_name_filter', nargs='?',
                            default='.*')

    def handle(self, *args, **options): 
        fetTimetableDir = options['fet_timetable_dir']
        if re.match(r'.*-multi', fetTimetableDir):
            fetName = fetTimetableDir[max(0, fetTimetableDir.rfind('/')):-len('-multi')]
            multi = True
        elif re.match(r'.*-single', fetTimetableDir):
            fetName = fetTimetableDir[max(0, fetTimetableDir.rfind('/')):-len('-single')]
            multi = False
        else:
            print("Timetable dir name must end in -single or -multi")
            exit(1)
        if len(args) > 1:
            destTimetableName = args[1]
        else:
            if not multi:
                destTimetableName = fetName
            else:
                print("Can't guess the timetable name for -multi timetables")
                exit(1)
        name_filter = options['allocation_name_filter']
        if multi:
            nbest=options['n_best']
            print("base:", destTimetableName)
            timetable = Timetable.objects.get(name=destTimetableName)
            bestTimetables(fetTimetableDir, nbest, timetable, fetName, name_filter)
        else:
            timetable = Timetable.objects.get(name=destTimetableName)
            singleTimetable(fetTimetableDir, timetable, fetName, True, name_filter)
            
        #roomsNotAvailableTimetableName = "FE"
        #roomsNotAvailableGroupActivityID = 331
        #if roomsNotAvailableTimetableName is not None:
        #    timetable = Timetable.objects.get(name=roomsNotAvailableTimetableName)
        #    if timetable is None:
        #        timetable = Timetable(name=roomsNotAvailableTimetableName)
        #        timetable.save()
        #    rl = roomsNotAvailableFromFile(open(fetDir + fetTimetableName + '_data_and_timetable.fet'))
        #    roomNotAvailableGroupActivity = GroupActivity.objects.get(id=roomsNotAvailableGroupActivityID)
        #    roomsNotAvailableToTimetable(rl, timetable, roomNotAvailableGroupActivity, clear=clearNotAvailableTimetable)
            
