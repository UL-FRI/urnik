from django.core.management.base import BaseCommand

import friprosveta.models


class Command(BaseCommand):
    """
    Export students in groups for a subject
    """

    args = "timetable_slug subject_code"
    help = "Export students by groups"

    # option_list = BaseCommand.option_list + (
    #    make_option('--delete',
    #        action='store_true',
    #        dest='delete',
    #        default=False,
    #        help='Delete existing groups in the destination timetable.'),
    #    )

    def handle(self, *args, **options):
        assert (
            len(args) >= 2
        ), "Usage: timetable_slug subject_code [subject_code2] [subject_code3...]"

        tt = friprosveta.models.Timetable.objects.get(slug=args[0])
        subjects = friprosveta.models.Subject.objects.filter(code__in=args[1:])
        self.print_groups(tt, subjects)

    def print_groups(self, tt, subjects):
        for subject in subjects:
            print("{0} ({1})".format(subject.name, subject.code))
            for allocation in tt.allocations.filter(
                activityRealization__activity__activity__subject=subject
            ).distinct():
                s = "; ".join(
                    [
                        "{0} {1}".format(t.user.first_name, t.user.last_name)
                        for t in allocation.activityRealization.teachers.all()
                    ]
                )
                print(
                    "    {0} {1}-{2}, {3}: {4}".format(
                        allocation.day,
                        allocation.start,
                        allocation.end,
                        allocation.classroom,
                        s,
                    )
                )
                students = set()
                for group in allocation.activityRealization.groups.distinct():
                    for student in group.students.all():
                        students.add(
                            "{1} {2} ({0})".format(
                                student.studentId, student.name, student.surname
                            )
                        )
                print("        " + "\n        ".join(students))
