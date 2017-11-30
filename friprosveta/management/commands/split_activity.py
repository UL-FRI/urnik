from django.core.management.base import BaseCommand
from django.db import transaction

import friprosveta.models
import timetable.models


class Command(BaseCommand):
    '''
    Split activity into multiple parts.
    '''
    args = 'timetable_slug activity_id duration_1 duration_2 ...'
    help = 'Split activity.'

    def add_arguments(self, parser):
        parser.add_argument('tt_slug', nargs=1, type=str, help="timetable slug")
        parser.add_argument('activity_id', nargs=1, type=int, help="activity id")
        parser.add_argument('durations', nargs='+', type=int, help="durations of splits")


    def handle(self, *args, **options):
        timetable = friprosveta.models.Timetable.objects.get(slug=options['tt_slug'][0])
        activity = friprosveta.models.Activity.objects.get(pk=options['activity_id'][0])

        splits = options['durations']
        self.split_activity(timetable, activity, splits)

    def split_activity(self, tt, activity, splits):
        if activity.duration != sum(splits):
            raise Exception("Activity {0} with duration {1} cannot be\
split into {3}".format(activity, activity.duration, splits))

        with transaction.atomic():
            activity.duration = splits[0]
            activity.save()
            act = activity
            all_activities = [act]
            for split in splits[1:]:
                activity = friprosveta.models.Activity(name=act.name, short_name=act.short_name,
                                                       type=act.type, duration=split,
                                                       subject=act.subject,
                                                       activityset=act.activityset,
                                                       lecture_type=act.lecture_type)
                activity.save()
                activity.locations.add(*act.locations.all())
                activity.requirements.add(*act.requirements.all())
                activity.groups.add(*act.groups.all())
                activity.mustNotOverlap.add(*act.mustNotOverlap.all())
                activity.before.add(*act.before.all())
                activity.tags.add(*act.tags.all())
                activity.save()
                for teacher in act.teachers.all():
                    activity.teachers.add(teacher)
                for ar in act.realizations.all():
                    nar = timetable.models.ActivityRealization(activity=activity)
                    nar.save()
                    nar.groups.add(*act.groups.all())
                    nar.teachers.add(*act.teachers.all())
                all_activities.append(activity)

            t12urmed = timetable.models.Tag(name=u"12 ur med {0}".format(act.subject.short_name))
            t12urmed.save()
            t12urmed.activities.add(*all_activities)
            tvp = timetable.models.TagValuePreference(tag=t12urmed, value=13, weight=1.0,
                                                      level=u"WANT", name=u'MINACTIVITYGAP',
                                                      preferenceset=tt.preferenceset)
            tvp.save()
