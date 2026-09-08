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

    args = "update_subgroups_from_hints timetable_slug method_name_1 method_name_2 ..."
    help = """Usage:
update_subgroups_from_hints timetable_slug method_name [--strategy strategy_name]

Update subgroups of groups on lectures for the given timetable.

There can be more than one method: if no entry for one method exists,
the next one is tried.

"""

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug", type=str)
        parser.add_argument("method_names", nargs="+", type=str)
        parser.add_argument(
            "--strategy",
            dest="strategy_name",
            default="max",
            help="Strategy used to combine group size hints. See "
            "GroupSizeHint.strategy for the available options (default: max).",
        )

    def handle(self, *args, **options):
        tt = Timetable.objects.get(slug=options["timetable_slug"])
        method_names = options["method_names"]
        strategy_name = options["strategy_name"]
        print(method_names)
        for subject in tt.subjects.all():
            try:
                subject.update_or_create_subgroups_from_hints(
                    activityset=tt.activityset,
                    methods=method_names,
                    strategy_name=strategy_name,
                )
            except Exception as error:
                print("Error: while processing {}: {}".format(subject, error))
