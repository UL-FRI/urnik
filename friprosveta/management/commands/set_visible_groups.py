from django.core.management.base import BaseCommand

from friprosveta.models import Timetable


class Command(BaseCommand):
    help = "Show top-level groups in navigation and hide synthetic groups."

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug")

    def handle(self, *args, **options):
        timetable = Timetable.objects.get(slug=options["timetable_slug"])
        groups = timetable.groups.filter(parent__isnull=True)
        groups.update(visible_in_navigation=True)
        hidden_count = groups.filter(
            short_name__startswith="99"
        ).update(visible_in_navigation=False)
        hidden_count += timetable.groups.filter(
            short_name="VSI_PADALCI"
        ).update(visible_in_navigation=False)
        self.stdout.write(
            "Updated {} top-level group(s); hid {} synthetic group(s).".format(
                groups.count(), hidden_count
            )
        )
