#!/usr/bin/env python
# -*- coding: utf-8 -*-

import csv
import sys
import os
from collections import namedtuple
from xml.etree import ElementTree as ET
from collections import defaultdict

import timetable.models 
import friprosveta.models


# import django2fet 

# hackity hack -----------------------------------

import friprosveta
import timetable 

#novi = friprosveta.models.Timetable.objects.get(name="FRI2012/2013, zimski semester")
#stari = timetable.models.Timetable.objects.get(name='FRI2011/2012, zimski semester')

#noviPredavanja = novi.activities.filter(type='P')
#stariPredavanja = stari.activities.filter(type='P')
#stariPredavanja = stariPredavanja.filter(activity__locations__name__contains="Ljubljana").distinct()

#m = dict()
#for predavanjeNovo in noviPredavanja.all():                                              
#  predavanjaStaro = stariPredavanja.filter(activity__subject__code=predavanjeNovo.activity.subject.code).distinct()
  
#  if len(predavanjaStaro.all()) > 0:
#    for predavanjeStaro in predavanjaStaro.all():
      #print "P:", predavanjeStaro
      #print "R:", predavanjeStaro.realizations.all()
       
#      if len(predavanjeStaro.realizations.all()) == 0: continue
#      assert len(predavanjeStaro.realizations.all()) == 1
#      if predavanjeStaro.realizations.all()[0].id not in m:
#        m[predavanjeStaro.realizations.all()[0].id] = [predavanjeNovo.realizations.all()[0]]
#      else:
#        m[predavanjeStaro.realizations.all()[0].id].append(predavanjeNovo.realizations.all()[0])
# -------------------------------------



#ignore_subjects = ['63240', '63232', '63748', '63245', '63247', '63757', '63759', '63813', '63809', '63812', '63743', '63803', '63805', '63815', '63807', '63817']
ignore_subjects = []
rewrite_subjects = {'63746': '63223' }


class Group:
    def __init__(self, name, size, study, group):
        self.name = name
        self.size = size
        self.study = study
        self.students = list()
        self.group = group
        self.types = []
    
    def isEnroled(self, student):
        return student in self.students
    
    def enrol(self, student):
        #assert len(self.students) < self.size
        assert student not in self.students
        self.students.append(student)
        if len(self.students) > self.size:
            self.size+=1;
            self.group.size += 1
            #self.group.save()
            print(u"Increase size of {0} by 1".format(self.name))

    def remove(self, student):        
        if student in self.students:
            self.students.remove(student)
            #self.group.students.remove(student)
                    
    def currentSize(self):
        return len(self.students)
    
    def __str__(self):
        return u"ID: {3}: {0}, {1}, {2}".format(self.name, self.size, self.students, id(self.students))
    
    
def groupTypes(groups):
    types = []
    for group in groups:
        if group.type not in types: types.append(group.type)
    return types

def getYearForGroup(group):
    return int (group.name.split('_')[0])

    
def getStudyForGroup(groupShortName):
   """Get a study from a group stort name."""
   if len(groupShortName.split('_')) < 2: return "UNKNOWN"
   studyName = groupShortName.split('_')[1]
   return studyName
   
def parseGroups(currentTimetable):
    """Creata a groupname -> group 
       and subject code -> group *class Group above in this file* 
       mapping for the current timetable."""
    subject_group = dict()
    groupname_group = dict()
    realizations = []
    
    for subject in currentTimetable.subjects.all():
        for activity in subject.activities.filter(activityset=currentTimetable.activityset):
            
            for realization in activity.realizations.all():
                assert realization not in realizations
                realizations.append(realization)
            
            for group in activity.groups.all():
                if group.short_name not in groupname_group:
                    groupname_group[group.short_name] = Group(group.short_name, group.size, getStudyForGroup(group.short_name), group)
                    # Add all students to this group
                    for student in group.students.all():
                        groupname_group[group.short_name].enrol(student.studentId)
                    
                
                if activity.type not in groupname_group[group.short_name].types: groupname_group[group.short_name].types.append(activity.type)
                                
                if subject.code.strip() not in subject_group:
                    subject_group[subject.code.strip()] = []
                    
                if groupname_group[group.short_name] not in subject_group[subject.code.strip()]:
                    subject_group[subject.code.strip()].append(groupname_group[group.short_name])  
    return (groupname_group, subject_group, realizations)


