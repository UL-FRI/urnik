from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from friprosveta.models import ActivityRealization, GroupSizeHint, Study, Timetable
from friprosveta.services.group_coverage import missing_realization_group_messages
from friprosveta.services.manual_activities import apply_manual_activities
from friprosveta.studis import Najave, Studij
from timetable.models import Group, Resource


class Command(BaseCommand):
    help = "Synchronize Studis groups and assign them to realizations before OR-Tools generation."

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug", type=str)
        parser.add_argument("year", type=str)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--previous-timetable-slug", type=str)
        parser.add_argument(
            "--hint-source",
            action="append",
            dest="hint_sources",
            choices=(
                "previous-enrollments",
                "previous-students",
                "current-enrollments",
                "previous-size",
            ),
        )
        parser.add_argument(
            "--hint-strategy",
            default="max",
            choices=("first", "first-non-zero", "max", "max-non-zero", "max-group"),
        )
        parser.add_argument("--exclude-study", action="append", default=[])

    def handle(self, *args, **options):
        timetable = Timetable.objects.get(slug=options["timetable_slug"])
        year = options["year"]
        dry_run = options["dry_run"]
        previous_timetable_slug = options["previous_timetable_slug"]
        hint_sources = list(
            dict.fromkeys(
                options["hint_sources"]
                or (
                    ["current-enrollments", "previous-enrollments"]
                    if previous_timetable_slug
                    else ["current-enrollments"]
                )
            )
        )
        prior_sources = {
            "previous-enrollments",
            "previous-students",
            "previous-size",
        }
        if prior_sources.intersection(hint_sources) and not previous_timetable_slug:
            raise CommandError(
                "--previous-timetable-slug is required for prior hint sources."
            )
        previous_timetable = None
        if previous_timetable_slug:
            previous_timetable = Timetable.objects.get(slug=previous_timetable_slug)
        previous_groupset = (
            previous_timetable.groupset if previous_timetable is not None else None
        )
        source_methods = {
            "previous-enrollments": "enrollments from {0} for types [4, 26]".format(
                previous_groupset
            ),
            "previous-students": "group from {0} with enrollment types [4, 26]".format(
                previous_groupset
            ),
            "current-enrollments": "enrollments from {0} for types [4, 26]".format(
                timetable.groupset
            ),
            "previous-size": "group from {0} from size".format(previous_groupset),
        }
        methods = [source_methods[hint_source] for hint_source in hint_sources]
        studij = Studij(year)
        najave = Najave(year)

        with transaction.atomic():
            obligatory_curricula = [
                (subject, predmetnik)
                for subject in timetable.subjects.all()
                for izvajanje, predmetnik in subject.get_studis_predmetnik(
                    year, studij=studij, najave=najave
                )
                if izvajanje["obvezen"]
            ]
            complete_curricula = [
                (subject, predmetnik)
                for subject, predmetnik in obligatory_curricula
                if len(predmetnik) == 5
            ]
            incomplete_curricula = [
                (subject, predmetnik)
                for subject, predmetnik in obligatory_curricula
                if len(predmetnik) != 5
            ]
            required_study_names = {
                najave.get_study_short_name(predmetnik)
                for _, predmetnik in complete_curricula
            }
            existing_study_names = set(
                Study.objects.filter(short_name__in=required_study_names).values_list(
                    "short_name", flat=True
                )
            )
            missing_study_names = sorted(required_study_names - existing_study_names)
            for study_name in missing_study_names:
                Study.objects.create(short_name=study_name, name=study_name)

            complete_subject_ids = {subject.id for subject, _ in complete_curricula}
            for subject in timetable.subjects.filter(id__in=complete_subject_ids):
                subject.create_obligatory_top_level_groups_from_studis_predmetnik(
                    year, timetable, studij=studij, najave=najave
                )
                subject.create_non_obligatory_top_level_groups_from_studis_predmetnik(
                    year, timetable, studij=studij, najave=najave
                )

            for subject, predmetnik in incomplete_curricula:
                study_data = predmetnik[2]
                study_name = study_data["sifra"]
                if not study_name:
                    raise CommandError(
                        f"Studis has no fallback study code for subject {subject.code}."
                    )
                study, _ = Study.objects.get_or_create(
                    short_name=study_name,
                    defaults={"name": study_data["title"]["sl"]},
                )
                classyear = predmetnik[5]["short_title"]
                group, _ = Group.objects.update_or_create(
                    short_name=f"{classyear}_{study.short_name}",
                    parent=None,
                    groupset=timetable.groupset,
                    defaults={
                        "name": f"{predmetnik[5]['title']['sl']}, {study.name}",
                        "size": subject.enrolled_students_for_study(timetable, study).count(),
                    },
                )
                for activity in subject.activities.filter(
                    activityset=timetable.activityset, type="P"
                ):
                    activity.groups.add(group)

            default_room_resources = {
                "P": "Avditorna učilnica",
                "AV": "Avditorna učilnica",
                "LV": "Računalnik",
            }
            for activity_type, resource_name in default_room_resources.items():
                try:
                    resource = Resource.objects.get(name=resource_name)
                except Resource.DoesNotExist:
                    self.stderr.write(
                        "Warning: default room resource {0} is not configured; "
                        "skipping the {1} default.".format(resource_name, activity_type)
                    )
                    continue
                for activity in timetable.activities.filter(type=activity_type):
                    activity.requirements.add(resource)
                    realizations_have_rooms = all(
                        realization.preferred_rooms(timetable).filter(
                            capacity__gte=realization.size
                        ).exists()
                        for realization in activity.realizations.all()
                    )
                    if realizations_have_rooms:
                        continue
                    activity.requirements.remove(resource)
                    self.stderr.write(
                        "Warning: {0} ({1}) has no capacity-valid room with default "
                        "resource {2}; leaving its existing room requirements unchanged.".format(
                            activity.short_name, activity_type, resource_name
                        )
                    )

            lecture_groups = {}
            for activity in timetable.activities.filter(type="P"):
                for group in activity.groups.all():
                    lecture_groups[group.id] = group

            hint_calculators = {
                "previous-enrollments": lambda group: GroupSizeHint.size_from_enrollments(
                    group, previous_groupset
                ),
                "previous-students": lambda group: GroupSizeHint.size_from_old_group(
                    group, previous_groupset
                ),
                "current-enrollments": lambda group: GroupSizeHint.size_from_enrollments(
                    group, timetable.groupset
                ),
                "previous-size": lambda group: GroupSizeHint.size_from_old_group_size(
                    group, previous_groupset
                ),
            }
            for group in lecture_groups.values():
                for hint_source in hint_sources:
                    try:
                        hint_calculators[hint_source](group)
                    except Group.DoesNotExist:
                        continue

            excluded_studies = set(options["exclude_study"])
            subgroup_groups = [
                group
                for group in lecture_groups.values()
                if group.study not in excluded_studies
            ]
            for group in subgroup_groups:
                size = GroupSizeHint.strategy(
                    group, methods, options["hint_strategy"]
                )
                if size is not None:
                    group.size = size
                    group.save()

            for subject in timetable.subjects.all():
                subject_groups = [
                    group
                    for group in subgroup_groups
                    if subject.activities.filter(
                        activityset=timetable.activityset,
                        type="P",
                        groups=group,
                    ).exists()
                ]
                if subject_groups:
                    subject.update_or_create_subgroups_from_hints(
                        timetable.activityset,
                        methods,
                        strategy_name=options["hint_strategy"],
                        groups=subject_groups,
                    )

            for realization in ActivityRealization.objects.filter(
                activity__activityset=timetable.activityset
            ).select_related("activity"):
                realization.groups.clear()
                if realization.activity.type != "P":
                    realization.assign_groups()

            for realization in timetable.realizations.filter(activity__type="P"):
                realization.groups.add(*realization.activity.groups.all())

            unassigned = list(
                timetable.realizations.filter(groups__isnull=True)
                .distinct()
                .values_list("id", flat=True)
            )
            if unassigned:
                self.stderr.write(
                    self.style.WARNING(
                        "Group preparation left realizations without groups: "
                        + ", ".join(
                            str(realization_id) for realization_id in unassigned
                        )
                    )
                )
            for message in missing_realization_group_messages(timetable):
                self.stderr.write(self.style.WARNING(message))
            # Reapply operator-managed exceptions after generic room defaults and groups.
            apply_manual_activities(timetable)
            if dry_run:
                transaction.set_rollback(True)

        action = "Validated" if dry_run else "Prepared"
        realization_count = timetable.realizations.count()
        assigned_count = realization_count - len(unassigned)
        self.stdout.write(
            f"{action} groups for timetable {timetable.slug}; "
            f"{assigned_count}/{realization_count} realizations have groups."
        )
