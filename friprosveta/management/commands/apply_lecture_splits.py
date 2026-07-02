from django.core.management.base import BaseCommand

import friprosveta.models
from friprosveta.services.activity_splitting import split_activity


SPLIT_DURATIONS = {
    "2-1": [2, 1],
    "1-1-1": [1, 1, 1],
}


class Command(BaseCommand):
    """
    Apply saved lecture split preferences before exporting/generating a timetable.
    """

    help = "Split 3-hour lecture activities according to saved teacher preferences."

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug", type=str, help="Timetable slug")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would be split without changing the database.",
        )

    def handle(self, *args, **options):
        timetable = friprosveta.models.Timetable.objects.get(
            slug=options["timetable_slug"]
        )
        dry_run = options["dry_run"]
        activities = list(
            friprosveta.models.Activity.objects.filter(
                activityset=timetable.activityset,
                type="P",
                duration=3,
                lecture_split__in=SPLIT_DURATIONS.keys(),
            ).order_by("subject__code", "short_name")
        )

        if not activities:
            self.stdout.write("No lecture split preferences to apply.")
            return

        for activity in activities:
            splits = SPLIT_DURATIONS[activity.lecture_split]
            self.stdout.write(
                "{}: {} -> {}".format(activity, activity.duration, "+".join(map(str, splits)))
            )
            if not dry_run:
                split_activity(timetable, activity, splits)

        if dry_run:
            self.stdout.write("Dry run complete; no changes made.")
        else:
            self.stdout.write("Lecture split preferences applied.")
