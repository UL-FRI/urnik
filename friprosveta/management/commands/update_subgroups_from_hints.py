from django.core.management.base import BaseCommand

from friprosveta.models import Timetable


class Command(BaseCommand):
    """
    Calculate group size hints from enrollments.
    It requires that:
    1) Groups for all lectures are already created.
    2) There exists one group named {{subject.code}}_PAD for every subject.
    Students with enrollment type 4, 26 are enrolled into
    'regular' groups, others into PAD group.
    """
    args = 'update_subgroups_from_hints timetable_slug method_name_1 method_name_2 ...'
    help = '''Usage:
update_subgroups_from_hints timetable_slug method_name

Update subgroups of groups on lectures for the given timetable.

There can be more than one method: if no entry for one method exists,
the next one is tried. 

'''

    def add_arguments(self, parser):
        parser.add_argument('timetable_slug', type=str)
        parser.add_argument('method_names', nargs='+', type=str)

    def handle(self, *args, **options):
        tt = Timetable.objects.get(slug=options['timetable_slug'])
        method_names = options["method_names"]
        print(method_names)
        for subject in tt.subjects.all():
            try:
                subject.create_subgroups_from_hints(activityset=tt.activityset, methods=method_names)
            except:
                print("Error: while processing {}".format(subject))