def subjectStudies(subjectCode, subject_group):
    groups = subject_group[subjectCode.strip()]
    #print groups
    studies = []
    for group in groups: 
        groupStudy = getStudyForGroup(group.name)
        if groupStudy not in studies: studies.append(groupStudy)
    return studies


def fixRegularSubjectsEnrollments(currentTimetable, regular_subjects_map, newStudy):
    """
    Za predmete na študijih kjer ni izbirnosti pogleda, kateri študentje obiskujejo vse predmete na 
    danem študiju/letniku. Te potem pusti pri miru, ostalim pa popravi vpis, in sicer jim spremeni študij
    na newStudy.

    Sintaksa za regular_subjects_map je sledeča:

    regular_subjects_map  = {
     (1, "BUN-RI"): [63201, 63202, 63203, 63204, 63205],
     (1, "BVS-RI"): [63701, 63702, 63703, 63704, 63705],
     (2, "BUN-RI"): [63211, 63212, 63213, 63214, 63215,],
    }
    """
    print (regular_subjects_map)
    def changeEnrollmentStudy(enrollments, newstudy):
        for enrollment in enrollments:
            enrollment.study = newstudy
            enrollment.save()

    for ((classyear, study), regular_subjects) in regular_subjects_map.items():
        print ("Changing {0} {1}".format(study, classyear))
        study = friprosveta.models.Study.objects.get(short_name=study)

        regular_subjects_list = list(friprosveta.models.Subject.objects.filter(code__in=regular_subjects))
        students_on_all_regular_subjects = friprosveta.models.Student.objects.filter(enrolled_subjects__groupset=currentTimetable.groupset, enrolled_subjects__classyear=classyear, enrolled_subjects__study=study).distinct()                
        students_not_on_any_regular_subject = friprosveta.models.Student.objects.filter(enrolled_subjects__groupset=currentTimetable.groupset, enrolled_subjects__classyear=classyear, enrolled_subjects__study=study).distinct()

        for subject in friprosveta.models.Subject.objects.filter(code__in=regular_subjects):
            enrolled_students = subject.enrolled_students_study_classyear(currentTimetable, study, classyear)
            students_on_all_regular_subjects = students_on_all_regular_subjects.filter(enrolled_subjects__groupset=currentTimetable.groupset, enrolled_subjects__classyear=classyear, enrolled_subjects__study=study, enrolled_subjects__subject=subject)
            students_not_on_any_regular_subject = students_not_on_any_regular_subject.exclude(id__in=enrolled_students)

        print("On all: {0}".format(students_on_all_regular_subjects.count()))
        print("Nowhere: {0}".format(students_not_on_any_regular_subject.count()))

        for student in students_not_on_any_regular_subject:  
            student_enrollments_on_study = student.enrolled_subjects.filter(groupset=currentTimetable.groupset, study=study, classyear=classyear)
            changeEnrollmentStudy(student_enrollments_on_study, newStudy)

        for subject in friprosveta.models.Subject.objects.filter(code__in=regular_subjects):
            students_only_on_subject = subject.enrolled_students_study_classyear(currentTimetable, study, classyear).exclude(id__in=students_on_all_regular_subjects)

            for student in students_only_on_subject:
                student_enrollments_on_study = student.enrolled_subjects.filter(groupset=currentTimetable.groupset, study=study, classyear=classyear)
                print("Changed {0}".format(student_enrollments_on_study.count()))
                changeEnrollmentStudy(student_enrollments_on_study, newStudy)


