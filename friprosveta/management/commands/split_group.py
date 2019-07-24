from django.core.management.base import BaseCommand
from django.db import transaction

import timetable.models


class Command(BaseCommand):
    """
    Split group into multiple groups of the size 1.
    """
    args = 'group_id'
    help = 'Split group. Group should be assigned to exactly 1 activity. New group will be assigned to the same activity.'

    @transaction.atomic
    def handle(self, *args, **options):
        assert len(args) == 1, 'Expected at least one argument.'
        group = timetable.models.Group.objects.get(pk=args[0])
        assert group.activities.count() == 1, 'Group should be assigned to exactly one activity.'
        activity = group.activities.get()
        last_underscore = group.short_name.rfind('_')
        basename = group.short_name[:last_underscore]
        last_space = group.name.rfind(' ')
        baselongname = group.name[:last_space]
        group_number = 1
        groups = activity.groups.filter(short_name__contains=basename)
        start = max([int(g.groupnum) for g in groups]) + 1
        parent = group.parent
        groupset = group.groupset
        for i in range(group.size - 1):
            short_name = '{0}_{1:02}'.format(basename, start + i)
            name = '{0} {1}'.format(baselongname, start + i)
            g = timetable.models.Group(name=name, short_name=short_name, parent=parent, groupset=groupset, size=1)
            g.save()
            g.activities.add(*group.activities.all())
        group.size = 1
        group.save()
