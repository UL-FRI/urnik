#!/usr/bin/python
# -*- coding: utf-8 -*-

from xml.etree import ElementTree as ET
from optparse import make_option

from django.core.management.base import BaseCommand
from django.db.models import Q

import friprosveta.models
import timetable.models

from timetable.models import GroupSet

import friprosveta.management.commands.crossections as crossections
import logging

logger = logging.getLogger(__name__)


def l2El(l):
    try:
        e = ET.Element(l[0])
        if l[1] is not None:
            e.text = l[1]
        if len(l) > 2 and l[2] is not None:
            for i in l[2]:
                if i is not None and len(i) > 0:
                    e.append(l2El(i))
    except Exception as ex:
        print (l)
        print (ex)
        raise (ex)
    return e


def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def addNumberOf(l, s):
    return [[s, str(len(l))]] + l
    

def buildingsFet():
    logger.info("Entering buildingsFet")
    e = ET.Element('Buildings_List')
    for i in timetable.models.Location.objects.all():
        logger.debug("Adding building {}".format(i))
        e.append(l2El(['Building', None, [['Name', i.name]]]))
    logger.info("Exiting buildingsFet")
    return e


def roomFet(tt):
    logger.info("Entering roomFet")
    rooms_list = ET.Element('Rooms_List')
    for classroom in tt.classrooms.all():
        logger.debug("Processing classroom {}".format(classroom))
        location = classroom.location.name
        resource_workplace = timetable.models.Resource.objects.get(name='Delovno mesto')
        workplaces_n = timetable.models.ClassroomNResources.objects.filter(resource=resource_workplace, classroom=classroom)
        if len(workplaces_n) == 0:
            workplaces=0
        else:
            workplaces=workplaces_n[0].n
        logger.debug("Workplaces: {}".format(workplaces))
        rooms_list.append(l2El(['Room', None, [
            ['Name', classroom.shortName],
            ['Building', location],
            ['Capacity', str(workplaces)]]]))
    logger.info("Exiting roomFet")
    return rooms_list


def studentYearFet(timetable):
    logger.info("Entering studentYearFet")
    lsl = ['Students_List', None]
    years = {}
    for i in timetable.groups.all():
        logger.debug("Processing group {}".format(i))
        #print "Processing", i
        l = []
        j = i
        while j is not None:
            l.append(j)
            j = j.parent        
        year = l[-1]
        logger.debug("{} {}".format(l, year))

        if year in years:
            groups = years[year]
        else:
            groups = {}
            years[year] = groups
        if len(l) > 1:
            group = l[-2]
            # Gregor - premaknil if za eno v desno
            if group in groups:
                subgroups = groups[group]
            else:
                subgroups = set()
                groups[group] = subgroups
        if len(l) > 2:
            subgroups.add(l[0])
    ly = []
    for year, groups in years.items():
        logger.debug("{}; {}".format(year, groups))
        lg = []
        #print year.name + ":" + str(year.id)
        for group, subgroups in groups.items():

            logger.debug("{}; {}".format(group.name, group.id))
            logger.debug("{}".format(subgroups))
            lsg = []
            for subgroup in subgroups:
                logger.debug("Adding {}".format(subgroup))
                lsg.append(['Subgroup', None, [
                ['Name', subgroup.id_string()], ['Number_of_Students', str(subgroup.size)]]])
            lg.append(['Group', None, [['Name', group.id_string()], ['Number_of_Students', str(group.size)]] + lsg])
        ly.append(['Year', None, [['Name', year.id_string()], ['Number_of_Students', str(year.size)]] + lg])
    lsl.append(ly)
    logger.info("Exiting studentYearFet")
    return l2El(lsl)


def teachersFet(timetable):
    logger.info("Entering teachersFet")
    te = ET.Element('Teachers_List')
    for t in timetable.teachers.all():
        logger.debug("Processing teacher {}; {}".format(t, t.id_string()))
        te.append(l2El(['Teacher', None, 
            [['Name', t.id_string()]]]))
    logger.info("Exiting teachersFet")
    return te


def subjectsFet(timetable):
    logger.info("Entering subjectsFet")
    se = ET.Element('Subjects_List')
    for i in timetable.subjects.all():
        logger.debug("Adding subject {}".format(i))
        se.append(l2El(['Subject', None, 
            [['Name', i.id_string()]]]))
    logger.info("Exiting subjectsFet")
    return se


def _shrunkenStudents(timetable, realization):
    tagset = set()
    shrinkAmmount = 0
    for tag in realization.activity.tags.all():
        tagset.add(tag)
    for tag in realization.tags.all():
        tagset.add(tag)
    for tag in tagset:
        for p in tag.value_preferences.filter(preferenceset__timetable=timetable, name='SHRINKGROUPS'):
            shrinkAmmount = max(shrinkAmmount, p.value)
    return realization.size - shrinkAmmount