# vpisna: vpisna številka
# Sifra: šifra predmeta
# semester: zemski (Z) ali letni (L), irrelavant za naju
# letnik: letnik študenta
# skupina: študij 
# kraj: vedno Lj?
# predmet: ime predmeta
# ime_priimek: ime in priimek
# vpisan: T ali F , za naju ni važno (že pofiltriramo ven)
def enrolStudentsInDatabase(students, subject_group, currentTimetable):
    for student in friprosveta.models.Student.objects.all():
        for group in student.groups.filter(groupset__timetables__exact=currentTimetable).distinct():
            student.groups.remove(group)
            student.save()

    for student in students:
        study = student.skupina.strip()
        if len(study.split("-")) == 3:
            study = study[:-3]

        if student.kraj.strip() in ["SE"]:
            study = study + " SE"

        year = int(student.letnik.strip())
        studentId = student.vpisna.strip()
        subject = student.sifra.strip()
        name_surname = student.ime_priimek.strip()
        studentName = name_surname.split()[0]
        studentSurname = " ".join(name_surname.split()[1:])
        if subject in ignore_subjects:
            continue
        if subject in rewrite_subjects:
            subject = rewrite_subjects[subject]
        if subject not in subject_group:
            print(friprosveta.models.Subject.objects.filter(code=subject), subject)
            ignore_subjects.append(subject)
            continue
        studies = subjectStudies(subject, subject_group)
        if study not in studies:
            print(study, studies)
            continue
        assert study in studies

        (databaseStudent, created) = friprosveta.models.Student.objects.get_or_create(name=studentName, surname=studentSurname, studentId=studentId)
        print(studentName, studentSurname, study, year, studentId, subject, studies, created)
        types = ['P']
        for t in types:
            allGroups = subject_group[subject]
            groups =  filter(lambda group: group.study == study and t in group.types and getYearForGroup(group) == year, subject_group[subject])
            alreadyEnroled = False
            for group in groups:
                num = group.group.students.filter(studentId=studentId).count()
                assert num <= 1
                if num == 1: alreadyEnroled = True
            if alreadyEnroled:
                continue
            if len(groups) == 0:
                continue
            for group in groups:
                foundGroup = False
                if group.isEnroled( student.vpisna.strip() ):
                    foundGroup = True
                    break
                if (group.currentSize() < group.size) and (not group.isEnroled(student.vpisna.strip())):
                    group.enrol(student.vpisna.strip())
                    databaseStudent.groups.add(group.group)
                    databaseStudent.save()
                    foundGroup = True
                    break
                else:
                    pass
            if not foundGroup:
                print("NOT FOUND!!!!!!!!!!!!!!!")
                print(map(lambda g: g.group, groups))
                mingroup = min( filter(lambda group: group.study == study, groups) , key=lambda group: group.group.size)
                print("Group for student {0} ({1}) for subject {2} ({3}) not found ".format(student.ime_priimek.strip(), student.vpisna.strip(), subject, student.predmet.strip()))
                print(group.group.size)
                if True:
                    print("OK")
                    mingroup.group.size = group.group.size + 1
                    mingroup.group.save()
                    mingroup.size = group.size + 1
                    mingroup.enrol(student.vpisna.strip())



