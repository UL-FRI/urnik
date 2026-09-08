from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from timetable.models import ActivitySet, GroupSet, PreferenceSet, Timetable


class Command(BaseCommand):
    help = (
        "Create a new timetable with fresh activity, group, and preference sets, "
        "reusing the classroom set from an existing timetable."
    )

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug")
        parser.add_argument("name")
        parser.add_argument("source_timetable_slug")
        parser.add_argument(
            "--public",
            action="store_true",
            help="Make the new timetable publicly visible.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        timetable_slug = options["timetable_slug"]
        if Timetable.objects.filter(slug=timetable_slug).exists():
            raise CommandError("A timetable with slug '{}' already exists.".format(timetable_slug))

        source_timetable = Timetable.objects.filter(
            slug=options["source_timetable_slug"]
        ).first()
        if source_timetable is None:
            raise CommandError(
                "Source timetable '{}' does not exist.".format(
                    options["source_timetable_slug"]
                )
            )
        if source_timetable.classroomset is None:
            raise CommandError("Source timetable has no classroom set.")

        name = options["name"]
        activityset = ActivitySet.objects.create(
            slug="{}-activities".format(timetable_slug), name="{} activities".format(name)
        )
        preferenceset = PreferenceSet.objects.create(
            slug="{}-preferences".format(timetable_slug),
            name="{} preferences".format(name),
        )
        groupset = GroupSet.objects.create(
            slug="{}-groups".format(timetable_slug),
            name="{} groups".format(name),
            created=datetime.now(),
        )
        timetable = Timetable.objects.create(
            slug=timetable_slug,
            name=name,
            public=options["public"],
            activityset=activityset,
            preferenceset=preferenceset,
            groupset=groupset,
            classroomset=source_timetable.classroomset,
        )
        self.stdout.write(
            "Created timetable '{}' with classroom set '{}' from '{}'.".format(
                timetable.slug,
                source_timetable.classroomset.slug,
                source_timetable.slug,
            )
        )