def activitiesFet(timetable, disabled_types=[]):
    l = []
    #<Number_of_Students
    #for i in Activity.objects.filter(timetable__exact = timetable):
    al = []
    for i in timetable.activities.distinct().all():
        for ar in i.realizations.all():
            
            tl = []
            sl = []
            al = []
           
            for t in ar.teachers.all():
                tl.append(['Teacher', t.id_string()])
            for g in ar.groups.all():
                    #sl.append(['Students', g.name+"-"+str(g.id)])
                sl.append(['Students', g.id_string()])
            if len(tl) > 0:
                al += tl
            al.append(['Subject', ar.activity.activity.subject.id_string()])
            tagset = set()
            for tag in ar.activity.tags.all():
                tagset.add(tag)
            for tag in ar.tags.all():
                tagset.add(tag)
            for tag in tagset:
                al.append(['Activity_Tag', tag.name])
            if ar.duration is not None:
                al.append(['Duration', str(ar.duration)])
                al.append(['Total_Duration', str(ar.duration)])
            al.append(['Id', str(ar.id)])
            al.append(['Activity_Group_Id', str(0)])
            if i.type in disabled_types:
                al.append(['Active', 'false'])
            else:
                al.append(['Active', 'true'])
            if len(sl) > 0:
                al += sl
            al.append(['Number_Of_Students', str(int(_shrunkenStudents(timetable, ar)))])
            l.append(['Activity', None, al])                
    return l2El(['Activities_List', None, l])

def activityTags(tt):
    tagset = set()
    for tag in timetable.models.Tag.objects.filter(activities__activityset__timetable=tt).distinct():
        tagset.add(tag.name)
    for tag in timetable.models.Tag.objects.filter(activity_realizations__activity__activityset__timetable=tt).distinct():
        tagset.add(tag.name)
    return l2El(['Activity_Tags_List', None, [['Activity_Tag', None, [['Name', i]]] for i in tagset]])
    
    
#def activitiesNotOverlapping(timetable):
#    """<ConstraintActivitiesNotOverlapping>
#        <Weight_Percentage>100</Weight_Percentage>
#        <Number_of_Activities>2</Number_of_Activities>
#        <Activity_Id>730</Activity_Id>
#        <Activity_Id>733</Activity_Id>
#    </ConstraintActivitiesNotOverlapping>"""
#    d = {}
#    ars = []
#    l = []
#    for i in timetable.activities.activities.distinct().all():
#        ars = []
#        for ar in i.realizations.all():
#            ars.append(ar.id)
#        gotOverlaps = False
#        for j in i.mustNotOverlap.filter(id__gt = i.id):
#            gotOverlaps = True
#            for ar in j.realizations.all():
#                ars.append(ar.id)
#        ars.sort()
#        nl = []
#        if gotOverlaps:
#            for ar_id in ars:
#                nl.append(['Activity_Id', str(ar_id)])
#            l.append(['ConstraintActivitiesNotOverlapping', None, [
#                ['Weight_Percentage', '100']] + addNumberOf(nl, 'Number_of_Activities')])
#    return l


def activitiesNotOverlapping(tt):
    """<ConstraintActivitiesNotOverlapping>
        <Weight_Percentage>100</Weight_Percentage>
        <Number_of_Activities>2</Number_of_Activities>
        <Activity_Id>730</Activity_Id>
        <Activity_Id>733</Activity_Id>
    </ConstraintActivitiesNotOverlapping>"""
    l = []
    for i in tt.activities.distinct().all():
        for j in i.mustNotOverlap.all().filter(id__gt = i.id):
            for iar in i.realizations.all():
                for jar in j.realizations.all():
                    nl = []
                    nl.append(['Activity_Id', str(iar.id)])  # PAZI NA VELIKI I pri Id, sicer se FET sesuje!!!
                    nl.append(['Activity_Id', str(jar.id)])
                    l.append(['ConstraintActivitiesNotOverlapping', None, [
                             ['Weight_Percentage', '100']] + addNumberOf(nl, 'Number_of_Activities')])
    for pref in timetable.models.TagDescriptivePreference.objects.filter(typename='NOOVERLAP', preferenceset__timetable=tt).distinct():
        nl = []
        for i in pref.tag.activities.filter(activityset__timetable=tt): # tole je narobe, saj vse realizacije vseh aktivnosti vrze v eno vreco
            for iar in i.realizations.all():
                nl.append(['Activity_Id', str(iar.id)])  # PAZI NA VELIKI I pri Id, sicer se FET sesuje!!!
        if len(nl) > 1:
            l.append(['ConstraintActivitiesNotOverlapping', None, [
                ['Weight_Percentage', str(int(100*pref.weight))]] + addNumberOf(nl, 'Number_of_Activities')])
        nl = []
        for iar in pref.tag.activity_realizations.filter(activity__activityset__timetable=tt):
            nl.append(['Activity_Id', str(iar.id)])  # PAZI NA VELIKI I pri Id, sicer se FET sesuje!!!
        if len(nl) > 1:
            l.append(['ConstraintActivitiesNotOverlapping', None, [
                ['Weight_Percentage', str(int(100*pref.weight))]] + addNumberOf(nl, 'Number_of_Activities')])
    # Non-overlapping zaradi izbirnosti
    return l
    
   
def activitiesCrossectionsNotOverlappingFileHack(tt, razor, enrollmentFiles):
    l = crossections.read_files(enrollmentFiles)
    #l = read_files(["/home/gregor/Dokumenti/Raziskovanje/urnik/git/urnik/estudent/FRI_obv_pr_LJ_LET_30_1_2012.txt"])
    lf = filter(lambda x: x.vpisan[0] == 'T', l)
    (groupname_group, subject_group, realizations) = crossections.parseGroups(tt)
    crossections.enrolStudents(lf, subject_group)
    return crossections.realizationsMustNotOverlapNew(tt, groupname_group, realizations, razor)
    
