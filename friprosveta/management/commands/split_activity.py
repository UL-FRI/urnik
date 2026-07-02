from django.core.management.base import BaseCommand

import friprosveta.models
from friprosveta.services.activity_splitting import split_activity


class Command(BaseCommand):
    """
    Split activity into multiple parts.
    """

    args = "timetable_slug activity_id duration_1 duration_2 ..."
    help = "Split activity."

    def add_arguments(self, parser):
        parser.add_argument("tt_slug", nargs=1, type=str, help="timetable slug")
        parser.add_argument("activity_id", nargs=1, type=int, help="activity id")
        parser.add_argument(
            "durations", nargs="+", type=int, help="durations of splits"
        )

    def handle(self, *args, **options):
        timetable = friprosveta.models.Timetable.objects.get(slug=options["tt_slug"][0])
        activity = friprosveta.models.Activity.objects.get(pk=options["activity_id"][0])

        splits = options["durations"]
        split_activity(timetable, activity, splits)
