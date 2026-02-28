import math
import time
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from ortools.sat.python import cp_model

import friprosveta.models
from timetable.models import (
    WORKHOURS,
    WEEKDAYS,
    Allocation,
    GroupTimePreference,
    TeacherTimePreference,
)


class Command(BaseCommand):
    """
    Generate a timetable using OR-Tools CP-SAT and write allocations to the database.
    """

    help = "Generate a timetable using OR-Tools CP-SAT and save allocations."

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug", type=str, help="Timetable slug.")
        parser.add_argument(
            "--time-limit",
            type=int,
            default=60,
            help="Solver time limit in seconds (default: 60).",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Enable debug/progress output.",
        )
        parser.add_argument(
            "--progress-every",
            type=int,
            default=50,
            help="Emit progress after every N realizations (default: 50).",
        )
        parser.add_argument(
            "--build-timeout",
            type=int,
            default=0,
            help="Abort model building after N seconds (0 = no timeout).",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            default=False,
            help="Clear existing allocations before generating.",
        )
        parser.add_argument(
            "--ready-only",
            action="store_true",
            default=False,
            help="Schedule only activities marked ready_to_schedule.",
        )

    def handle(self, *args, **options):
        timetable = friprosveta.models.Timetable.objects.get(
            slug=options["timetable_slug"]
        )
        time_limit = options["time_limit"]
        clear_existing = options["clear_existing"]
        ready_only = options["ready_only"]
        debug = options["debug"]
        progress_every = max(1, options["progress_every"])
        build_timeout = max(0, options["build_timeout"])

        started_at = time.monotonic()

        realizations = list(
            timetable.realizations.all().prefetch_related(
                "teachers",
                "groups",
                "groups__students",
                "activity",
                "activity__mustNotOverlap",
                "activity__before",
            )
        )
        if ready_only:
            realizations = [
                r
                for r in realizations
                if hasattr(r.activity, "ready_to_schedule")
                and r.activity.ready_to_schedule
            ]

        if not realizations:
            self.stdout.write("No activity realizations to schedule.")
            return

        work_hours = [h[0] for h in WORKHOURS]
        weekday_codes = [d[0] for d in WEEKDAYS]
        slots_per_day = len(work_hours)
        days_count = len(weekday_codes)

        rooms = list(timetable.classrooms.all())
        if not rooms:
            self.stdout.write("No classrooms available on timetable.")
            return

        room_index = {room.id: idx for idx, room in enumerate(rooms)}

        if debug:
            self.stdout.write(
                "Building model: "
                f"realizations={len(realizations)}, rooms={len(rooms)}, "
                f"days={days_count}, slots/day={slots_per_day}"
            )

        if debug:
            self.stdout.write("Computing unavailable times (teachers/groups/rooms)...")
        teacher_unavailable = self._build_teacher_unavailable(timetable)
        group_unavailable = self._build_group_unavailable(timetable)
        room_unavailable = self._build_room_unavailable(timetable)
        if debug:
            self.stdout.write("Unavailable times computed.")

        room_blocked = {}
        for room in rooms:
            per_day = {}
            blocked_days = room_unavailable.get(room.id, {})
            for day_code in weekday_codes:
                blocked = [False] * slots_per_day
                for hour_idx in blocked_days.get(day_code, set()):
                    if 0 <= hour_idx < slots_per_day:
                        blocked[hour_idx] = True
                per_day[day_code] = blocked
            room_blocked[room.id] = per_day

        prefset = timetable.preferenceset
        teacher_time_prefs = defaultdict(list)
        group_time_prefs = defaultdict(list)
        if prefset is not None:
            for pref in TeacherTimePreference.objects.filter(
                preferenceset=prefset
            ).exclude(level="CANT"):
                teacher_time_prefs[pref.teacher_id].append(
                    (pref.day, set(preference_hours(pref)), pref.weight, pref.level)
                )
            for pref in GroupTimePreference.objects.filter(preferenceset=prefset).exclude(
                level="CANT"
            ):
                group_time_prefs[pref.group_id].append(
                    (pref.day, set(preference_hours(pref)), pref.weight, pref.level)
                )

        model = cp_model.CpModel()
        assignment_vars = defaultdict(list)
        start_vars = {}
        objective_terms = []

        realization_teachers = {
            r.id: list(r.teachers.all()) for r in realizations
        }
        realization_teacher_ids = {
            r_id: [t.id for t in teachers]
            for r_id, teachers in realization_teachers.items()
        }
        realization_groups = {r.id: list(r.groups.all()) for r in realizations}
        realization_group_ids = {
            r_id: [g.id for g in groups]
            for r_id, groups in realization_groups.items()
        }

        realization_preferred_rooms = {}
        for realization in realizations:
            if build_timeout and (time.monotonic() - started_at) > build_timeout:
                self.stdout.write(
                    "Model build timeout reached; aborting before solve."
                )
                return
            realization_preferred_rooms[realization.id] = list(
                realization.preferred_rooms(timetable).filter(
                    capacity__gte=realization.size
                )
            )

        scheduled_realizations = []
        total_assignment_vars = 0
        for realization in realizations:
            duration = realization.duration
            if duration <= 0 or duration > slots_per_day:
                self.stdout.write(
                    f"Skipping realization {realization.id}: invalid duration."
                )
                continue

            preferred_rooms = realization_preferred_rooms.get(realization.id, [])
            if not preferred_rooms:
                self.stdout.write(
                    f"No suitable rooms for realization {realization.id} ({realization})."
                )
                return

            teacher_ids = realization_teacher_ids.get(realization.id, [])
            group_ids = realization_group_ids.get(realization.id, [])

            blocked_by_day = {}
            for day_code in weekday_codes:
                blocked = [False] * slots_per_day
                for teacher_id in teacher_ids:
                    for hour_idx in teacher_unavailable[teacher_id].get(day_code, set()):
                        if 0 <= hour_idx < slots_per_day:
                            blocked[hour_idx] = True
                for group_id in group_ids:
                    for hour_idx in group_unavailable[group_id].get(day_code, set()):
                        if 0 <= hour_idx < slots_per_day:
                            blocked[hour_idx] = True
                blocked_by_day[day_code] = blocked

            allowed = []
            for day_idx, day_code in enumerate(weekday_codes):
                blocked = blocked_by_day[day_code]
                feasible_starts = []
                for start_idx in range(0, slots_per_day - duration + 1):
                    if any(blocked[start_idx + offset] for offset in range(duration)):
                        continue
                    feasible_starts.append(start_idx)

                if not feasible_starts:
                    continue

                for start_idx in feasible_starts:
                    hours = list(range(start_idx, start_idx + duration))
                    for room in preferred_rooms:
                        room_blocked_day = room_blocked[room.id][day_code]
                        if any(
                            room_blocked_day[start_idx + offset]
                            for offset in range(duration)
                        ):
                            continue
                        var = model.NewBoolVar(
                            f"r{realization.id}_d{day_idx}_s{start_idx}_c{room.id}"
                        )
                        assignment_vars[realization.id].append(
                            (var, day_idx, start_idx, room.id, duration)
                        )
                        allowed.append(var)
                        self._add_preference_objective_terms(
                            objective_terms,
                            var,
                            teacher_ids,
                            group_ids,
                            day_code,
                            hours,
                            teacher_time_prefs,
                            group_time_prefs,
                        )
            if not assignment_vars[realization.id]:
                self.stdout.write(
                    f"No feasible assignments for realization {realization.id} ({realization})."
                )
                return
            total_assignment_vars += len(assignment_vars[realization.id])
            model.Add(sum(var for var in allowed) == 1)

            start_var = model.NewIntVar(
                0, (days_count * slots_per_day) - 1, f"start_{realization.id}"
            )
            start_expr = []
            for var, day_idx, start_idx, _room_id, _duration in assignment_vars[
                realization.id
            ]:
                start_expr.append(var * (day_idx * slots_per_day + start_idx))
            model.Add(sum(start_expr) == start_var)
            start_vars[realization.id] = start_var
            scheduled_realizations.append(realization)

            if debug and (len(scheduled_realizations) % progress_every == 0):
                elapsed = time.monotonic() - started_at
                self.stdout.write(
                    "Model build progress: "
                    f"scheduled={len(scheduled_realizations)}/{len(realizations)}, "
                    f"vars={total_assignment_vars}, elapsed={elapsed:.1f}s"
                )

        if not scheduled_realizations:
            self.stdout.write("No realizations are schedulable with current settings.")
            return

        if debug:
            self.stdout.write(
                "Adding overlap and relation constraints..."
            )
        realization_student_ids = self._build_realization_student_ids(
            scheduled_realizations
        )
        self._add_no_overlap_constraints(
            model,
            assignment_vars,
            scheduled_realizations,
            realization_teacher_ids,
            realization_group_ids,
            slots_per_day,
            realization_student_ids=realization_student_ids,
        )
        self._add_activity_relations_constraints(
            model, start_vars, scheduled_realizations
        )

        if debug:
            elapsed = time.monotonic() - started_at
            self.stdout.write(
                "Model built: "
                f"scheduled={len(scheduled_realizations)}, vars={total_assignment_vars}, "
                f"objective_terms={len(objective_terms)}, elapsed={elapsed:.1f}s"
            )

        if objective_terms:
            model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.num_search_workers = 8
        if debug:
            solver.parameters.log_search_progress = True
            solver.parameters.log_to_stdout = True

        if debug:
            self.stdout.write("Starting solver...")

        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            self.stdout.write("No feasible timetable found.")
            return

        with transaction.atomic():
            Allocation.objects.filter(timetable=timetable).delete()

            allocations = []
            for realization in scheduled_realizations:
                if realization.id not in assignment_vars:
                    continue
                chosen = None
                for var, day_idx, start_idx, room_id, duration in assignment_vars[
                    realization.id
                ]:
                    if solver.Value(var) == 1:
                        chosen = (day_idx, start_idx, room_id, duration)
                        break
                if chosen is None:
                    continue
                day_idx, start_idx, room_id, _duration = chosen
                allocations.append(
                    Allocation(
                        timetable=timetable,
                        activityRealization=realization,
                        classroom=rooms[room_index[room_id]],
                        day=weekday_codes[day_idx],
                        start=work_hours[start_idx],
                    )
                )

            Allocation.objects.bulk_create(allocations)

        self.stdout.write(
            f"Generated {len(allocations)} allocations for timetable {timetable.slug}."
        )

    def _is_time_allowed(
        self, teacher_ids, group_ids, day_code, hours, teacher_unavailable, group_unavailable
    ):
        for teacher_id in teacher_ids:
            if not hours_is_disjoint(
                teacher_unavailable[teacher_id].get(day_code, set()), hours
            ):
                return False
        for group_id in group_ids:
            if not hours_is_disjoint(
                group_unavailable[group_id].get(day_code, set()), hours
            ):
                return False
        return True

    def _room_blocked(self, room, day_code, hours, room_unavailable):
        return not hours_is_disjoint(room_unavailable[room.id].get(day_code, set()), hours)

    def _build_teacher_unavailable(self, timetable):
        unavailable = defaultdict(lambda: defaultdict(set))
        prefset = timetable.preferenceset
        for teacher in timetable.teachers.all():
            for pref in teacher.time_preferences.filter(
                preferenceset=prefset, level="CANT"
            ):
                hours = preference_hours(pref)
                unavailable[teacher.id][pref.day].update(hours)

        for allocation in self._respected_allocations(timetable):
            hours = hour_strings_to_indices(allocation.hours)
            for teacher in allocation.teachers.all():
                unavailable[teacher.id][allocation.day].update(hours)

        return unavailable

    def _build_group_unavailable(self, timetable):
        unavailable = defaultdict(lambda: defaultdict(set))
        prefset = timetable.preferenceset
        for group in timetable.groups.all():
            for pref in group.time_preferences.filter(preferenceset=prefset, level="CANT"):
                hours = preference_hours(pref)
                unavailable[group.id][pref.day].update(hours)

        for allocation in self._respected_allocations(timetable):
            hours = hour_strings_to_indices(allocation.hours)
            for group in allocation.groups.all():
                unavailable[group.id][allocation.day].update(hours)

        return unavailable

    def _build_room_unavailable(self, timetable):
        unavailable = defaultdict(lambda: defaultdict(set))
        for allocation in self._respected_allocations(timetable):
            if allocation.classroom is None:
                continue
            unavailable[allocation.classroom.id][allocation.day].update(
                hour_strings_to_indices(allocation.hours)
            )
        return unavailable

    def _respected_allocations(self, timetable):
        return Allocation.objects.filter(timetable__in=timetable.respects.all())

    def _build_realization_student_ids(self, realizations):
        realization_student_ids = {}
        for realization in realizations:
            student_ids = set()
            for group in realization.groups.all():
                for student in group.students.all():
                    student_ids.add(student.id)
            if student_ids:
                realization_student_ids[realization.id] = student_ids
        return realization_student_ids

    def _add_no_overlap_constraints(
        self,
        model,
        assignment_vars,
        realizations,
        realization_teacher_ids,
        realization_group_ids,
        slots_per_day,
        realization_student_ids=None,
    ):
        teacher_map = defaultdict(list)
        group_map = defaultdict(list)
        room_map = defaultdict(list)
        student_map = defaultdict(list)

        for realization in realizations:
            teacher_ids = realization_teacher_ids.get(realization.id, [])
            group_ids = realization_group_ids.get(realization.id, [])
            student_ids = []
            if realization_student_ids is not None:
                student_ids = realization_student_ids.get(realization.id, [])
            for var, day_idx, start_idx, room_id, duration in assignment_vars.get(
                realization.id, []
            ):
                for offset in range(duration):
                    hour_idx = start_idx + offset
                    for teacher_id in teacher_ids:
                        teacher_map[(teacher_id, day_idx, hour_idx)].append(var)
                    for group_id in group_ids:
                        group_map[(group_id, day_idx, hour_idx)].append(var)
                    for student_id in student_ids:
                        student_map[(student_id, day_idx, hour_idx)].append(var)
                    room_map[(room_id, day_idx, hour_idx)].append(var)

        for vars_list in teacher_map.values():
            if len(vars_list) > 1:
                model.Add(sum(vars_list) <= 1)
        for vars_list in group_map.values():
            if len(vars_list) > 1:
                model.Add(sum(vars_list) <= 1)
        for vars_list in student_map.values():
            if len(vars_list) > 1:
                model.Add(sum(vars_list) <= 1)
        for vars_list in room_map.values():
            if len(vars_list) > 1:
                model.Add(sum(vars_list) <= 1)

    def _add_activity_relations_constraints(self, model, start_vars, realizations):
        realizations_by_activity = defaultdict(list)
        for realization in realizations:
            realizations_by_activity[realization.activity_id].append(realization)

        handled_pairs = set()
        for realization in realizations:
            for other in realization.activity.mustNotOverlap.all():
                key = tuple(sorted([realization.activity_id, other.id]))
                if key in handled_pairs:
                    continue
                handled_pairs.add(key)
                for r1 in realizations_by_activity.get(realization.activity_id, []):
                    for r2 in realizations_by_activity.get(other.id, []):
                        if r1.id == r2.id:
                            continue
                        order = model.NewBoolVar(f"order_{r1.id}_{r2.id}")
                        model.Add(start_vars[r1.id] + r1.duration <= start_vars[r2.id]).OnlyEnforceIf(
                            order
                        )
                        model.Add(start_vars[r2.id] + r2.duration <= start_vars[r1.id]).OnlyEnforceIf(
                            order.Not()
                        )

        for realization in realizations:
            for after in realization.activity.before.all():
                for r1 in realizations_by_activity.get(realization.activity_id, []):
                    for r2 in realizations_by_activity.get(after.id, []):
                        model.Add(start_vars[r1.id] + r1.duration <= start_vars[r2.id])

    def _add_preference_objective_terms(
        self,
        objective_terms,
        var,
        teacher_ids,
        group_ids,
        day_code,
        hours,
        teacher_time_prefs,
        group_time_prefs,
    ):
        hours_set = set(hours)
        for teacher_id in teacher_ids:
            for pref_day, pref_hours, pref_weight, pref_level in teacher_time_prefs.get(
                teacher_id, []
            ):
                if pref_day != day_code:
                    continue
                if hours_set.isdisjoint(pref_hours):
                    continue
                weight = int(math.ceil(pref_weight * 100))
                if pref_level == "HATE":
                    objective_terms.append(-weight * var)
                elif pref_level == "WANT":
                    objective_terms.append(weight * var)
        for group_id in group_ids:
            for pref_day, pref_hours, pref_weight, pref_level in group_time_prefs.get(
                group_id, []
            ):
                if pref_day != day_code:
                    continue
                if hours_set.isdisjoint(pref_hours):
                    continue
                weight = int(math.ceil(pref_weight * 100))
                if pref_level == "HATE":
                    objective_terms.append(-weight * var)
                elif pref_level == "WANT":
                    objective_terms.append(weight * var)


def preference_hours(pref):
    start_index = [h[0] for h in WORKHOURS].index(pref.start)
    return list(range(start_index, start_index + pref.duration))


def hours_overlap(pref_hours, hours):
    return not set(pref_hours).isdisjoint(hours)


def hours_is_disjoint(blocked_hours, hours):
    return set(blocked_hours).isdisjoint(hours)


def hour_strings_to_indices(hours):
    work_hours = [h[0] for h in WORKHOURS]
    return [work_hours.index(h) for h in hours if h in work_hours]