def activitiesOrdered(timetable):
    """
    <ConstraintTwoActivitiesOrdered>
        <Weight_Percentage>100</Weight_Percentage>
        <First_Activity_Id>881</First_Activity_Id>
        <Second_Activity_Id>1144</Second_Activity_Id>
    </ConstraintTwoActivitiesOrdered>
    """
    l = []
    for i in timetable.activities.distinct().all():
        for j in i.before.all():
            for iar in i.realizations.all():
                for jar in j.realizations.all():
                    l.append(['ConstraintTwoActivitiesOrdered', None, [
                        ['Weight_Percentage', '100'],
                        ['First_Activity_Id', str(iar.id)],
                        ['Second_Activity_Id', str(jar.id)],
                        ]])
    return l


def activitiesGrouped(tt):
    """<ConstraintTwoActivitiesGrouped>
        <Weight_Percentage>100</Weight_Percentage>
        <First_Activity_Id>797</First_Activity_Id>
        <Second_Activity_Id>796</Second_Activity_Id>
       </ConstraintTwoActivitiesGrouped>"""

    l = []
    groups = set()
    for pref in timetable.models.TagDescriptivePreference.objects.filter(typename='GROUPED', preferenceset__timetable=tt).distinct():
        al = set()
        for i in pref.tag.activities.filter(activityset__timetable=tt):
            for iar in i.realizations.all():
                al.add(str(iar.id))
        groups.add((pref.weight, tuple(al)))
        al = set()
        for i in pref.tag.activity_realizations.filter(activity__activityset__timetable=tt):
            al.add(str(i.id))
        groups.add((pref.weight, tuple(al)))
    for (w, g) in groups:
        if len(g) == 2:
            l.append(['ConstraintTwoActivitiesGrouped', None, [
                ['Weight_Percentage', str(int(100*w))],
                ['First_Activity_Id', g[0]],
                ['Second_Activity_Id', g[1]]]])
        elif len(g) == 3:
            l.append(['ConstraintThreeActivitiesGrouped', None, [
                ['Weight_Percentage', str(int(100*w))],
                ['First_Activity_Id', g[0]],
                ['Second_Activity_Id', g[1]],
                ['Third_Activity_Id', g[2]]]])
        else:
            #FET is braindead, cannot group more than 3 activities.       
            pass
    return l


def activitiesConsecutive(tt):
    """<ConstraintTwoActivitiesConsecutive>
        <Weight_Percentage>100</Weight_Percentage>
        <First_Activity_Id>2464</First_Activity_Id>
        <Second_Activity_Id>2465</Second_Activity_Id>
        <Active>true</Active>
        <Comments></Comments>
       </ConstraintTwoActivitiesConsecutive>"""
    l = []
    groups = set()
    for pref in timetable.models.TagDescriptivePreference.objects.filter(typename='CONSECUTIVE',
                                                                         preferenceset__timetable=tt).distinct():
        al = set()
        for i in pref.tag.activities.filter(activityset__timetable=tt):
            for iar in i.realizations.all():
                al.add(str(iar.id))
        groups.add((pref.weight, tuple(al)))
        al = set()
        for i in pref.tag.activity_realizations.filter(activity__activityset__timetable=tt):
            al.add(str(i.id))
        groups.add((pref.weight, tuple(al)))
    for (w, g) in groups:
        if len(g) == 2:
            l.append(['ConstraintTwoActivitiesConsecutive', None, [
                ['Weight_Percentage', str(int(100*w))],
                ['First_Activity_Id', g[0]],
                ['Second_Activity_Id', g[1]]]])
        else:
            # FET is braindead, cannot "consecutive" more than 2 activities.
            pass
    return l


def activitiesSameDay(tt):
    """<ConstraintActivitiesSameStartingDay>
        <Weight_Percentage>100</Weight_Percentage>
        <Number_of_Activities>2</Number_of_Activities>
        <Activity_Id>2672</Activity_Id>
        <Activity_Id>2673</Activity_Id>
        <Active>true</Active>
        <Comments></Comments>
       </ConstraintActivitiesSameStartingDay>"""

    l = []
    for p in timetable.models.TagDescriptivePreference.objects.filter(typename='SAMEDAY', level="WANT", preferenceset__timetable=tt).distinct():
        realizations = tt.realizations.filter(Q(activity__tags__exact = p.tag) |  Q(tags__exact = p.tag) ).distinct()
        if len(realizations) > 0:
            actList = [['Activity_Id', str(r.id)] for r in realizations]
            l.append(['ConstraintActivitiesSameStartingDay', None, [
                ['Weight_Percentage', str(100*p.weight)]] +
                addNumberOf(actList, 'Number_of_Activities')])
    return l



def activitiesMaxNumberOfRooms(tt):
    """<ConstraintActivitiesOccupyMaxDifferentRooms>
        <Weight_Percentage>100</Weight_Percentage>
        <Number_of_Activities>2</Number_of_Activities>
        <Activity_Id>2464</Activity_Id>
        <Activity_Id>2465</Activity_Id>
        <Max_Number_of_Different_Rooms>1</Max_Number_of_Different_Rooms>
        <Active>true</Active>
        <Comments></Comments>
       </ConstraintActivitiesOccupyMaxDifferentRooms>"""
    l = []
    for p in timetable.models.TagValuePreference.objects.filter(name='MAXROOMSREALIZATIONS', level="WANT", preferenceset__timetable=tt).distinct():
        realizations = tt.realizations.filter(Q(activity__tags__exact = p.tag) |  Q(tags__exact = p.tag) ).distinct()
        if len(realizations) > 1:
            actList = [['Activity_Id', str(r.id)] for r in realizations]
            l.append(['ConstraintActivitiesOccupyMaxDifferentRooms', None, [
                ['Weight_Percentage', str(100*p.adjustedWeight())]] +
                addNumberOf(actList, 'Number_of_Activities') +
                [['Max_Number_of_Different_Rooms', str(p.value)]]])
    return l
       
    
