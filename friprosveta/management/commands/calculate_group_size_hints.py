from django.core.management.base import BaseCommand
from friprosveta.models import GroupSizeHint, Timetable, ENROLMENTTYPES, StudentEnrollment


class Command(BaseCommand):
    '''
    Calculate group size hints from enrollments.
    It requires that:
    1) Groups for all lectures are already created.
    2) There exists one group named {{subject.code}}_PAD for every subject.
    Students with enrollment type 4, 26 are enrolled into
    'regular' groups, others into PAD group.
    '''
    args = 'calculate_group_size_hint timetable method_name'
    help = '''Usage:
calculate_group_size_hint timetable_slug method_name

Timetable represents the timetable students are enrolling into.

Method name is the name of the method in GroupSizeHint object.
If prior entries with this method name exist they will be overwritten.

Groups with sizes 0 are not stored. It is not possible to know whether 
enrollments are still missing or actually no student for this group is enrolled.  
'''

    def add_arguments(self, parser):
        parser.add_argument('timetable_slug', type=str)
        parser.add_argument('method_name', nargs=1, type=str)

    def handle(self, *args, **options):
        tt = Timetable.objects.get(slug=options['timetable_slug'])
        method_name = options['method_name'][0]
        GroupSizeHint.objects.filter(method=method_name).delete()

        for a in tt.activities.filter(type='P'):
            enrollment_types = [4, 26]
            for group in a.groups.all().exclude(shortName__contains='PAD'):
                if GroupSizeHint.objects.filter(group=group, method=method_name).count() == 0:
                    GroupSizeHint.size_from_enrollments(
                        group,
                        tt.groupset,
                        enrollment_types=enrollment_types,
                        method=method_name
                    )
            enrollment_types = sorted([e[0] for e in ENROLMENTTYPES if e[0] not in [4, 26]])
            try:
                group = a.groups.get(shortName__contains='PAD')
                if GroupSizeHint.objects.filter(group=group, method=method_name).count() == 0:
                    se = StudentEnrollment.objects.filter(
                        groupset=tt.groupset,
                        subject=a.subject,
                        enrollment_type__in=enrollment_types
                    )
                    GroupSizeHint(
                        method=method_name,
                        size=se.count(),
                        group=group,
                    ).save()
            except:
                print("No PAD group for {}".format(a.name, a.type))
        GroupSizeHint.objects.filter(size=0, method=method_name).delete()