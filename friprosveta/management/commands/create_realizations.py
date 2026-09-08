import heapq

from django.core.management.base import BaseCommand, CommandError

from friprosveta.models import REALIZATIONSIZES, ActivityRealization, Timetable
from timetable.models import Allocation, TimetableSet


class Command(BaseCommand):
    """
    Create realizations for a given timetable and timetableset.
    """

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug")
        parser.add_argument("timetable_set_slug")
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Delete existing realizations before creating new ones.",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        timetable_slug = options.get("timetable_slug")
        timetable_set_slug = options.get("timetable_set_slug")

        if args:
            if len(args) == 2:
                timetable_slug, timetable_set_slug = args
            else:
                print("Usage: create_realizations timetable_slug timetable_set_slug")
                return

        if not timetable_slug or not timetable_set_slug:
            print("Usage: create_realizations timetable_slug timetable_set_slug")
            return

        tt = Timetable.objects.get(slug=timetable_slug)
        timetable_set = TimetableSet.objects.get(slug=timetable_set_slug)
        if force:
            foreign_allocations = Allocation.objects.filter(
                activityRealization__activity__activityset=tt.activityset
            ).exclude(timetable=tt)
            foreign_timetable_slugs = list(
                foreign_allocations.order_by("timetable__slug")
                .values_list("timetable__slug", flat=True)
                .distinct()
            )
            if foreign_timetable_slugs:
                raise CommandError(
                    "Refusing to recreate realizations because they have allocations "
                    "owned by other timetables: {}. Deleting a realization would "
                    "cascade-delete those allocations.".format(
                        ", ".join(foreign_timetable_slugs)
                    )
                )
        for activity in tt.activities.all():
            self.create_realizations_for_activity(
                activity.activity,
                tt,
                timetable_set,
                force,
            )

    def create_realizations_for_activity(
        self, activity, timetable, timetable_set, force=False
    ):
        """
        Create realizations for activity.
        If force flag is enabled, old activities are erased.
        """
        print("Creating realizations for {0}".format(activity))
        if force:
            for realization in activity.realizations.all():
                realization.delete()
        elif activity.realizations.count() > 0:
            print(
                "Activity {0} already has realizations and force flag is disabled. "
                "Skipping.".format(activity)
            )
            return
        if activity.type == "P":
            self.create_realizations_for_predavanje(activity, timetable, timetable_set)
        if activity.type == "LV" or activity.type == "AV":
            self.create_realizations_for_vaje(activity, timetable, timetable_set)

    def _add_single_realization(self, activity, flat_teachers, groups):
        assert len(flat_teachers) > 0, "No teachers available for cycle"
        current_teachers = flat_teachers[0]
        ar = ActivityRealization(activity=activity)
        ar.save()
        ar.teachers.add(*current_teachers)
        ar.groups.add(*groups)
        return flat_teachers[1:]

    def create_realizations_for_predavanje(self, activity, timetable, timetable_set):
        """
        Create realizations for activity of type predavanje.
        Does not modify old realizations.
        """
        # This one is easy: just add one realization with all groups selected
        try:
            self._add_single_realization(
                activity, [list(activity.teachers.all())], list(activity.groups.all())
            )
        except Exception:
            return

    def vsi_nacini_izvajanja(self, activity):
        """
        Vrne vse načine izvajanja predmeta v vseh aktivnostih istega tipa,
        kjer se pojavlja (v vseh urnikih).
        """
        tipi_izvajanja = set()
        for activity in activity.subject.activities.filter(type=activity.type):
            for tip in activity.nacini_izvajanja:
                tipi_izvajanja.add(tip)
        return list(tipi_izvajanja)

    def create_realizations_for_vaje(self, activity, timetable, timetable_set):
        """
        Create realizations for activity of type avditorne vaje.
        Does not modify old realizations.
        """
        teachers = [
            [activity.cycles(t.code, activity.lecture_type.id, timetable_set), t]
            for t in activity.teachers.all()
        ]
        teachers.sort(key=lambda e: -e[0])

        max_size = 30
        if activity.type == "LV" and REALIZATIONSIZES[
            1
        ] not in self.vsi_nacini_izvajanja(activity):
            max_size = 15
        if activity.type == "LV" and REALIZATIONSIZES[1] in self.vsi_nacini_izvajanja(
            activity
        ):
            flat_teachers = self._velike_cikle_asistentom(teachers)
        else:
            flat_teachers = []
            for cycles, teacher in teachers:
                flat_teachers += cycles * [[teacher]]
        current_groups, current_groups_size = [], 0

        group_list = sorted(activity.groups.all(), key=lambda g: (-g.size, g.short_name))
        try:
            for group in group_list:
                if group.size + current_groups_size > max_size:
                    flat_teachers = self._add_single_realization(
                        activity, flat_teachers, current_groups
                    )
                    current_groups = []
                    current_groups_size = 0
                current_groups.append(group)
                current_groups_size += group.size
            if current_groups_size > 0:
                self._add_single_realization(activity, flat_teachers, current_groups)
        except Exception:
            return

    def _velike_cikle_asistentom(self, teachers_cycles):
        """
        teacher_cycles format: ((1, "Gregor"), (100, "GFZ"), ...)
        """
        cycles_l = []
        teachers_cycles = [(-n, t) for (n, t) in teachers_cycles]
        heapq.heapify(teachers_cycles)
        while len(teachers_cycles) > 1:
            n1, t1 = heapq.heappop(teachers_cycles)
            n2, t2 = heapq.heappop(teachers_cycles)
            cycles_l.append((t1, t2))
            n1 += 1
            n2 += 1
            if n1 < 0:
                heapq.heappush(teachers_cycles, (n1, t1))
            if n2 < 0:
                heapq.heappush(teachers_cycles, (n2, t2))
        if len(teachers_cycles) > 0:
            cycles, teacher = heapq.heappop(teachers_cycles)
            for i in range(-cycles):
                cycles_l.append([teacher])
        assert len(teachers_cycles) == 0, "NAPAKA - odvecni cikli!"
        return cycles_l