def allocationsToPreferredTimes(timetable, allocationWeights):
    logger.info("Entering allocationsToPreferredTimes")
    logger.debug("tt: {}".format(timetable))
    logger.debug("Allocation weights: {}".format(allocationWeights))
    l = []
    # done = set()
    aw = {}
    for f, (t_weight, s_weight) in allocationWeights.items():  # @UnusedVariable
        logger.debug("Processing {}; {}".format(f, (t_weight, s_weight)))
        logger.debug("Matching allocations")
        logger.debug("{}".format(timetable.own_allocations.filter(**dict(f)).distinct()))
        for a in timetable.own_allocations.filter(**dict(f)).distinct():
            w = max(t_weight, aw.get(a, t_weight))
            aw[a] = t_weight
    for (a, w) in aw.items():
        if (w > 0):
            logger.debug("Adding w {}; a_id {}; pd {}; ph {}; pl {}".format(
                str(100*w), a.activityRealization.id,
                a.get_day_display(), a.start, 'false'
            ))
            l.append(['ConstraintActivityPreferredStartingTime', None, [
                ['Weight_Percentage', str(100 * w)],
                ['Activity_Id', str(a.activityRealization.id)],
                ['Preferred_Day', a.get_day_display()],
                ['Preferred_Hour', a.start],
                ['Permanently_Locked', 'false']
            ]])
    logger.info("Exiting allocationsToPreferredTimes")
    return l


def genericNotAvailablePreferences(tt, objs, constraintString, entityString):
    l = []
    for i in objs:
        ad = {}
        for a in i.time_preferences.filter(preferenceset = tt.preferenceset, level__in = ['HATE', 'CANT']):
            weight = a.adjustedWeight()*100
            # Ignore yellow fields
            #if weight < 100:
            #    continue
            #p = str(int(a.adjustedWeight()*100))  
            p = "100"#Gregor: only 100 supported by fet, stupid
            if p not in ad:
                ad[p] = []
            for h in a.hours():
                ad[p].append(['Not_Available_Time', None, [
                    #['Day', a.get_day_display()],
                    ['Day', a.get_day_display()],
                    ['Hour', h]]])
        for tag in i.tags.all():
            for tp in timetable.models.TagTimePreference.objects.filter(tag = tag):
                weight = tp.adjustedWeight()*100
                # Ignore yellow fields
                #if weight < 100:
                #    continue
                #p = str(int(a.adjustedWeight()*100))  
                p = "100"#Gregor: only 100 supported by fet, stupid
                if p not in ad:
                    ad[p] = []
                for h in tp.hours():
                    ad[p].append(['Not_Available_Time', None, [
                        ['Day', tp.get_day_display()],
                        ['Hour', h]]])
        for (p, al) in ad.items():
            l.append([constraintString, None, [
                ['Weight_Percentage', p],
                [entityString, i.id_string()]] + addNumberOf(al, 'Number_of_Not_Available_Times')])
    return l
    
def teacherNotAvailablePreferences(tt):
    logger.info("Entering teacherNotAvailablePreferences")
    logger.debug("TT: {}".format(tt))
    r = genericNotAvailablePreferences(tt, tt.teachers.all(), 'ConstraintTeacherNotAvailableTimes', 'Teacher')
    logger.info("Exiting teacherNotAvailablePreferences")
    return r


def studentsNotAvailablePreferences(tt):
    logger.info("Entering studentsNotAvailablePreferences")
    r = genericNotAvailablePreferences(tt, tt.groups.all(), 'ConstraintStudentsSetNotAvailableTimes', 'Students')
    logger.info("Exiting studentsNotAvailablePreferences")
    return r
    
def genericValuePreferences(preferenceset, objects, fetConstraintNames, fetObject):
    l = []
    for o in objects:
        allPrefs = []
        for p in o.value_preferences.filter(preferenceset = preferenceset):
            allPrefs.append(p)
        for tag in o.tags.all():
            for p in timetable.models.TagValuePreference.objects.filter(tag = tag, preferenceset=preferenceset).all():
                allPrefs.append(p)
        for p in allPrefs:
            fetName, fetVal = fetConstraintNames.get(p.name, (None, None))
            if fetName is not None:
                l.append([fetName, None, [ 
                    ['Weight_Percentage', str(int(p.adjustedWeight()*100))], 
                    [fetObject, o.id_string()],
                    [fetVal, str(p.value)]]])
    return l
    
    
def teacherValueTimePreferences(timetable):
    logger.info("Entering teacherValueTimePreferences")
    fetConstraintNames = {
        'MAXDAYSWEEK': ('ConstraintTeacherMaxDaysPerWeek', 'Max_Days_Per_Week'),
        'MINDAYSWEEK': ('ConstraintTeacherMinDaysPerWeek', 'Min_Days_Per_Week'),
        'MAXHOURSDAY': ('ConstraintTeacherMaxHoursDaily', 'Maximum_Hours_Daily'),
        'MAXHOURSCONT': ('ConstraintTeacherMaxHoursContinuously', 'Maximum_Hours_Continuously'),
        #'MAXHOURSDAY': 'Max hours per day for a tag'),
        #'MINHOURSDAY': 'Min hours per day for a tag'),
        'MAXGAPSDAY': ('ConstraintTeacherMaxGapsPerDay', 'Max_Gaps'),
        'MAXGAPSWEEK': ('ConstraintTeacherMaxGapsPerWeek', 'Max_Gaps'),
        #'MAXCHANGESWEEK': 'Max building changes per week'),
        #'MAXCHANGESDAY': 'Max building changes per day'),
        }
    r = genericValuePreferences(timetable.preferenceset, timetable.teachers.all(), fetConstraintNames, 'Teacher_Name')
    logger.info("Exiting teacherValueTimePreferences")
    return r


