import sys
import json
import urllib2
from _collections import defaultdict

from django.core.management.base import BaseCommand
from django.conf import settings

from friprosveta.models import StudentEnrollment, Timetable, Study, Student
from friprosveta.models import Subject
from timetable.models import Group



class Command(BaseCommand):
    '''
    Re-assign students to already existing groups
    '''
    args = 'timetable_slug'
    help = '''
THIS COMMAND DOES NOT WORK YET

Re-fill groups from the current StudentEnrollments.
First remove the students who have left any subject the group is on
then re-fill groups up to their capacity with new students,
then, if no un-enrolled students remain for a given group, reduce its size,
finally create new groups for the remaining students.
'''

    def handle(self, *args, **options):
        if len(args) < 1:
            print("See help")
            sys.exit()

        currentTimetable = Timetable.objects.get(slug=args[0])
        print u"timetable: {}".format(currentTimetable)
        groupset = currentTimetable.groupset
        modified_groups = set()
        for activity in currentTimetable.activities.all():
            activity = activity.activity
            enrollments = StudentEnrollment.objects.filter(
                    groupset = groupset,
                    subject = activity.subject)
            peer_groups = set(activity.groups.filter(groupset = groupset))
            all_group_sizes = 0
            activity_students = set()
            for g in peer_groups:
                activity_students = activity_students.union(set(g.students.all()))
            enrollment_students = set([e.student for e in enrollments])
            if enrollment_students != activity_students:
                print activity.id, activity.short_name
            free_group_space = defaultdict(int)
            for s in activity_students.difference(enrollment_students):
                g = set(s.groups.all()).intersection(peer_groups)
                assert len(g) == 1
                g = list(g)[0]
                print "    - ", s, g
                free_group_space[g] += 1
                g.students.remove(s)
                modified_groups.add(g)
            for s in enrollment_students.difference(activity_students):
                print "    + ", s
                e = enrollments.get(student = s)
                suggested_group = None
                for g in peer_groups:
                    split_g_short = g.short_name.split('_')
                    if split_g_short[:2] == [unicode(e.classyear), e.study.short_name]:
                        suggested_group = g
                        if free_group_space[g] > 0:
                            free_group_space[g] -= 1
                            break 
                if suggested_group is None:
                    print "CREATE GROUP"
                    short_name = '{}_{}_{}'.format(e.classyear, e.study, activity.subject.short_name)
                    if activity.type != 'P':
                        short_name += '_00'
                    g, created = Group.objects.get_or_create(short_name = short_name, groupset = groupset)
                    if created:
                        g.parent = Group.objects.filter(shortName__startswith=u'{}_{}'.format(e.classyear, e.study), parent=None)[0]
                        g.size = 0
                    g.save()
                    activity.groups.add(g)
                    suggested_group = g
                    modified_groups.add(g)
                print "        ", "->", suggested_group
                suggested_group.students.add(s)
            for g in modified_groups:
                g.size = len(g.students.all())
                g.save()
            # print activity.name