# vpisna: vpisna številka
# Sifra: šifra predmeta
# semester: zemski (Z) ali letni (L), irrelavant za naju
# letnik: letnik študenta
# skupina: študij 
# kraj: vedno Lj?
# predmet: ime predmeta
# ime_priimek: ime in priimek
# vpisan: T ali F , za naju ni važno (že pofiltriramo ven)
def enrolStudents(students, subject_group):
    for student in students:
    
        study = student.skupina.strip()
        if len(study.split("-")) == 3:
            study = study[:-3]
        
        year = int(student.letnik.strip())
        
        subject = student.sifra.strip()
        if subject in ignore_subjects: continue
        
        if subject in rewrite_subjects:
            subject = rewrite_subjects[subject]
        
        # print student
        # print subject
        assert subject in subject_group
          
        studies = subjectStudies(subject, subject_group)
        assert study in studies
        
        types = ['P', 'LV', 'AV']
        for t in types:
            groups =  filter(lambda group: group.study == study and t in group.types and getYearForGroup(group) == year, subject_group[subject])
                          
            if len(groups) == 0: continue
            for group in groups:            
                foundGroup = False
                # print group, group.currentSize(), group.size, group.isEnroled(student.sifra.strip())
                if group.isEnroled(student.vpisna.strip()):
                    foundGroup = True
                    break
                
                if (group.currentSize() < group.size) and (not group.isEnroled(student.vpisna.strip())):
                    #print "Enroling"
                    group.enrol(student.vpisna.strip())
                    foundGroup = True
                    break
                else:
                    pass

        
            if not foundGroup:
                print("NOT FOUND!!!!!!!!!!!!!!")
                print("Groups: " + groups)
                mingroup = min( filter(lambda group: group.study == study, groups) , key=lambda group: group.group.size)
                print("Group for student {0} ({1}) for subject {2} ({3}) not found ".format(student.ime_priimek.strip(), student.vpisna.strip(), subject, student.predmet.strip()))
                print(group.group.size)
                #if raw_input("Should I increase size of the group {0} by one (y/n)? ".format(mingroup)) == 'y':
                if True:
                    print ("OK")
                    mingroup.group.size = group.group.size + 1
                    mingroup.group.save()
                    mingroup.size = group.size + 1
                    mingroup.enrol(student.vpisna.strip())

        #raw_input("Student processed")

def getEnroledStudents(realization, groupname_group):
    students = set()
    for group in realization.groups.all():
        mygroup = groupname_group[group.short_name]
        students = students.union(set(mygroup.students))
    return students


def getEnroledStudentsDatabase(realization, studentsCache, groupset=None):
    """
    Return a set of students enrolled to a realization.
    
    Students are obtained by iterating over groups on realization and
    returning union of students in groups.
    
    If a groupset is given, students enrelled to the group with the same name in 
    the given groupset are returned. 
    """
    
    subject = realization.activity.activity.subject
    students = set()
    if realization not in studentsCache:
        for group in realization.groups.all():
            
            if groupset != None:
                # A group is a match if it has a same short name and is on the same subject 
                matched_groups = groupset.groups.filter(short_name=group.short_name, activities__in=subject.activities.all())
                if matched_groups.count() != 1:
                    continue
                else:
                    group = matched_groups.get()
                
            
            #TODO: če generacija ne gre skozi            
            if group.study == "IZ" or group.study == "EV":
                continue
            
            groupStudents = set(group.students.all().values_list("studentId", flat=True).distinct())
            students = students.union(groupStudents)
        studentsCache[realization] = students
    return studentsCache[realization]


def realizationsMustNotOverlapNew(currentTimetable, groupname_group, realizations, razor=2):
    notOverlapPairs = []
    for realization1 in realizations:
        for realization2 in realizations:
            if realization1.id >= realization2.id: continue
            sr1 = getEnroledStudents(realization1, groupname_group)
            sr2 = getEnroledStudents(realization2, groupname_group)
            problematic = sr1.intersection(sr2)
            if len(problematic) > razor:
                notOverlapPairs.append((len(problematic), realization1, realization2))