def studentsValueTimePreferences(timetable):
    fetConstraintNames = {
        'MAXDAYSWEEK': ('ConstraintStudentsSetMaxDaysPerWeek', 'Max_Days_Per_Week'),
        'MINDAYSWEEK': ('ConstraintStudentsSetMinDaysPerWeek', 'Min_Days_Per_Week'),
        'MAXHOURSDAY': ('ConstraintStudentsSetMaxHoursDaily', 'Maximum_Hours_Daily'),
        'MAXHOURSCONT': ('ConstraintStudentsSetMaxHoursContinuously', 'Maximum_Hours_Continuously'),
        #'MINHOURSDAY': 'Min hours per day for a tag'),
        'MAXGAPSDAY': ('ConstraintStudentsSetMaxGapsPerDay', 'Max_Gaps'),
        'MAXGAPSWEEK': ('ConstraintStudentsSetMaxGapsPerWeek', 'Max_Gaps'),
        #'MAXCHANGESWEEK': 'Max building changes per week'),
        #'MAXCHANGESDAY': 'Max building changes per day'),
        }
    return genericValuePreferences(timetable.preferenceset, timetable.groups.all(), fetConstraintNames, 'Students') 


def teacherTimePreferencesToPreferredTimes(tt):
    logger.info("Entering teacherTimePreferencesToPreferredTimes")
    logger.debug("TT: {}".format(tt))
    prefs = dict()
    for t in tt.teachers.all():
        logger.debug("Processing {}".format(t))
        id_string = t.id_string()
        for p in t.time_preferences.filter(preferenceset = tt.preferenceset, level = 'WANT'):
            logger.debug("Processing preference: {}".format(p))
            if id_string not in prefs:
                prefs[id_string] = dict()
            w = p.adjustedWeight()
            if w not in prefs[id_string]:
                prefs[id_string][w] = dict()
            day = p.get_day_display()
            if day not in prefs[id_string][w]:
                prefs[id_string][w][day] = set()
            for h in p.hours():
                prefs[id_string][w][day].add(h)
        for p in timetable.models.TagTimePreference.objects.filter(preferenceset__timetable = tt, level='WANT', tag__teachers = t).distinct():
            if id_string not in prefs:
                prefs[id_string] = dict()
            w = p.adjustedWeight()
            if w not in prefs[id_string]:
                prefs[id_string][w] = dict()
            day = p.get_day_display()
            if day not in prefs[id_string][w]:
                prefs[id_string][w][day] = set()
            for h in p.hours():
                prefs[id_string][w][day].add(h)
    l = []
    for (teacher, i) in prefs.items():
        for (w, j) in i.items():
            timeSlots = []
            for day, hours in j.items():
                for h in hours:
                    timeSlots.append(['Preferred_Time_Slot', None, [
                        ['Preferred_Day', day],
                        ['Preferred_Hour', h]]])
            l.append(['ConstraintActivitiesPreferredTimeSlots', None, [
                ['Weight_Percentage', str(100*w)],
                ['Teacher_Name', teacher],
                ['Students_Name', None],
                ['Activity_Tag_Name', None],
                ] + addNumberOf(timeSlots, 'Number_of_Preferred_Time_Slots')])
    logger.info("Exiting teacherTimePreferencesToPreferredTimes")
    return l


def tagTimePreferencesToPreferredTimes(tt):
    prefs = dict()
    for p in timetable.models.TagTimePreference.objects.filter(Q(preferenceset__timetable = tt) &
        Q(level='WANT') & (Q(tag__activities__activityset__timetable = tt) |
        Q(tag__activity_realizations__activity__activityset__timetable = tt))).distinct():
        if p.tag.name not in prefs:
            prefs[p.tag.name] = dict()
        w = p.adjustedWeight()
        if w not in prefs[p.tag.name]:
            prefs[p.tag.name][w] = dict()
        day = p.get_day_display()
        if day not in prefs[p.tag.name][w]:
            prefs[p.tag.name][w][day] = set()
        for h in p.hours():
            prefs[p.tag.name][w][day].add(h)
    l = []
    for (tag, i) in prefs.items():
        for (w, j) in i.items():
            timeSlots = []
            for day, hours in j.items():
                for h in hours:
                    timeSlots.append(['Preferred_Time_Slot', None, [
                        ['Preferred_Day', day],
                        ['Preferred_Hour', h]]])
            l.append(['ConstraintActivitiesPreferredTimeSlots', None, [
                ['Weight_Percentage', str(100*w)],
                ['Teacher_Name', None],
                ['Students_Name', None],
                ['Activity_Tag_Name', tag],
                ] + addNumberOf(timeSlots, 'Number_of_Preferred_Time_Slots')])
    return l


