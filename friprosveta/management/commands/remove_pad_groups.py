from django.core.management.base import BaseCommand

from friprosveta.models import Timetable


def is_pad_group(group):
    return group.short_name == "VSI_PADALCI" or group.short_name.endswith("_PAD")


class Command(BaseCommand):
    help = (
        "Remove PAD placeholder groups from lecture realizations while preserving "
        "their contribution to intended size."
    )

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report groups that would be removed without changing data.",
        )

    def handle(self, *args, **options):
        timetable = Timetable.objects.get(slug=options["timetable_slug"])
        dry_run = options["dry_run"]
        removed_count = 0

        for realization in timetable.realizations.filter(activity__type="P").prefetch_related(
            "groups"
        ):
            pad_groups = [group for group in realization.groups.all() if is_pad_group(group)]
            if not pad_groups:
                continue
            if dry_run:
                self.stdout.write(
                    "Would remove {} from realization {}.".format(
                        ", ".join(group.short_name for group in pad_groups), realization.id
                    )
                )
            else:
                realization.intended_size = max(
                    realization.intended_size, realization.size
                )
                realization.save(update_fields=["intended_size"])
                realization.groups.remove(*pad_groups)
                self.stdout.write(
                    "Removed {} from realization {}.".format(
                        ", ".join(group.short_name for group in pad_groups), realization.id
                    )
                )
            removed_count += len(pad_groups)

        action = "Would remove" if dry_run else "Removed"
        self.stdout.write("{} {} PAD group assignment(s).".format(action, removed_count))