def realizationsMustNotOverlapDatabase(currentTimetable, razor, razor_dict={},
                                       groupset=None, skip_pairs=[]):
    """
    skip_pairs: a list of tuples of lecture types, which should be ignored.
    If lecture <-> lecture overlaps are to be ignored, then it should be 
    set to [('P', 'P')].
    """
    notOverlapPairs = []
    studentCache = dict()
    for realization1 in currentTimetable.realizations.filter():
        rs = currentTimetable.realizations.filter(id__gt=realization1.id)
        for realization2 in rs:
            type1 = realization1.activity.type
            type2 = realization2.activity.type
            skip = False
            for pair in skip_pairs:
                if sorted((type1, type2)) == sorted(pair):
                    skip = True
                    break
            if skip:
                continue
            r = razor_dict.get((realization1.activity.type,
                                realization2.activity.type), None)
            if r is None:
                r = razor_dict.get((realization2.activity.type,
                                    realization1.activity.type),
                                   razor)
            sr1 = getEnroledStudentsDatabase(realization1, studentCache,
                                             groupset)
            sr2 = getEnroledStudentsDatabase(realization2, studentCache,
                                             groupset)
            problematic = sr1.intersection(sr2)
            if len(problematic) > r:
                notOverlapPairs.append((len(problematic), realization1,
                                        realization2))

    l = []
    for i in notOverlapPairs:
        l.append(['ConstraintActivitiesNotOverlapping', None, [
            ['Weight_Percentage', '100'], ['Number_of_Activities', '2'],
            ['Activity_Id', str(i[1].id)],
            ['Activity_Id', str(i[2].id)]]])
    return l


def realizationsMustNotOverlap(assignments, classes, razor=2):
    notOverlapPairs = []
    for ar1 in assignments.keys():
        st1 = assignments[ar1]
        ns1 = len(classes[ar1.activity.activity.subject.code])
        for ar2 in assignments.keys():
            a1 = ar1.activity.activity
            a2 = ar2.activity.activity

            if ar1.id >= ar2.id  or (a1.type=='P' and a2.type=='P'):
                continue
            st2 = assignments[ar2]
            ns2 = len(classes[ar2.activity.activity.subject.code])
         
            numberOfProblematicStudents = len(st1 & st2)
            
            if numberOfProblematicStudents > razor or numberOfProblematicStudents > min(ns1, ns2)/4:
                notOverlapPairs.append((numberOfProblematicStudents, ar1, ar2))
                #    timetable.models.ActivityRealization.get(id=int(ar1.id)), 
                #    timetable.models.ActivityRealization.get(id=int(ar2.id))))   
                #print ar1, "<==>", ar2        
    return notOverlapPairs
















def studentsGroupsClasses(l):
    students = dict()
    studentStudy = dict()
    classesStudy = dict()
    groupsStudents = dict()
    classes = {}
    classnames = {}
    for i in l:
        studentKey = (i.vpisna, i.letnik, i.skupina)
        studentSubjects = students.get(studentKey, set())
        studentSubjects.add(i.sifra)
        
        skupina = i.skupina.strip()
        #Hadnling za UN-RI-XY : odstrani -XY del, ker ga v bazi nimamo
        if len(i.skupina.split("-"))==3:
            skupina = skupina[:-3].strip()
        
        if i.vpisna not in studentStudy:
            studentStudy[i.vpisna] = (i.letnik, skupina)
        
        # print i.vpisna, studentStudy[i.vpisna] , (i.letnik, skupina)
        assert studentStudy[i.vpisna] == (i.letnik, skupina)
        
        c = i.sifra
        classnames[c] = i.predmet[:-1]
        s = classes.get(c, set())
        s.add(i.vpisna)
        classes[c] = s

        
        groupName = "{0}_{1}".format(i.letnik, skupina)
        cs = classesStudy.get((c, groupName), set())
        cs.add(i.vpisna)
        #print (c, groupName)
        classesStudy[(c, groupName)] = cs
        
        
        gs = groupsStudents.get(groupName, set())
        gs.add(i.vpisna)
        groupsStudents[groupName] = gs 
    return (students, groupsStudents, studentStudy, classesStudy, classnames, classes)

def getNumberOfStundentsForRealization(realization, groupname):
    ret = 0
    for group in realization.groups.all():
        if group.short_name.startswith(groupname): ret += group.size

    #print "{0}, {1} -> {2}".format(realization, groupname, ret)
    return ret

