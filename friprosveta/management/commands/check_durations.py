from django.core.management.base import BaseCommand, CommandError

from friprosveta.models import Timetable


class Command(BaseCommand):
    help = "Report realized activities whose duration differs from P=3, LV=2, AV=2."

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug")
        parser.add_argument(
            "--exclude-subject",
            action="append",
            default=[],
            help="Subject code to omit from the report. May be repeated.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when duration problems are found.",
        )

    def handle(self, *args, **options):
        timetable = Timetable.objects.get(slug=options["timetable_slug"])
        expected_durations = {"P": 3, "LV": 2, "AV": 2}
        excluded_subjects = set(options["exclude_subject"])
        problems = []

        for activity_type, expected_duration in expected_durations.items():
            activities = timetable.activities.filter(type=activity_type).exclude(
                duration=expected_duration
            )
            for activity in activities.filter(realizations__isnull=False).distinct():
                if activity.subject.code not in excluded_subjects:
                    problems.append(activity)

        if not problems:
            self.stdout.write("All realized P, LV, and AV activities have expected durations.")
            return

        for activity in problems:
            self.stdout.write(
                "{} {}: duration {} (expected {})".format(
                    activity.subject.code,
                    activity.type,
                    activity.duration,
                    expected_durations[activity.type],
                )
            )
        summary = "Found {} activity duration problem(s).".format(len(problems))
        self.stdout.write(summary)
        if options["strict"]:
            raise CommandError(summary)
