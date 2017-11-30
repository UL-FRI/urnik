from optparse import make_option
import logging
from django.core.management.base import BaseCommand, CommandError
from timetable.models import TagValuePreference, Timetable, Tag

logger = logging.getLogger('friprosveta')


class Command(BaseCommand):
    """
    Add tags to activities.
    """
    help = """Add default teacher tags for the given timetable.
If teacher option is specified only tags for the given teacher are set.
When rm_prefs option is given old time preferences and tags are deleted and \
default TagValuePreferences are created.
Usage: add_tags [--teacher=teacher_id] [--rm_prefs] timetable_slug"""
    option_list = BaseCommand.option_list + \
        (make_option(
            '--teacher',
            type='int',
            dest='teacher_id',
            help='Only set preferences for the user with the given id'),
         make_option(
            '--rm_prefs',
            action='store_true',
            dest='remove_old_preferences',
            default=False,
            help='Remove old preferences for tags. This option is only valid when option \
pset is also given, otherwise it is silently ignored.'),
         )

    def handle(self, *args, **options):
        if len(args) < 1:
            raise CommandError(Command.help)
        timetable = Timetable.objects.get(slug=args[0])
        self.prepare()
        teachers = timetable.teachers
        if options['remove_old_preferences']:
            self.remove_old_preferences(timetable)
        if options['teacher_id'] is not None:
            teachers = teachers.filter(pk=options['teacher_id'])
        self.add_default_preference_tags(teachers.all(), timetable)

    def remove_old_preferences(self, timetable):
        TagValuePreference.objects.filter(
            tag__name__in=self.safe_to_delete,
            preferenceset=timetable.preferenceset,
        ).delete()
        self.recreate_tag_time_preferences(timetable)
        for teacher in timetable.teachers.all():
            teacher.tags.clear()

    def recreate_tag_time_preferences(self, timetable):
        level = 'WANT'
        for value, tag in self.max_hours_daily.iteritems():
            preference = TagValuePreference(
                weight=1,
                value=value,
                name='MAXHOURSDAY',
                tag=tag,
                preferenceset=timetable.preferenceset,
                level=level,
            )
            preference.save()
        for value, tag in self.max_days_weekly.iteritems():
            preference = TagValuePreference(
                weight=1,
                value=value,
                name='MAXDAYSWEEK',
                tag=tag,
                preferenceset=timetable.preferenceset,
                level=level,
            )
            preference.save()

    def add_default_preference_tags(self, teachers, timetable):
        for teacher in teachers:
            tags = self.teacher_tags(timetable, teacher)
            teacher.tags.add(*tags)

    def prepare(self):
        self.safe_to_delete = [
            '3 ure na dan',
            '4 ure na dan',
            '5 ur na dan',
            '6 ur na dan',
            '8 ur na dan',
            '10 ur na dan',
            '2 dni na teden',
            '3 dni na teden',
            '4 dni na teden',
            '2 do upokojitve',
        ]
        self.max_hours_daily = {
            10: '10 ur na dan',
            8: '8 ur na dan',
            6: '6 ur na dan',
            5: '5 ur na dan',
            4: '4 ure na dan',
            3:  '3 ure na dan',
        }
        self.max_days_weekly = {
            4: '4 dni na teden',
            3: '3 dni na teden',
            2: '2 dni na teden',
        }

        for k, v in self.max_hours_daily.iteritems():
            self.max_hours_daily[k] = Tag.objects.get(name=v)
        for k, v in self.max_days_weekly.iteritems():
            self.max_days_weekly[k] = Tag.objects.get(name=v)

    def teacher_tags(self, timetable, teacher):
        def teacher_hours(teacher):
            hours = 0
            realizations = teacher.activity_realizations
            realizations = realizations.filter(activity__activityset=timetable.activityset)
            for realization in realizations:
                hours += realization.duration
            return hours

        def max_days(teacher):
            if teacher_hours(teacher) <= 12:
                return 3
            else:
                return 4

        def max_hours(teacher):
            activities = teacher.activities.all()
            activities = activities.filter(activityset=timetable.activityset)
            if activities.filter(type='P').exists():
                return 5
            else:
                return 6

        return [
            self.max_days_weekly[max_days(teacher)],
            self.max_hours_daily[max_hours(teacher)],
        ]