def minGapsBetweenActivities(tt):
    l = []
    for p in timetable.models.TagValuePreference.objects.filter( Q(preferenceset__timetable = tt) &
        #Q(level='WANT', name='MINACTIVITYGAP') & (Q(tag__activities__activityset__timetable = tt) |
        #Q(tag__activity_realizations__activity__activityset__timetable = tt))).distinct():
        Q(level='WANT', name='MINACTIVITYGAP')).distinct():
        realizations = tt.realizations.filter(Q(activity__tags__exact = p.tag) |
            Q(tags__exact = p.tag) ).distinct()
        if len(realizations) > 0:
            actList = [['Activity_Id', str(r.id)] for r in realizations]
            l.append(['ConstraintMinGapsBetweenActivities', None, [
                ['Weight_Percentage', str(100*p.adjustedWeight())]] +
                addNumberOf(actList, 'Number_of_Activities') +
                [['MinGaps', str(p.value)]]])
    return l


def activityEndsStudentsDay(tt):
    l = []
    for p in timetable.models.TagDescriptivePreference.objects.filter( Q(preferenceset__timetable = tt) &
        #Q(level='WANT', name='MINACTIVITYGAP') & (Q(tag__activities__activityset__timetable = tt) |
        #Q(tag__activity_realizations__activity__activityset__timetable = tt))).distinct():
        Q(level='WANT', typename='ENDSSTUDENTSDAY')).distinct():
        realizations = tt.realizations.filter(Q(activity__tags__exact = p.tag) |
            Q(tags__exact = p.tag) ).distinct()
        if len(realizations) > 0:
            for r in realizations:
                l.append(['ConstraintActivityEndsStudentsDay', None, [
                    ['Weight_Percentage', str(100*p.weight)],
                    ['Activity_Id', str(r.id)],
                    ['Active', 'true'],
                    ['Comments', ''],]
                    ])
    return l


def timeConstraintsFet(timetable, groupset, razor, razor_dict,
                       allocationWeights, skip_pairs):
    l = [
        'Time_Constraints_List', None,
        [['ConstraintBasicCompulsoryTime', None,
          [['Weight_Percentage', '100']]]] +
        teacherNotAvailablePreferences(timetable) +
        respectedToTeachersNotAvailable(timetable) +
        allocationsToPreferredTimes(timetable, allocationWeights) +
        tagTimePreferencesToPreferredTimes(timetable) +
        teacherTimePreferencesToPreferredTimes(timetable) +
        activitiesOrdered(timetable) +
        activitiesNotOverlapping(timetable) +
        crossections.realizationsMustNotOverlapDatabase(
            timetable, razor=razor, razor_dict=razor_dict,
            groupset=groupset, skip_pairs=skip_pairs) +
        studentsNotAvailablePreferences(timetable) +
        respectedToStudentsNotAvailable(timetable) +
        teacherValueTimePreferences(timetable) +
        studentsValueTimePreferences(timetable) +
        minGapsBetweenActivities(timetable) +
        activityEndsStudentsDay(timetable) +
        activitiesConsecutive(timetable) +
        activitiesGrouped(timetable) +
        activitiesSameDay(timetable)
        ]
    return l2El(l)


def timetableToRoomsNotAvailable(timetable, activity=None):
    logger.info("Entering timetableToRoomsNotAvailable")
    logger.debug("Processing timetable {}".format(timetable))
    if activity is None:
        logger.debug("Activity is none")
        allocations = timetable.own_allocations.all()
    else:
        allocations = timetable.own_allocations.filter(activityRealization__activity = activity)
    logger.debug("Allocations: {}".format(allocations))
    r = []
    for room in timetable.classrooms.all():
        logger.debug("Processing room {}".format(room))
        l = []
        for i in allocations.filter(classroom=room):
            logger.debug("Processing allocation {}".format(i))
            for hour in i.hours:
                logger.debug("Not available hour: {}".format(hour))
                l.append(['Not_Available_Time', None, [
                    ['Day', i.get_day_display()],
                    ['Hour', hour],
                ]])
        if len(l) > 0:
            logger.debug("Number of not available times: {}".format(len(l)))
            l = addNumberOf(l, 'Number_of_Not_Available_Times')
            r.append(['ConstraintRoomNotAvailableTimes', None,
                [['Weight_Percentage', '100'], ['Room', room.shortName]] + l])
    logger.debug("Returning {}".format(r))
    logger.info("Exiting timetableToRoomsNotAvailable")
    return r


def timetableToStudentsNotAvailable(timetable, groupset = None):
    #print "DEBUG: rooms not available"
    allocations = timetable.own_allocations.all()
    if groupset is None:
        groupset = timetable.groupset
    r = []
    #print u"Timetable: {0}".format(timetable)
    for group in groupset.groups.all():
        #print u"DEBUG: {0}".format(room)
        l = []
        for i in allocations.filter(activityRealization__groups = group):
            for hour in i.hours:
                l.append(['Not_Available_Time', None, [
                    ['Day', i.get_day_display()],
                    ['Hour', hour],
                ]])
        if len(l) > 0:
            l = addNumberOf(l, 'Number_of_Not_Available_Times')
            r.append(['ConstraintStudentsSetNotAvailableTimes', None,
                [['Weight_Percentage', '100'], ['Students', group.id_string()]] + l])
    return r