def assignStudentsToRealizations(tt, students, groupsStudents, studentStudy, classesStudy, classnames, classes):
    subjectCodes = classnames.keys()
    # Realizacije na katere so študenti vpisani
    # ključ je realizacija, pod njo pa dictionary:
    # Ključ je letnik, smer, vrednost pa seznam študentov, ki smo jih že dodelili na tole.  
    assignments = dict()
    
    exercises = ["LV", "AV", "LAB", "P"]
    for subjectCode in subjectCodes:
        activities = friprosveta.models.Activity.objects.filter(activityset = tt.activityset,
            subject__code=subjectCode, type__in = exercises, locations__name__contains="Ljubljana").distinct()
        if len(activities) == 0:
            #print "No activity for subject {0}".format(subjectCode)
            continue

        #print "Subject {0}: enrolled {1}".format(subjectCode, len(classes[subjectCode]))
        for studentCode in classes[subjectCode]:
            (year, study) = studentStudy[studentCode]
            groupName = u"{0}_{1}".format(year,study)
            #print "Student {0}, {1}".format(studentCode, groupName)
            for activity in activities:
                #print u"Processing {0}, {1}".format(activity, activity.subject.name)  
                activityRealizations = timetable.models.ActivityRealization.objects.filter(activity = activity, groups__shortName__contains = groupName).distinct()
                #print u"Realizations for group {0} for {1}".format(groupName, activity), activityRealizations
                #assert len(activityRealizations) > 0
                #print "Realizations", activityRealizations
                realizationFound = False
                for realization in activityRealizations:
                    enroledStudents = assignments.get(realization, set())
                    enroledStudnetsFromStudy = filter(lambda student: student in groupsStudents[groupName], assignments.get(realization, set()))
                    
                    assignments[realization] = enroledStudents
                    freeSpace = getNumberOfStundentsForRealization(realization, groupName)
                    if len(enroledStudnetsFromStudy) >= freeSpace:
                        #print "Processing {0} for {1}: no more space".format(subjectCode, groupName)
                        continue
                        #raise  Exception ("Processing {0}: more than {1} students of {2} enrolled".format(subjectCode, freeSpace, groupName))
                    
                    #print enroledStudents
                    #print enroledStudnetsFromStudy
                    assert studentCode not in enroledStudents
                    enroledStudents.add(studentCode)
                    realizationFound = True
                    break
                if not realizationFound:
                    #raise  Exception ("Processing {0}: no more room ({1} enrolled)".format(subjectCode, len(classesStudy[(subjectCode, groupName)])))
                    pass
                    #print u"Student {0} ({1}), {2}: no more room ({3} enrolled)".format(studentCode, groupName, activity.name, len(classesStudy[(subjectCode, groupName)]))
    return assignments

def realizationsMustNotOverlap(assignments, classes, razor = 2):
    notOverlapPairs = []
    for ar1 in assignments.keys():
        st1 = assignments[ar1]
        ns1 = len(classes[ar1.activity.activity.subject.code])
        for ar2 in assignments.keys():
            a1 = ar1.activity.activity
            a2 = ar2.activity.activity

            if ar1.id >= ar2.id  or (a1.type=='P' and a2.type=='P'):
                continue
            st2 = assignments[ar2]
            ns2 = len(classes[ar2.activity.activity.subject.code])
            
            numberOfProblematicStudents = len(st1 & st2)
            
            if numberOfProblematicStudents > razor or numberOfProblematicStudents > min(ns1, ns2)/4:
                notOverlapPairs.append((numberOfProblematicStudents, ar1, ar2))
                #    timetable.models.ActivityRealization.get(id=int(ar1.id)), 
                #    timetable.models.ActivityRealization.get(id=int(ar2.id))))   
                #print ar1, "<==>", ar2        
    return notOverlapPairs
    
    
def notoverlap_gregor(tt, l, threshold = 2):
    students, groupsStudents, studentStudy, classesStudy, classnames, classes = studentsGroupsClasses(l)
    assignments = assignStudentsToRealizations(tt, students, groupsStudents, studentStudy, classesStudy, classnames, classes)
    return realizationsMustNotOverlap(assignments, classes, threshold)
    
