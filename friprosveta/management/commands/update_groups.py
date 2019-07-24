import json
import sys
import traceback
from optparse import make_option

import urllib2
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from enroll_students_to_subjects import get_study_classyear
from friprosveta.utils.utils import Utils

import friprosveta


class Command(BaseCommand):
    """
    Update groups for a given timetable based on enrolments on subjects
    (see enrol_students_to_subjects).
    """
    args = 'update_groups timetable_slug studis_year'
    help = 'Update groups for the given timetable. Data about subjects (optional, classyear...) \
is read from studis. '
    option_list = BaseCommand.option_list + (
        make_option('--testrun',
                    action='store_true',
                    dest='testrun',
                    default=False,
                    help='Run without database modification'),
        make_option('--subject',
                    action='store',
                    dest='subject',
                    help='Only update groups for the given subject. Subject is given by code.'),
    )

    def handle(self, *args, **options):
        if len(args) != 2:
            print("See help.")
            sys.exit()

        timetable = friprosveta.models.Timetable.objects.get(slug=args[0])
        studis_year = int(args[1])

        token = settings.STUDIS_API_TOKEN
        headers = {'Content-Type': 'application/json',
                   'AUTHENTICATION_TOKEN': token}
        baseurl = settings.STUDIS_API_BASE_URL

        url = baseurl + '/studijapi/{0}/studijskodrevo'.format(studis_year)
        data = json.loads(urllib2.urlopen(urllib2.Request(url, None, headers)).read())
        studijsko_drevo = {vnos['id']: vnos for vnos in data}

        url = baseurl + '/studijapi/{0}/izvajanjepredmeta'.format(studis_year)
        izvajanja = json.loads(urllib2.urlopen(urllib2.Request(url, None, headers)).read())

        url = baseurl + '/studijapi/{0}/predmet'.format(studis_year)
        data = json.loads(urllib2.urlopen(urllib2.Request(url, None, headers)).read())
        subjects = {subject['id']: subject for subject in data}

        activities = dict()
        for izvajanje in izvajanja:
            study, classyear = get_study_classyear(studijsko_drevo, izvajanje['predmetnik'])
            if study is None:
                continue
            subject = subjects[izvajanje['idpredmet']]
            if subject['sifra'] not in activities:
                activities[subject['sifra']] = dict()
            activities[subject['sifra']][(study, classyear)] = izvajanje

        subjects = timetable.subjects
        if options['subject'] is not None:
            subjects = friprosveta.models.Subject.objects.filter(code=options['subject'])

        for subject in subjects:
            try:
                studis_activity = activities[subject.code]
                self.update_groups_for_subject(subject, timetable,
                                               options['testrun'],
                                               studis_activity,
                                               never_delete_studies=['FKKT-UNI', 'FKKT-VS']
                                               )
            except Exception as e:
                print("Error updating groups for subject {0}: {1}".format(subject, repr(e)).encode("utf-8"))
                traceback.print_exc()

    @transaction.atomic
    def update_groups_for_subject(self, subject, timetable, testrun,
                                  studis_activity, safe_to_delete_studies=['PAD', 'UN-RI'],
                                  never_delete_studies=['FKKT-UNI', 'FKKT-VS', 'BUN-UI', 'BUN-MM', 'BM-RM', 'BM-MM']):
        """
        Update groups for a given subject for a given timetable.
        This method only updates groups on activities in existing activitySet.
        It does not change activity data in any way, except its group list.
        Beware: if some groups are deleted, empty realizations
        (realizations without groups) will remain.
        """

        oldutils = Utils()
        assert timetable.subjects.filter(id=subject.id).count() == 1, "Subject {0} must exist \
in the timetable {1}".format(subject, timetable).encode("utf-8")
        for activity in subject.activities.filter(activityset=timetable.activityset):
            print("Processing {0}".format(activity.short_name))
            groups = oldutils.updateGroupsForActivity(activity=activity,
                                                      timetable=timetable,
                                                      studis_studies=studis_activity)
            updated_groups_ids = []
            if activity.type == 'P':
                activity.groups.add(*groups.keys())
                updated_groups_ids = map(lambda group: group.id, groups.keys())
            else:
                for values in groups.values():
                    activity.groups.add(*values)
                    updated_groups_ids += map(lambda group: group.id, values)
            groups_to_remove = activity.groups.filter(groupset=timetable.groupset)
            groups_to_remove = groups_to_remove.exclude(id__in=updated_groups_ids)
            print("Remove groups from activity: {0}".format(groups_to_remove))
            for group in groups_to_remove.all():
                if group.study in never_delete_studies:
                    print('Group {0} study in never_delete_studies, not removing'.format(group))
                    continue
                if friprosveta.models.StudentEnrollment.objects.filter(subject=subject,
                                                                       groupset=timetable.groupset,
                                                                       study__short_name=group.study).count() == 0:
                    if group.study in safe_to_delete_studies or raw_input(
                            'No enrolment data found for group {0}. Delete (Y/n)? '.format(group)) in ['y', 'Y']:
                        print('Deleting')
                        activity.groups.remove(group)
                else:
                    print('Deleting')
                    activity.groups.remove(group)
        if testrun:
            raise Exception('Testrun')
