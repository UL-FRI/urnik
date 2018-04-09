from optparse import make_option

from django.core.management.base import BaseCommand

import friprosveta.models
from timetable.models import Group


class Command(BaseCommand):
    """
    Read groups from old timetables and create their copies in the current timetable.
    """
    args = '<source_timetable_name source_timetable_name ...>  destination_timetable_name'
    help = 'Copies groups from source timetables to the destination timetable'

    option_list = BaseCommand.option_list + (
        make_option('--delete',
                    action='store_true',
                    dest='delete',
                    default=False,
                    help='Delete existing groups in the destination timetable.'),
    )

    def handle(self, *args, **options):
        assert len(args) >= 2, "At least one destination and one source timetable must be specified."

        source_timetables = friprosveta.models.Timetable.objects.filter(name__in=args[:-1])
        destination_timetable = friprosveta.models.Timetable.objects.get(name=args[-1])

        if options['delete']:
            destination_timetable.groups.all().delete()

        self.copy_groups(source_timetables, destination_timetable)

    def copy_groups(self, source_timetables, destination_timetable):

        groupset = destination_timetable.groupset
        for activity in destination_timetable.activities.all():
            activity = activity.activity
            subject = activity.subject
            old_activity = None
            for previous in source_timetables.all():
                if previous.subjects.filter(code=subject.code).count() == 1:
                    pactivities = subject.activities.filter(activityset=previous.activityset, type=activity.type)
                    if pactivities.count() > 1:
                        # print "More than one activity for {0} of type {1} found in {2}".format(subject, activity.type, previous)
                        old_activity = pactivities.all()[0]
                    if pactivities.count() == 1:
                        old_activity = pactivities.get()
                if old_activity is not None:
                    activity.groups.add(*self.copy_groups_for_activity(old_activity, groupset))

            if old_activity is None:
                print("No old groups for activity {0}".format(activity))

                # Return a copy of the group.

    # Parents are created recursively.
    # If group already exists no new copy is created.
    def copy_group(self, old_group, new_groupset):
        assert new_groupset.groups.filter(
            name=old_group.name).count() <= 1, "More than one group with name {0} found".format(old_group.name)
        if new_groupset.groups.filter(name=old_group.name).count() == 0:
            # Create new group
            new_group = Group(name=old_group.name, short_name=old_group.short_name, size=old_group.size,
                              groupset=new_groupset)
            # Get parent
            if old_group.parent != None:
                new_parent = self.copy_group(old_group.parent, new_groupset)
                new_group.parent = new_parent
            new_group.save()
        elif new_groupset.groups.filter(name=old_group.name).count() == 1:
            # Return old group
            # print "Returning old group"
            new_group = new_groupset.groups.get(name=old_group.name)

        if old_group.parent is not None and new_group.parent is None:
            new_parent = self.copy_group(old_group.parent, new_groupset)
            print(new_parent)
            print("Napaka")
            new_group.parent = new_parent
            new_group.save()

        return new_group

    def copy_groups_for_activity(self, old_activity, new_groupset):
        return (self.copy_group(old_group, new_groupset) for old_group in old_activity.groups.all())