def max_overlap(c1, c2):
    return intersection(c1, c2)

def avg_overlap(c1, c2):
    overlap = float(len(intersection(c1, c2)))
    return max(overlap/len(c1), overlap/len(c2))

def notoverlap_polz(tt, students, threshold=1):
    l = []
    studentdict = {}
    group_dict = {
        u'UN-RI-IN':u'UN-RI', 
        u'UN-RI-PO':u'UN-RI',
        u'UN-RI-RS':u'UN-RI'}
    qwerkyset = set()
    for i in students: 
        nskupina = group_dict.get(unicode(i.skupina), unicode(i.skupina.strip()))
        studentgroup = studentdict.get((i.letnik, nskupina), {})
        studentgroupsubject = studentgroup.get(i.sifra, set())
        studentgroupsubject.add(i)
        studentgroup[i.sifra] = studentgroupsubject
        studentdict[(i.letnik, nskupina)] = studentgroup
    # print studentdict.keys()
    for r1 in tt.realizations.all():
        for r2 in tt.realizations.filter(id__gt=r1.id):
            yeargroups1 = set()
            yeargroups2 = set()
            for g in r1.groups.all():
                i = g
                while i.parent is not None:
                    i = i.parent
                (year, group) = i.short_name.split('_')
                yeargroups1.add((year, group))
            for g in r2.groups.all():
                i = g
                while i.parent is not None:
                    i = i.parent
                (year, group) = i.short_name.split('_')
                yeargroups2.add((year, group))
            overlap = 0
            for studygroup in yeargroups1 & yeargroups2:
                n = min_realization_overlap(r1, r2, studentdict, studygroup, qwerkyset)
                overlap = max(overlap, n)
            if overlap >= threshold:
                l.append((overlap, r1, r2))
                # print l[-1]
    return l

def min_realization_overlap(r1, r2, students, studygroup, qwerkyset):
    otherssize = [0, 0]
    rsize = [0, 0]
    s1 = set()
    s2 = set()
    for i, (r, s) in enumerate([(r1, s1), (r2, s2)]):
        sifra = r.activity.activity.subject.code
        for g in r.groups.filter(shortName__startswith="{0}_{1}".format(*studygroup)):
            rsize[i] += g.size
            if rsize[i] > 0 and studygroup in students:
                for student in students[studygroup].get(sifra, []):
                    s.add(student.vpisna)
            else:
                if rsize[i] > 0:
                    pass
    #                print "  posebni:", studygroup, rsize[i]
    for i, activity in enumerate([r1.activity, r2.activity]):
        for r in activity.realizations.exclude(id = r1.id):
            for g in r.groups.filter(shortName__startswith="{0}_{1}".format(*students)):
                # print " others:", g
                otherssize[i] += g.size()
    if len(s1) != rsize[0]+otherssize[0] and (studygroup, r1.activity.id) not in qwerkyset:
        qwerkyset.add((studygroup, r1.activity.id))
    #    print studygroup, r1
    #    print u"  {0} estudent:{1}, najave:{2}".format(r1.activity.name, len(s1), rsize[0])
    if len(s2) != rsize[1]+otherssize[1] and (studygroup, r2.activity.id) not in qwerkyset:
        qwerkyset.add((studygroup, r2.activity.id))
    #    print studygroup, r2
    #    print u"  {0} estudent:{1}, najave:{2}".format(r2.activity.short_name, len(s2), rsize[1])
    # assert len(s1) == rsize[0] and len(s2) == rsize[1]
    
    n1 = 0
    others1 = 0
    n2 = 0 # ljudje v studygroup, ki so na r2
    others2 = 0 # vsa mesta na aktivnosti2 za studygroup - n2
    overlap = len(s1 & s2) # studentje v studygroup, ki so na obeh predmetih
    return max(0, -(max(*otherssize) - overlap))

def max_realization_overlap(r1, r2):
    pass