def timetableToTeachersNotAvailable(timetable, teachers = None):
    logger.info("Entering timetableToTeachersNotAvailable")
    logger.debug("TT: {}".format(timetable))
    logger.debug("Teachers: {}".format(teachers))
    allocations = timetable.own_allocations.all()
    if teachers is None:
        teachers = timetable.teachers
    r = []
    for teacher in teachers.all():
        logger.debug("Processing {}".format(teacher))
        l = []
        for i in allocations.filter(activityRealization__teachers = teacher).distinct():
            for hour in i.hours:
                l.append(['Not_Available_Time', None, [
                    ['Day', i.get_day_display()],
                    ['Hour', hour],
                ]])
        if len(l) > 0:
            l = addNumberOf(l, 'Number_of_Not_Available_Times')
            r.append(['ConstraintTeacherNotAvailableTimes', None,
                [['Weight_Percentage', '100'], ['Teacher', teacher.id_string()]] + l])
    logger.info("Exiting timetableToTeachersNotAvailable")
    return r


def activityRequirementsToPreferredRooms(timetable):
    l = []
    #for a in Activity.objects.filter(timetable__exact = timetable):
    for ia in timetable.activities.distinct().all():
        # print ia.id, ia
        # print ia.activity
        a = ia.activity
        for ar in a.realizations.all():
            # for tmp in bmri.children(): bolonjaPodiplomci = bolonjaPodiplomci or tmp in ar.groups.all()
            lr = []
            n_students = _shrunkenStudents(timetable, ar)
            for r in ar.preferred_rooms(timetable, n_students).distinct():
            #    if r.shortName != "Eles" or bolonjaPodiplomci:  # Ugly hack
                lr.append(['Preferred_Room', r.shortName])
                
#            if ar.id == 2407:
#            print "GREGOR:", a.id , a.subject.code, a.preferred_rooms(timetable).distinct()
#            print len(lr), lr
            
            # print u"" + a.name + ", "  + str(lr)
            if len(lr) > 1:
                l.append(['ConstraintActivityPreferredRooms', None, [
                    ['Weight_Percentage', '100'],
                    ['Activity_Id', str(ar.id)]] + addNumberOf(lr, 'Number_of_Preferred_Rooms') ])
            elif len(lr) == 1:
                l.append(['ConstraintActivityPreferredRoom', None, [
                    ['Weight_Percentage', '100'],
                    ['Activity_Id', str(ar.id)],
                    ['Room', lr[0][1]],
                    ['Permanently_Locked', 'true']]])
            elif len(lr) == 0:
                raise Exception ("No prefered room for ActivityRealization id {0} - {1} \n    size:{2}\n     requirements:{3}\n    NRequirements:{4})".format(ar.id, ar, ar.size, a.requirements.all(), a.requirements_per_student.all()))
    return l


def allocationsToPreferredRoom(timetable, allocationWeights):
    l = []
    aw = dict()
    for f, (t_weight, s_weight) in allocationWeights.items():
        for a in timetable.own_allocations.filter(**dict(f)).distinct():
            w = max(s_weight, aw.get(a, s_weight))
            aw[a] = s_weight
    for (a, w) in aw.items():
        if (w > 0):
            l.append(['ConstraintActivityPreferredRoom', None, [
                ['Weight_Percentage', str(100 * w)],
                ['Activity_Id', str(a.activityRealization.id)],
                ['Room', a.classroom.shortName],
                ['Permanently_Locked', 'false']]])
    return l

def teacherValueSpacePreferences(tt):
    fetConstraintNames = {
        'MAXCHANGESWEEK': ('ConstraintTeacherMaxBuildingChangesPerWeek', 'Max_Building_Changes_Per_Week'),
        'MAXCHANGESDAY': ('ConstraintTeacherMaxBuildingChangesPerDay', 'Max_Building_Changes_Per_Day'),
        'MINCHANGEGAP': ('ConstraintTeacherMinGapsBetweenBuildingChanges', 'Min_Gaps_Between_Building_Changes'),
        }
    return genericValuePreferences(tt.preferenceset, tt.teachers.all(), fetConstraintNames, 'Teacher')
    

def studentsValueSpacePreferences(tt):
    fetConstraintNames = {
        'MAXCHANGESWEEK': ('ConstraintStudentsSetMaxBuildingChangesPerWeek', 'Max_Building_Changes_Per_Week'),
        'MAXCHANGESDAY': ('ConstraintStudentsSetMaxBuildingChangesPerDay', 'Max_Building_Changes_Per_Day'),
        'MINCHANGEGAP': ('ConstraintStudentsSetMinGapsBetweenBuildingChanges', 'Min_Gaps_Between_Building_Changes'),
        }
    return genericValuePreferences(tt.preferenceset, tt.groups.all(), fetConstraintNames, 'Students')


def respectedToRoomsNotAvailable(timetable):
    #print u"DEBUG: resp ectedToRoomsNotAvailable {0}".format(timetable)
    logger.info("Processing respectedRoomsNotAvailable")
    logger.debug("{}".format(timetable.respects.all()))
    l = []
    for j in timetable.respects.all():
        logger.debug("Processing timetable {}".format(j))
        for i in timetableToRoomsNotAvailable(j):
            logger.debug("Got {0}".format(i))
            l.append(i)
    logger.debug("Returning {}".format(l))
    return l



def respectedToStudentsNotAvailable(timetable):
    l = []
    for j in timetable.respects.all():
        for i in timetableToStudentsNotAvailable(j, groupset = timetable.groupset):
            l.append(i)
    return l


def respectedToTeachersNotAvailable(timetable):
    logger.info("Entering respectedToTeachersNotAvailable")
    l = []
    for j in timetable.respects.all():
        logger.debug("Processing timetable {}".format(j))
        for i in timetableToTeachersNotAvailable(j):
            logger.debug("Appending {}".format(i))
            l.append(i)
    logger.info("Exiting respectedToTeachersNotAvailable")
    return l


