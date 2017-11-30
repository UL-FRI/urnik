from django.core.management.base import BaseCommand
from friprosveta.models import GroupSizeHint


class Command(BaseCommand):
    '''
    Calculate group size hints from enrollments.
    It requires that:
    1) Groups for all lectures are already created.
    2) There exists one group named {{subject.code}}_PAD for every subject.
    Students with enrollment type 4, 26 are enrolled into
    'regular' groups, others into PAD group.
    '''
    args = 'update_group_sizes_from_hints method_name'
    help = '''Usage:
update_group_sizes_from_hints method_name

Set sizes of groups according to hints.
'''

    def add_arguments(self, parser):
        parser.add_argument('method_name', nargs=1, type=str)

    def handle(self, *args, **options):
        method_name = options['method_name'][0]
        for e in GroupSizeHint.objects.filter(method=method_name):
            e.group.size = e.size
            e.group.save()