def avg_realization_overlap(r1, r2):
    pass
    
def mustNotOverlap(r, thresh = 10):
    l1 = []
    for i in r:
        if (i[0] > thresh):
            l1.append(i)
    return l1
    
def read_files(fnames, Line = namedtuple('Line', ['vpisna', 'upn', 'sifra', 'semester', 'letnik', 'skupina', 'kraj', 'ime_priimek','predmet', 'vpisan', 'tip_vpisa'])):
    l = []
    for fname in fnames:
        print("opening file")
        f = open(fname)
        print("file opened")
        l1 = unicode(f.read(), 'utf-16')
        print("read data")
        #s = l1.encode('utf8')
        s = l1
        for i in s.split('\n')[1:]:
            if i != '':
                l.append(Line(*i.split('\t')))
        f.close()
    return l
    
def overlaps_list(pairs):
    l = []
    for k, iar, jar in pairs:
        nl = []
        nl.append(['Activity_Id', str(iar.id)])
        nl.append(['Activity_Id', str(jar.id)])
        l.append(['ConstraintActivitiesNotOverlapping', None, [
            ['Weight_Percentage', '100']] + addNumberOf(nl, 'Number_of_Activities')])
    return l


def getMainGroupForStudyClassYear(study_shortname, classyear, current_timetable):
    groups = set()
    for group in current_timetable.groups.filter(parent=None).distinct():
        if group.study == study_shortname and int(group.classyear) == int(classyear):
            groups.add(group)
    assert len(groups) == 1, u"Exactly one top-level group per study/classyear/timetable should exist ({0}, {1}, {2}): {3}".format(
                               study_shortname, classyear, current_timetable, groups).encode("utf-8")
    return groups.pop()


def getSubjectsForGroup(group):
    subjects = set()
    for activity in group.activities.all():
        subjects.add(activity.activity.subject)
    return list(subjects)


if __name__=='__main__':
    
    if len(sys.argv) < 4:
        print("example usage:")
        print('  ./crossections.py (enrol|calculate) "FRI2012/2013, zimski semester" [../../estudent/*LJ*12_10_2011.txt ...]')
        exit(1)    

    timetableName = sys.argv[2]
    #timetableName = "FRI2011/2012, letni semester"
    currentTimetable = friprosveta.models.Timetable.objects.get(name=timetableName)
    
    action = sys.argv[1]

    l = read_files( sys.argv[3:] )
    #l = read_files(["/home/gregor/Dokumenti/Raziskovanje/urnik/git/urnik/estudent/FRI_obv_pr_LJ_LET_30_1_2012.txt"])
    
    
    lf = filter(lambda x: x.vpisan[0] == 'T', l)
    (groupname_group, subject_group, realizations) = parseGroups(currentTimetable)

    if action == "enrol":
        
                
        print ("Enroling")
        enrolStudentsToSubjects(lf, currentTimetable)

        regular_studies_years = ((1, "BUN-RI"),(2, "BUN-RI"),(1, "BVS-RI"))
        regular_studies_top_groups = dict((entry, getMainGroupForStudyClassYear(entry[1], entry[0], currentTimetable)) for entry in regular_studies_years)
        regular_studies_subjects = dict((key, getSubjectsForGroup(group)) for key, group in regular_studies_top_groups.iteritems())                
        regular_subjects_map = regular_studies_subjects
        
        padstudy = friprosveta.models.Study.objects.get(short_name="PAD")        
        fixRegularSubjectsEnrollments(currentTimetable, regular_subjects_map, padstudy)
        
    elif action == 'calculate': 
        x = realizationsMustNotOverlapDatabase(currentTimetable, razor=7)
         
        #print len(x), len(x[0])
        #xmlout = django2fet.l2El(['Insanity', None, x])
        #django2fet.indent(xmlout)
        #print ET.tostring(xmlout, encoding='UTF-8')
        #ET.tostring(realizationsMustNotOverlapNew(currentTimetable, groupname_group, realizations))
        #print x