def spaceConstraintsFet(tt, allocationWeights):
    logger.info("Entering spaceConstraintsFet")
    l = ['Space_Constraints_List', None,
            [['ConstraintBasicCompulsorySpace', None, [['Weight_Percentage', '100']] ]] + 
            teacherValueSpacePreferences(tt) +
            respectedToRoomsNotAvailable(tt) +
            activityRequirementsToPreferredRooms(tt) +
            allocationsToPreferredRoom(tt, allocationWeights) +
            studentsValueSpacePreferences(tt) +
            activitiesMaxNumberOfRooms(tt)
    ]
    logger.info("Exiting spaceConstraintsFet")
    return l2El(l)


def generateFet(tt, groupset, razor, razor_dict=None,
                allocationWeights={".*": (1.0, 1.0)},
                skip_pairs=[],
                disabled_types=[]):
    logger.info("Entering generateFet")
    logger.debug("TT: {0}".format(tt))
    logger.debug("Groupset: {0}".format(groupset))
    logger.debug("razor_dict: {0}".format(razor_dict))
    logger.debug("allocationWeights: {0}".format(allocationWeights))
    logger.debug("Skip pairs: {0}".format(skip_pairs))
    logger.debug("Disabled types: {}".format(disabled_types))
    fet = ET.Element('fet', version="5.11.0")
    fet.append(l2El(['Institution_Name', 'FRI']))
    fet.append(l2El(['Comments', u"Fakulteta za računalništvo in informatiko"
                                 u" Univerze v Ljubljani"]))
    l = [['Name', i[0]] for i in timetable.models.WORKHOURS]
    fet.append(l2El(['Hours_List', None, addNumberOf(l, 'Number')]))
    l = [['Name', i[1]] for i in timetable.models.WEEKDAYS]
    fet.append(l2El(['Days_List', None, addNumberOf(l, 'Number')]))
    fet.append(studentYearFet(tt))
    fet.append(teachersFet(tt))
    fet.append(subjectsFet(tt))
    fet.append(activityTags(tt))
    fet.append(activitiesFet(tt, disabled_types))
    fet.append(buildingsFet())
    fet.append(roomFet(tt))
    fet.append(timeConstraintsFet(tt, groupset, razor, razor_dict,
                                  allocationWeights, skip_pairs))
    fet.append(spaceConstraintsFet(tt, allocationWeights))
    return fet


class Command(BaseCommand):
    '''
    Export a timetable into a FET file
    '''

    # args = '[django_timetable_slug] [razor] [<filter time_w space_w> <filter time_w space_w> ...]'
    help = """   
time_w is the weight for the time constraints, generated from the allocations
space_w is the weight for the space constraint, generated from the allocations

The filter is a regexp in the format used by your database. 
Example: 

./manage.py django2fet "2014_2015_zimski_letni" 3 .*_P 0.8 0.5 .*_LV 0.8 0.5 .*_AV 0.6 0.4
./manage.py django2fet "2014_2015_zimski_letni" 2 '{"activityRealization__activity__name__regex":".*_P", "activityRealization__groups__name__contains":"1"}' 0.8 0.5 .*_LV 0.8 0.5 .*_AV 0.6 0.4"""

    def add_arguments(self, parser):
        parser.add_argument(
            '--enrollments__groupset', nargs=1,
            action='store',
            type=str,
            dest='groupset',
            default=None,
            help='The groupset slug from which student enrollments are read.')
        parser.add_argument(
            'timetable_slug', nargs=1,
            type=str,)
        parser.add_argument(
            'razor', nargs=1,
            type=int,)
        parser.add_argument(
            'filters', nargs='*',
            type=str,
            )

    def handle(self, *args, **options):
        # print(options)
        groupset = options['groupset']
        if groupset is not None:
            groupset = GroupSet.objects.get(slug=groupset[0])

        fetTimetableName = options['timetable_slug'][0]
        razor = options['razor'][0]
        allocationWeights = {}
        filters = options['filters']
        if filters == None:
            filters=[]
        for i in range(0, len(filters), 3):
            try:
                f = eval(filters[i])
                if type(f) is not dict:
                    raise Exception
                f = tuple(f.items())
            except:
                f = (('activityRealization__activity__shortName__regex',
                      filters[i]),)
            allocationWeights[f] = (float(filters[i+1]), float(filters[i+2]))
        if len(allocationWeights) < 1:
            allocationWeights = {(('activityRealization__activity__shortName__regex', '.*'),): (1.0, 1.0)}
        razor_dict = {('P', 'P'): 3}
        try:
            timetable = friprosveta.models.Timetable.objects.get(slug=fetTimetableName)
        except Exception as e:
            print (e)
            print ("Timetables:")
            for t in friprosveta.models.Timetable.objects.all():
                print ("    ", t.slug)
            exit(1)
        # Skip pairs: which activity pairs to skip when checking for overlaps
        fet = generateFet(
            timetable, groupset, razor=razor,
            razor_dict=razor_dict,
            allocationWeights=allocationWeights,
            #skip_pairs=[('P', 'P')],
            #disabled_types=[u'LV', u'AV'],
        )
        indent(fet)
        # this is a workaround for Django's stdout.write being buggy.
        self.stdout.write(ET.tostring(fet, encoding='UTF-8').decode('UTF-8'), ending=None)
