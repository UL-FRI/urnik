import math
import time
from collections import defaultdict
from dataclasses import dataclass, field

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from ortools.sat.python import cp_model

from friprosveta.management.commands import crossections
from friprosveta.models import (
    ActivityRealizationSchedulingWindow,
    ActivityTypeSchedulingRestriction,
    SolverWeightSettings,
    TeacherSchedulingWindow,
)
from friprosveta.services.group_coverage import missing_realization_group_messages
from timetable.models import (
    AFTERHOURS,
    WORKHOURS,
    WEEKDAYS,
    Allocation,
    Group,
    GroupValuePreference,
    GroupTimePreference,
    SolverConstraint,
    StudyModule,
    TagDescriptivePreference,
    TagValuePreference,
    TagTimePreference,
    TeacherValuePreference,
    TeacherTimePreference,
)

HARD_UNAVAILABLE_LEVELS = ("CANT", "HATE")
SCHEDULING_WINDOW_WEIGHT = 10000
CONSECUTIVE_TEACHER_ROOM_WEIGHT = 10
ROOM_ADJACENCY_WEIGHT = 2
LECTURE_GRID_ALIGNMENT_WEIGHT = 8
LECTURE_BACK_TO_BACK_PENALTY = 10
ROOM_FIT_WEIGHT = 1


@dataclass
class ORToolsSolverOptions:
    time_limit: int = 60  # 0 means no search-time limit.
    num_search_workers: int = 8
    max_memory_in_mb: int = 4096
    debug: bool = False
    progress_every: int = 50
    build_timeout: int = 0
    clear_existing: bool = False
    ready_only: bool = False
    allocation_time_weight: int = 100
    allocation_room_weight: int = 25
    cross_section_razor: int | None = None
    cross_section_group_razor: int | None = None
    scheduling_mode: str = "improve"
    repair_realization_ids: tuple[int, ...] = ()


@dataclass
class ORToolsSolverResult:
    success: bool
    allocations: list = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    status: int | None = None


class ORToolsTimetableSolver:
    def __init__(self, timetable, options=None):
        self.timetable = timetable
        self.options = options or ORToolsSolverOptions()
        self.weight_settings = SolverWeightSettings.objects.filter(timetable=timetable).first()
        self.messages = []
        self._contention_messages = []
        self._forced_placement_messages = []
        self._room_capacity_messages = []

    def _automatic_weight(self, name, default):
        if self.weight_settings is None:
            return default
        return getattr(self.weight_settings, name)

    def solve_and_save(self):
        result = self.solve()
        if not result.success:
            return result

        with transaction.atomic():
            allocations_to_replace = Allocation.objects.filter(timetable=self.timetable)
            if self.options.ready_only:
                allocations_to_replace = allocations_to_replace.filter(
                    activityRealization_id__in={
                        allocation.activityRealization_id
                        for allocation in result.allocations
                    }
                )
            allocations_to_replace.delete()
            Allocation.objects.bulk_create(result.allocations)

        result.messages.append(
            f"Generated {len(result.allocations)} allocations for timetable {self.timetable.slug}."
        )
        return result

    def solve(self):
        started_at = time.monotonic()

        existing_allocations = list(
            Allocation.objects.filter(timetable=self.timetable).select_related(
                "classroom", "activityRealization"
            ).prefetch_related(
                "activityRealization__teachers__user",
                "activityRealization__groups__students",
            )
        )
        if existing_allocations and not self.options.clear_existing:
            return self._failure(
                "Timetable already has allocations; pass --clear-existing to replace "
                "them after a feasible solution is found."
            )

        realizations = list(
            self.timetable.realizations.all().prefetch_related(
                "teachers",
                "teachers__user",
                "groups",
                "groups__parent",
                "groups__students",
                "tags",
                "activity",
                "activity__tags",
                "activity__mustNotOverlap",
                "activity__before",
            )
        )
        if self.options.ready_only:
            realizations = [
                r
                for r in realizations
                if self._is_activity_ready_to_schedule(r.activity)
            ]

        invalid_realizations = [
            realization for realization in realizations if realization.duration <= 0
        ]
        if invalid_realizations:
            invalid_details = [
                "{}(duration={})".format(realization.id, realization.duration)
                for realization in invalid_realizations
            ]
            self.messages.append(
                "Skipping {} realization(s) with invalid duration: {}".format(
                    len(invalid_realizations), ", ".join(invalid_details)
                )
            )
            realizations = [
                realization
                for realization in realizations
                if realization.duration > 0
            ]

        if not realizations:
            return self._failure("No activity realizations to schedule.")

        scheduled_realization_ids = {realization.id for realization in realizations}
        preserved_allocations = (
            [
                allocation
                for allocation in existing_allocations
                if allocation.activityRealization_id not in scheduled_realization_ids
            ]
            if self.options.ready_only
            else []
        )

        realizations_without_groups = [
            realization for realization in realizations if not realization.groups.all()
        ]
        if realizations_without_groups:
            self.messages.extend(
                "Warning: realization {0} ({1}) has no groups; generation will not "
                "apply student-group constraints to it.".format(
                    realization.id, realization
                )
                for realization in realizations_without_groups
            )
        self.messages.extend(
            missing_realization_group_messages(
                self.timetable,
                {realization.activity_id for realization in realizations},
            )
        )

        work_hours = [h[0] for h in WORKHOURS]
        weekday_codes = [d[0] for d in WEEKDAYS]
        slots_per_day = len(work_hours)
        days_count = len(weekday_codes)
        window_boundaries = work_hours + [AFTERHOURS[0]]
        activity_type_restrictions = defaultdict(dict)
        for activity_type, day, start, weight in ActivityTypeSchedulingRestriction.objects.filter(
            timetable=self.timetable
        ).values_list("activity_type", "day", "start", "weight"):
            activity_type_restrictions[(activity_type, day)][work_hours.index(start)] = weight
        realization_windows = {}
        for realization_id, day, start, end, unrestricted, weight in (
            ActivityRealizationSchedulingWindow.objects.filter(
                timetable=self.timetable
            ).values_list("realization_id", "day", "start", "end", "unrestricted", "weight")
        ):
            realization_windows[(realization_id, day)] = (
                (0, slots_per_day, 0)
                if unrestricted
                else (work_hours.index(start), window_boundaries.index(end), weight)
            )
        teacher_windows = {}
        for teacher_id, day, start, end, unrestricted, unavailable, weight in (
            TeacherSchedulingWindow.objects.filter(timetable=self.timetable).values_list(
                "teacher_id", "day", "start", "end", "unrestricted", "unavailable", "weight"
            )
        ):
            teacher_windows[(teacher_id, day)] = (
                (0, slots_per_day, 0)
                if unrestricted
                else (0, 0, 100)
                if unavailable
                else (work_hours.index(start), window_boundaries.index(end), weight)
            )

        rooms = list(
            self.timetable.classrooms.prefetch_related(
                "supported_activity_types", "activity_start_times"
            )
        )
        if not rooms:
            return self._failure("No classrooms available on timetable.")

        room_index = {room.id: idx for idx, room in enumerate(rooms)}
        room_capacities = {room.id: room.capacity for room in rooms}
        virtual_rooms = [room for room in rooms if room.is_virtual]
        virtual_room_ids = {room.id for room in virtual_rooms}
        supported_activity_types = {
            room.id: {entry.activity_type for entry in room.supported_activity_types.all()}
            for room in rooms
        }
        allowed_room_starts = defaultdict(set)
        for room in rooms:
            for entry in room.activity_start_times.all():
                allowed_room_starts[(room.id, entry.activity_type)].add(entry.start)
        overlapping_room_ids = {
            room.id for room in rooms if room.allow_overlaps or room.is_virtual
        }
        room_locations = {room.id: room.location_id for room in rooms}
        location_ids = sorted({loc_id for loc_id in room_locations.values() if loc_id is not None})
        location_index = {loc_id: idx for idx, loc_id in enumerate(location_ids)}

        self._debug(
            "Building model: "
            f"realizations={len(realizations)}, rooms={len(rooms)}, "
            f"days={days_count}, slots/day={slots_per_day}"
        )

        teacher_unavailable = self._build_teacher_unavailable()
        group_unavailable = self._build_group_unavailable()
        room_unavailable = self._build_room_unavailable()

        room_blocked = self._build_room_blocked(rooms, weekday_codes, slots_per_day, room_unavailable)
        teacher_time_prefs, group_time_prefs, tag_time_prefs = self._build_want_preferences()
        allocation_locks = self._build_allocation_locks(existing_allocations)
        hard_allocation_locks = self._build_hard_allocation_locks(existing_allocations)

        realization_teachers = {
            r.id: [teacher for teacher in r.teachers.all() if not self._is_placeholder_teacher(teacher)]
            for r in realizations
        }
        realization_teacher_ids = {
            r_id: [t.id for t in teachers]
            for r_id, teachers in realization_teachers.items()
        }
        realization_groups, ignored_group_assignments = (
            self._build_solver_realization_groups(realizations)
        )
        self._solver_group_ids_by_realization = {
            realization_id: {group.id for group in groups}
            for realization_id, groups in realization_groups.items()
        }
        self._solver_group_size_by_realization = {
            realization_id: sum(group.size or 0 for group in groups)
            for realization_id, groups in realization_groups.items()
        }
        if self.options.cross_section_group_razor is not None:
            examples = ", ".join(
                "#{} {}={}".format(realization_id, group.short_name, effective_size)
                for realization_id, group, effective_size in ignored_group_assignments[:10]
            )
            message = (
                "Group assignment razor: ignored {} assignment(s) across {} group(s) "
                "with effective size below {}; database assignments unchanged.".format(
                    len(ignored_group_assignments),
                    len({group.id for _rid, group, _size in ignored_group_assignments}),
                    self.options.cross_section_group_razor,
                )
            )
            if examples:
                message += " Examples: {}.".format(examples)
            self.messages.append(message)
        realization_group_ids = {
            r_id: [group.id for group in groups]
            for r_id, groups in realization_groups.items()
        }
        realization_student_ids = self._build_realization_student_ids(
            realizations, realization_groups
        )
        preserved_realizations = {
            allocation.activityRealization_id: allocation.activityRealization
            for allocation in preserved_allocations
        }
        preserved_realization_groups, _ignored_preserved_groups = (
            self._build_solver_realization_groups(preserved_realizations.values())
        )
        preserved_student_ids = self._build_realization_student_ids(
            preserved_realizations.values(), preserved_realization_groups
        )
        fixed_occupancy, fixed_occupancy_error = self._build_fixed_allocation_occupancy(
            preserved_allocations,
            preserved_realization_groups,
            preserved_student_ids,
            weekday_codes,
            work_hours,
        )
        if fixed_occupancy_error:
            return self._failure(fixed_occupancy_error)
        realization_tag_ids = self._build_realization_tag_ids(realizations)
        teacher_site_cycles = self._teacher_site_cycles(realizations)
        remote_realization_ids = {
            realization_id
            for data in teacher_site_cycles.values()
            if data["physical_count"] < len(data["realization_ids"])
            for realization_id in data["realization_ids"]
        }
        if remote_realization_ids and not virtual_rooms:
            return self._failure(
                "Teacher-specific remote cycles require at least one classroom marked as virtual."
            )
        size_adjustments = self._build_tag_size_adjustments()
        self._debug(
            f"Built size adjustments for {len(size_adjustments)} tags"
            if self.options.debug else ""
        )

        realization_preferred_rooms = {}
        realization_candidate_rooms = {}
        fixed_rooms_by_realization = self._fixed_rooms_by_realization(realizations, rooms)
        for realization in realizations:
            if self.options.build_timeout and (time.monotonic() - started_at) > self.options.build_timeout:
                return self._failure("Model build timeout reached; aborting before solve.")
            adjusted_size = self._adjusted_size(realization, realization_tag_ids, size_adjustments)
            fixed_room_sets = fixed_rooms_by_realization.get(realization.id, [])
            if fixed_room_sets:
                fixed_room_ids = set.intersection(*fixed_room_sets)
                candidate_rooms = [room for room in rooms if room.id in fixed_room_ids]
            else:
                candidate_rooms = realization.preferred_rooms(self.timetable)
            realization_candidate_rooms[realization.id] = list(candidate_rooms)
            physical_rooms = [
                room
                for room in candidate_rooms
                if room.capacity >= adjusted_size
                and room.minimum_realization_size <= adjusted_size
                and room.id not in virtual_room_ids
            ]
            physical_rooms = [
                room
                for room in physical_rooms
                if not supported_activity_types.get(room.id)
                or realization.activity.type in supported_activity_types[room.id]
            ]
            if realization.id in remote_realization_ids:
                physical_rooms.extend(virtual_rooms)
            realization_preferred_rooms[realization.id] = physical_rooms

        self._room_capacity_messages = self._build_room_capacity_messages(
            realizations,
            realization_candidate_rooms,
            realization_preferred_rooms,
            realization_tag_ids,
            size_adjustments,
            virtual_room_ids,
        )

        no_room_messages = []
        for realization in realizations:
            preferred_rooms = realization_preferred_rooms.get(realization.id, [])
            if preferred_rooms:
                continue
            adjusted_size = self._adjusted_size(realization, realization_tag_ids, size_adjustments)
            all_preferred = list(realization.preferred_rooms(self.timetable))
            max_capacity = 0
            if all_preferred:
                max_capacity = max(room.capacity for room in all_preferred)
            min_size_excluded = sum(
                1
                for room in all_preferred
                if room.capacity >= adjusted_size
                and room.minimum_realization_size > adjusted_size
            )
            teachers = ", ".join(str(teacher) for teacher in realization.teachers.all())
            no_room_messages.append(
                "  #{id} {name} [{activity_type}]; required={required}, "
                "eligible_rooms={eligible}, max_capacity={maximum}, "
                "excluded_by_minimum_size={minimum_excluded}, teachers={teachers}".format(
                    id=realization.id,
                    name=realization.activity.name,
                    activity_type=realization.activity.type,
                    required=adjusted_size,
                    eligible=len(all_preferred),
                    maximum=max_capacity,
                    minimum_excluded=min_size_excluded,
                    teachers=teachers or "none",
                )
            )

        if no_room_messages:
            self.messages.append(
                "No suitable rooms for {} realizations:".format(len(no_room_messages))
            )
            self.messages.extend(no_room_messages)
            return ORToolsSolverResult(success=False, messages=self.messages, status=None)

        model = cp_model.CpModel()
        assignment_vars = defaultdict(list)
        start_vars = {}
        day_vars = {}
        objective_terms = []

        scheduled_realizations = []
        total_assignment_vars = 0
        for realization in realizations:
            duration = realization.duration
            if duration > slots_per_day:
                return self._failure(
                    f"Invalid duration for realization {realization.id}; aborting."
                )

            preferred_rooms = realization_preferred_rooms.get(realization.id, [])

            teacher_ids = realization_teacher_ids.get(realization.id, [])
            group_ids = realization_group_ids.get(realization.id, [])
            tag_ids = realization_tag_ids.get(realization.id, set())

            allowed = []
            time_candidates = 0
            room_candidates = 0
            for day_idx, day_code in enumerate(weekday_codes):
                restriction_weights = activity_type_restrictions.get(
                    (realization.activity.type, day_code), {}
                )
                teacher_bounds = [
                    teacher_windows[(teacher_id, day_code)]
                    for teacher_id in teacher_ids
                    if (teacher_id, day_code) in teacher_windows
                ]
                if teacher_bounds:
                    default_window = (
                        max(start for start, _end, _weight in teacher_bounds),
                        min(end for _start, end, _weight in teacher_bounds),
                        max(weight for _start, _end, weight in teacher_bounds),
                    )
                else:
                    default_window = (0, slots_per_day, 0)
                window_start_idx, window_end_idx, window_weight = realization_windows.get(
                    (realization.id, day_code), default_window
                )
                blocked = self._blocked_slots_for_realization(
                    day_code,
                    slots_per_day,
                    teacher_ids,
                    group_ids,
                    teacher_unavailable,
                    group_unavailable,
                )
                for start_idx in range(0, slots_per_day - duration + 1):
                    if any(
                        restriction_weights.get(hour_idx) == 100
                        for hour_idx in range(start_idx, start_idx + duration)
                    ):
                        continue
                    if window_weight == 100 and (
                        start_idx < window_start_idx
                        or start_idx + duration > window_end_idx
                    ):
                        continue
                    if any(blocked[start_idx + offset] for offset in range(duration)):
                        continue
                    time_candidates += 1
                    hours = list(range(start_idx, start_idx + duration))
                    for room in preferred_rooms:
                        room_starts = allowed_room_starts.get(
                            (room.id, realization.activity.type)
                        )
                        if room_starts and work_hours[start_idx] not in room_starts:
                            continue
                        room_blocked_day = room_blocked[room.id][day_code]
                        if any(
                            room_blocked_day[start_idx + offset]
                            for offset in range(duration)
                        ):
                            continue
                        if self._placement_conflicts_with_fixed_occupancy(
                            fixed_occupancy,
                            day_idx,
                            start_idx,
                            duration,
                            teacher_ids,
                            group_ids,
                            realization_student_ids.get(realization.id, set()),
                            room.id,
                            overlapping_room_ids,
                        ):
                            continue
                        room_candidates += 1
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
                            realization.id,
                            teacher_ids,
                            group_ids,
                            tag_ids,
                            day_code,
                            hours,
                            room.id,
                            teacher_time_prefs,
                            group_time_prefs,
                            tag_time_prefs,
                            allocation_locks,
                        )
                        self._add_scheduling_window_objective_terms(
                            objective_terms,
                            var,
                            start_idx,
                            duration,
                            window_start_idx,
                            window_end_idx,
                            window_weight,
                        )
                        self._add_activity_type_restriction_objective_terms(
                            objective_terms,
                            var,
                            start_idx,
                            duration,
                            restriction_weights,
                        )
                        if room.id not in virtual_room_ids:
                            unused_capacity = room_capacities[room.id] - self._adjusted_size(
                                realization, realization_tag_ids, size_adjustments
                            )
                            if unused_capacity > 0:
                                objective_terms.append(-ROOM_FIT_WEIGHT * unused_capacity * var)
                        grid_duration = {"P": 3, "LV": 2, "AV": 2}.get(
                            realization.activity.type
                        )
                        if (
                            grid_duration == duration
                            and (start_idx - 1) % grid_duration == 0
                        ):
                            objective_terms.append(
                                self._automatic_weight(
                                    "lecture_grid_alignment_weight",
                                    LECTURE_GRID_ALIGNMENT_WEIGHT,
                                )
                                * var
                            )

            if not assignment_vars[realization.id]:
                return self._failure(
                    f"No feasible assignments for realization {realization.id} ({realization}). "
                    f"rooms={len(preferred_rooms)}, time_candidates={time_candidates}, "
                    f"room_candidates={room_candidates}."
                )

            total_assignment_vars += len(assignment_vars[realization.id])
            model.Add(sum(var for var in allowed) == 1)
            hard_lock = hard_allocation_locks.get(realization.id)
            if not self._add_hard_allocation_lock(
                model,
                assignment_vars[realization.id],
                hard_lock,
                weekday_codes,
                work_hours,
            ):
                return self._failure(
                    "Existing allocation for realization {} cannot be preserved in "
                    "repair mode: {} {} in room {} is not a feasible candidate.".format(
                        realization.id,
                        hard_lock.day,
                        hard_lock.start,
                        hard_lock.classroom_id,
                    )
                )

            start_var = model.NewIntVar(
                0, (days_count * slots_per_day) - 1, f"start_{realization.id}"
            )
            day_var = model.NewIntVar(0, days_count - 1, f"day_{realization.id}")
            start_expr = []
            day_expr = []
            for var, day_idx, start_idx, _room_id, _duration in assignment_vars[realization.id]:
                start_expr.append(var * (day_idx * slots_per_day + start_idx))
                day_expr.append(var * day_idx)
            model.Add(sum(start_expr) == start_var)
            model.Add(sum(day_expr) == day_var)
            start_vars[realization.id] = start_var
            day_vars[realization.id] = day_var
            scheduled_realizations.append(realization)

            if self.options.debug and (len(scheduled_realizations) % self.options.progress_every == 0):
                elapsed = time.monotonic() - started_at
                self._debug(
                    "Model build progress: "
                    f"scheduled={len(scheduled_realizations)}/{len(realizations)}, "
                    f"vars={total_assignment_vars}, elapsed={elapsed:.1f}s"
                )

        if not scheduled_realizations:
            return self._failure("No realizations are schedulable with current settings.")

        self._contention_messages = self._build_contention_messages(
            assignment_vars,
            scheduled_realizations,
            realization_teachers,
            realization_groups,
        )

        self._add_teacher_site_cycle_constraints(
            model,
            assignment_vars,
            teacher_site_cycles,
            virtual_room_ids,
        )
        self._forced_placement_messages = self._build_forced_placement_messages(
            assignment_vars,
            scheduled_realizations,
            realization_teacher_ids,
            realization_group_ids,
            realization_student_ids,
            overlapping_room_ids,
            weekday_codes,
            work_hours,
        )
        self._add_no_overlap_constraints(
            model,
            assignment_vars,
            scheduled_realizations,
            realization_teacher_ids,
            realization_group_ids,
            realization_student_ids=realization_student_ids,
            overlapping_room_ids=overlapping_room_ids,
        )
        self._add_consecutive_teacher_room_preferences(
            model,
            objective_terms,
            assignment_vars,
            scheduled_realizations,
            realization_teacher_ids,
        )
        self._add_room_compactness_preferences(
            model,
            objective_terms,
            assignment_vars,
            overlapping_room_ids,
        )
        self._add_lecture_back_to_back_penalties(
            model,
            objective_terms,
            assignment_vars,
            scheduled_realizations,
            realization_group_ids,
        )
        self._add_workload_constraints(
            model,
            assignment_vars,
            scheduled_realizations,
            realization_teacher_ids,
            realization_group_ids,
        )
        self._add_lecture_group_hour_limits(
            model, assignment_vars, scheduled_realizations, realization_group_ids
        )
        self._add_movement_constraints(
            model,
            assignment_vars,
            scheduled_realizations,
            realization_teacher_ids,
            realization_group_ids,
            room_locations,
        )
        self._add_building_change_constraints(
            model,
            assignment_vars,
            scheduled_realizations,
            realization_teacher_ids,
            realization_group_ids,
            room_locations,
            location_index,
        )
        self._add_activity_relations_constraints(model, start_vars, scheduled_realizations)
        self._add_subject_lecture_exercise_no_overlap(
            model, start_vars, scheduled_realizations
        )
        self._add_optional_activity_mandatory_lecture_no_overlap(
            model, start_vars, scheduled_realizations
        )
        self._add_lv_av_parent_group_no_overlap(
            model, start_vars, scheduled_realizations, realization_groups
        )
        self._add_tag_descriptive_constraints(
            model,
            assignment_vars,
            start_vars,
            day_vars,
            scheduled_realizations,
            realization_group_ids,
            realization_student_ids,
        )
        self._add_tag_value_constraints(
            model, assignment_vars, start_vars, scheduled_realizations,
            realization_group_ids=realization_group_ids,
        )
        self._add_cross_section_no_overlap_constraints(
            model,
            start_vars,
            scheduled_realizations,
            realization_student_ids,
        )
        self._add_study_module_constraints(model, start_vars, scheduled_realizations)
        self._add_solver_constraints(
            model,
            assignment_vars,
            start_vars,
            day_vars,
            scheduled_realizations,
            realization_teacher_ids,
            realization_group_ids,
            realization_student_ids,
        )

        elapsed = time.monotonic() - started_at
        self._debug(
            "Model built: "
            f"scheduled={len(scheduled_realizations)}, vars={total_assignment_vars}, "
            f"objective_terms={len(objective_terms)}, elapsed={elapsed:.1f}s"
        )

        if objective_terms:
            model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        if self.options.time_limit > 0:
            solver.parameters.max_time_in_seconds = float(self.options.time_limit)
        solver.parameters.num_search_workers = self.options.num_search_workers
        solver.parameters.max_memory_in_mb = self.options.max_memory_in_mb
        if self.options.debug:
            solver.parameters.log_search_progress = True
            solver.parameters.log_to_stdout = True

        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if status == cp_model.UNKNOWN:
                if self.options.time_limit <= 0:
                    return self._failure(
                        "The solver ended without a timetable. Check the solver log and memory limit.",
                        status=status,
                    )
                return self._failure(
                    "No timetable was found before the solver time limit. "
                    "Candidate generation succeeded; increase --time-limit or "
                    "reduce the hard constraint search space.",
                    status=status,
                )
            return self._failure(
                "No feasible timetable found. Candidate generation succeeded, so "
                "infeasibility is likely caused by hard overlap/order/tag constraints.",
                status=status,
            )

        allocations = []
        for realization in scheduled_realizations:
            chosen = None
            for var, day_idx, start_idx, room_id, duration in assignment_vars[realization.id]:
                if solver.Value(var) == 1:
                    chosen = (day_idx, start_idx, room_id, duration)
                    break
            if chosen is None:
                return self._failure(
                    f"Solver returned no placement for realization {realization.id}; "
                    "aborting without writing allocations.",
                    status=status,
                )
            day_idx, start_idx, room_id, _duration = chosen
            allocations.append(
                Allocation(
                    timetable=self.timetable,
                    activityRealization=realization,
                    classroom=rooms[room_index[room_id]],
                    day=weekday_codes[day_idx],
                    start=work_hours[start_idx],
                )
            )

        if len(allocations) != len(scheduled_realizations):
            return self._failure("Incomplete solution; aborting without writing allocations.", status=status)

        self.messages.extend(self._soft_time_restriction_summary(allocations))
        self.messages.extend(self._constraint_summary(allocations))
        self.messages.extend(self._soft_constraint_summary(allocations))
        return ORToolsSolverResult(
            success=True, allocations=allocations, messages=self.messages, status=status
        )

    def _failure(self, message, status=None):
        if self._contention_messages and message.startswith((
            "No feasible timetable found.",
            "No timetable was found before",
        )):
            self.messages.extend(self._contention_messages)
            self.messages.extend(self._room_capacity_messages)
            self.messages.extend(self._forced_placement_messages)
        self.messages.append(message)
        return ORToolsSolverResult(success=False, messages=self.messages, status=status)

    def _soft_time_restriction_summary(self, allocations):
        """Summarize how often activity-type soft-unavailable slots were avoided."""
        soft_restrictions = {
            (activity_type, day, start)
            for activity_type, day, start in ActivityTypeSchedulingRestriction.objects.filter(
                timetable=self.timetable, weight__gt=0, weight__lt=100
            ).values_list("activity_type", "day", "start")
        }
        restricted_types = {activity_type for activity_type, _day, _start in soft_restrictions}
        if not restricted_types:
            return []

        work_hours = [hour for hour, _label in WORKHOURS]
        applicable_hours = 0
        used_soft_unavailable_hours = 0
        for allocation in allocations:
            activity_type = allocation.activityRealization.activity.type
            if activity_type not in restricted_types:
                continue
            start_index = work_hours.index(allocation.start)
            for hour in work_hours[start_index : start_index + allocation.activityRealization.duration]:
                applicable_hours += 1
                if (activity_type, allocation.day, hour) in soft_restrictions:
                    used_soft_unavailable_hours += 1

        if not applicable_hours:
            return []
        avoided_hours = applicable_hours - used_soft_unavailable_hours
        percentage = 100 * avoided_hours / applicable_hours
        return [
            "Soft activity-type time restrictions: {}/{} scheduled hours avoided "
            "soft-unavailable slots ({:.0f}%; {} used).".format(
                avoided_hours,
                applicable_hours,
                percentage,
                used_soft_unavailable_hours,
            )
        ]

    def _constraint_summary(self, allocations):
        """Summarize the hard safeguards verified on the generated result."""
        teacher_slots = defaultdict(set)
        group_slots = defaultdict(set)
        student_slots = defaultdict(set)
        room_slots = defaultdict(set)
        realization_slots = defaultdict(set)

        for allocation in allocations:
            realization = allocation.activityRealization
            solver_group_ids = getattr(
                self, "_solver_group_ids_by_realization", {}
            ).get(realization.id)
            groups = [
                group
                for group in realization.groups.all()
                if not self._is_pad_group(group)
                and (solver_group_ids is None or group.id in solver_group_ids)
            ]
            for hour in allocation.hours:
                slot = (allocation.day, hour)
                realization_slots[realization.id].add(slot)
                for teacher in realization.teachers.all():
                    teacher_slots[(teacher.id, *slot)].add(realization.id)
                for group in groups:
                    group_slots[(group.id, *slot)].add(realization.id)
                    for student in group.students.all():
                        student_slots[(student.id, *slot)].add(realization.id)
                if not allocation.classroom.allow_overlaps and not allocation.classroom.is_virtual:
                    room_slots[(allocation.classroom_id, *slot)].add(realization.id)

        def conflicts(slots):
            return sum(1 for realizations in slots.values() if len(realizations) > 1)

        group_conflicts = conflicts(group_slots)
        if self.options.cross_section_razor is None:
            student_conflicts = conflicts(student_slots)
        else:
            student_conflicts = sum(
                bool(realization_slots[first_id] & realization_slots[second_id])
                for first_id, second_id in self._cross_section_no_overlap_pairs()
            )

        respected_allocations = self._respected_allocations()
        respected_room_slots = {
            (allocation.classroom_id, allocation.day, hour)
            for allocation in respected_allocations
            if allocation.classroom_id is not None
            and not allocation.classroom.allow_overlaps
            and not allocation.classroom.is_virtual
            for hour in allocation.hours
        }
        respected_room_collisions = sum(
            1 for slot in room_slots if slot in respected_room_slots
        )
        prefset = self.timetable.preferenceset
        hard_time_restrictions = (
            ActivityTypeSchedulingRestriction.objects.filter(
                timetable=self.timetable, weight=100
            ).count()
            + ActivityRealizationSchedulingWindow.objects.filter(
                timetable=self.timetable, weight=100, unrestricted=False
            ).count()
            + TeacherSchedulingWindow.objects.filter(
                timetable=self.timetable, weight=100, unrestricted=False
            ).count()
        )
        tag_constraints = (
            TagDescriptivePreference.objects.filter(preferenceset=prefset).count()
            + TagValuePreference.objects.filter(preferenceset=prefset).count()
        )

        return [
            "Hard constraint verification: overlap violations teacher={}, group={}, student={}, room={}.".format(
                conflicts(teacher_slots),
                group_conflicts,
                student_conflicts,
                conflicts(room_slots),
            ),
            "Respected timetable locks: timetables={}, allocations={}, protected room slots={}, collisions={}.".format(
                self.timetable.respects.count(),
                len(respected_allocations),
                len(respected_room_slots),
                respected_room_collisions,
            ),
            "Configured hard-rule sources: custom={}, tag={}, study_modules={}, hard_time_restrictions={}.".format(
                SolverConstraint.objects.filter(timetable=self.timetable, active=True).count(),
                tag_constraints,
                StudyModule.objects.filter(timetable=self.timetable, active=True).count(),
                hard_time_restrictions,
            ),
        ]

    def _soft_constraint_summary(self, allocations):
        """Report missed terms and penalties from the generated objective."""
        work_hours = [hour for hour, _label in WORKHOURS]
        window_boundaries = work_hours + [AFTERHOURS[0]]
        teacher_prefs, group_prefs, tag_prefs = self._build_want_preferences()
        want_terms = 0
        want_terms_met = 0
        soft_restriction_hours = 0
        soft_window_hours = 0
        grid_eligible = 0
        grid_aligned = 0
        activity_type_restrictions = defaultdict(dict)
        for activity_type, day, start, weight in ActivityTypeSchedulingRestriction.objects.filter(
            timetable=self.timetable, weight__gt=0, weight__lt=100
        ).values_list("activity_type", "day", "start", "weight"):
            activity_type_restrictions[(activity_type, day)][work_hours.index(start)] = weight
        realization_windows = {
            (realization_id, day): (
                work_hours.index(start),
                window_boundaries.index(end),
                weight,
            )
            for realization_id, day, start, end, unrestricted, weight in (
                ActivityRealizationSchedulingWindow.objects.filter(timetable=self.timetable).values_list(
                    "realization_id", "day", "start", "end", "unrestricted", "weight"
                )
            )
            if not unrestricted
        }
        teacher_windows = defaultdict(list)
        for teacher_id, day, start, end, unrestricted, unavailable, weight in TeacherSchedulingWindow.objects.filter(
            timetable=self.timetable
        ).values_list("teacher_id", "day", "start", "end", "unrestricted", "unavailable", "weight"):
            if not unrestricted and not unavailable:
                teacher_windows[(teacher_id, day)].append(
                    (work_hours.index(start), window_boundaries.index(end), weight)
                )

        parent_by_group = dict(
            Group.objects.filter(groupset=self.timetable.groupset).values_list("id", "parent_id")
        )
        root_by_group = {}

        def root_group(group_id):
            if group_id not in root_by_group:
                root = group_id
                while parent_by_group.get(root) is not None:
                    root = parent_by_group[root]
                root_by_group[group_id] = root
            return root_by_group[group_id]

        lecture_starts = set()
        lecture_ends = set()
        realization_tag_ids = {
            allocation.activityRealization_id: {
                tag.id for tag in allocation.activityRealization.tags.all()
            }
            | {tag.id for tag in allocation.activityRealization.activity.tags.all()}
            for allocation in allocations
        }
        for allocation in allocations:
            realization = allocation.activityRealization
            day = allocation.day
            start_idx = work_hours.index(allocation.start)
            hours = set(range(start_idx, start_idx + realization.duration))
            tag_ids = realization_tag_ids[realization.id]
            for owner_ids, preferences in (
                ([teacher.id for teacher in realization.teachers.all()], teacher_prefs),
                ([group.id for group in realization.groups.all()], group_prefs),
                (tag_ids, tag_prefs),
            ):
                for owner_id in owner_ids:
                    for pref_day, pref_hours, _weight in preferences.get(owner_id, []):
                        want_terms += 1
                        if pref_day == day and not hours.isdisjoint(pref_hours):
                            want_terms_met += 1
            for hour_idx in hours:
                if activity_type_restrictions[(realization.activity.type, day)].get(hour_idx):
                    soft_restriction_hours += 1

            window = realization_windows.get((realization.id, day))
            if window is None:
                teacher_bounds = [
                    bound
                    for teacher in realization.teachers.all()
                    for bound in teacher_windows[(teacher.id, day)]
                ]
                if teacher_bounds:
                    window = (
                        max(start for start, _end, _weight in teacher_bounds),
                        min(end for _start, end, _weight in teacher_bounds),
                        max(weight for _start, _end, weight in teacher_bounds),
                    )
            if window is not None and 0 < window[2] < 100:
                soft_window_hours += sum(
                    hour_idx < window[0] or hour_idx >= window[1] for hour_idx in hours
                )

            grid_duration = {"P": 3, "LV": 2, "AV": 2}.get(realization.activity.type)
            if grid_duration == realization.duration:
                grid_eligible += 1
                if (start_idx - 1) % grid_duration == 0:
                    grid_aligned += 1
            if realization.activity.type == "P":
                for group in realization.groups.all():
                    root = root_group(group.id)
                    lecture_starts.add((root, day, start_idx))
                    lecture_ends.add((root, day, start_idx + realization.duration))

        lecture_back_to_back = len(lecture_starts & lecture_ends)
        return [
            "Soft constraint summary: WANT terms met={}, missed={}; soft-unavailable hours used={}; soft-window hours outside={}; grid starts aligned={}/{}, missed={}; back-to-back lecture penalties={}.".format(
                want_terms_met,
                want_terms - want_terms_met,
                soft_restriction_hours,
                soft_window_hours,
                grid_aligned,
                grid_eligible,
                grid_eligible - grid_aligned,
                lecture_back_to_back,
            )
        ]

    def _build_contention_messages(
        self, assignment_vars, realizations, realization_teachers, realization_groups
    ):
        """Summarize mandatory teacher/group capacity before CP-SAT search."""
        resources = {}
        realization_candidates = []
        realizations_by_id = {realization.id: realization for realization in realizations}
        for realization in realizations:
            time_slots = set()
            time_candidates = set()
            candidate_count = 0
            for _var, day_idx, start_idx, _room_id, duration in assignment_vars[realization.id]:
                candidate_count += 1
                time_candidates.add((day_idx, start_idx, duration))
                time_slots.update((day_idx, start_idx + offset) for offset in range(duration))
            realization_candidates.append((candidate_count, realization))

            for kind, entities in (
                ("teacher", realization_teachers[realization.id]),
                ("group", realization_groups[realization.id]),
            ):
                for entity in entities:
                    key = (kind, entity.id)
                    resource = resources.setdefault(
                        key,
                        {
                            "entity": entity,
                            "label": (
                                f"{entity} ({entity.code})"
                                if kind == "teacher" and entity.code
                                else str(entity)
                            ),
                            "demand": 0,
                            "slots": set(),
                            "slots_by_day": defaultdict(set),
                            "realizations": set(),
                            "times_by_realization": {},
                            "slots_by_realization": {},
                        },
                    )
                    resource["demand"] += realization.duration
                    resource["slots"].update(time_slots)
                    for day_idx, hour_idx in time_slots:
                        resource["slots_by_day"][day_idx].add(hour_idx)
                    resource["realizations"].add(realization.id)
                    resource["times_by_realization"][realization.id] = time_candidates
                    resource["slots_by_realization"][realization.id] = time_slots

        tight_resources = []
        for (kind, _entity_id), resource in resources.items():
            available = len(resource["slots"])
            if available:
                tight_resources.append((resource["demand"] / available, kind, resource, available))
        tight_resources.sort(key=lambda item: (-item[0], -item[2]["demand"], item[2]["label"]))

        messages = []
        if tight_resources:
            messages.append("Highest mandatory resource contention (demand/feasible slots):")
            for ratio, kind, resource, available in tight_resources[:10]:
                realization_ids = ",".join(str(value) for value in sorted(resource["realizations"])[:12])
                messages.append(
                    f"  {kind}={resource['label']}; demand={resource['demand']}, "
                    f"feasible_slots={available}, utilization={ratio:.0%}, "
                    f"realizations={realization_ids}"
                )

        pair_pressure = []
        for ratio, kind, resource, _available in tight_resources:
            realization_ids = sorted(resource["realizations"])
            for first_index, first_id in enumerate(realization_ids):
                first_times = resource["times_by_realization"][first_id]
                for second_id in realization_ids[first_index + 1:]:
                    second_times = resource["times_by_realization"][second_id]
                    pair_count = len(first_times) * len(second_times)
                    compatible_count = sum(
                        first_day != second_day
                        or first_start + first_duration <= second_start
                        or second_start + second_duration <= first_start
                        for first_day, first_start, first_duration in first_times
                        for second_day, second_start, second_duration in second_times
                    )
                    shared_slots = (
                        resource["slots_by_realization"][first_id]
                        & resource["slots_by_realization"][second_id]
                    )
                    combined_slots = (
                        resource["slots_by_realization"][first_id]
                        | resource["slots_by_realization"][second_id]
                    )
                    compatibility = compatible_count / pair_count if pair_count else 0
                    pair_pressure.append(
                        (
                            compatible_count != 0,
                            -ratio,
                            compatibility,
                            compatible_count,
                            kind,
                            resource,
                            first_id,
                            second_id,
                            shared_slots,
                            combined_slots,
                            pair_count,
                        )
                    )

        pair_pressure.sort(key=lambda row: row[:4] + (row[5]["label"], row[6], row[7]))
        if pair_pressure:
            weekday_codes = [day[0] for day in WEEKDAYS]
            work_hours = [hour[0] for hour in WORKHOURS]
            messages.append(
                "Shared-resource pair pressure (unique time starts; room alternatives ignored):"
            )
            for (
                has_compatible_pair,
                _negative_ratio,
                _compatibility,
                compatible_count,
                kind,
                resource,
                first_id,
                second_id,
                shared_slots,
                combined_slots,
                pair_count,
            ) in pair_pressure[:10]:
                shared_days = sorted({day_idx for day_idx, _hour_idx in shared_slots})
                shared_day_text = ",".join(weekday_codes[day_idx] for day_idx in shared_days) or "none"
                impossible = " IMPOSSIBLE" if not has_compatible_pair else ""
                messages.append(
                    f"  {kind}={resource['label']}; pair=#{first_id}/#{second_id}; "
                    f"shared_feasible_hours={len(shared_slots)}, "
                    f"combined_feasible_hours={len(combined_slots)}, shared_days={shared_day_text}, "
                    f"non_overlapping_start_pairs={compatible_count}/{pair_count}.{impossible}"
                )
                for realization_id in (first_id, second_id):
                    realization = realizations_by_id[realization_id]
                    times = sorted(resource["times_by_realization"][realization_id])
                    displayed_times = ", ".join(
                        f"{weekday_codes[day_idx]} {work_hours[start_idx]}"
                        for day_idx, start_idx, _duration in times[:12]
                    )
                    if len(times) > 12:
                        displayed_times += f", ... (+{len(times) - 12})"
                    messages.append(
                        f"    #{realization.id} {realization.activity.name} "
                        f"[{realization.activity.type}]; duration={realization.duration}, "
                        f"candidate_starts={len(times)}: {displayed_times or 'none'}"
                    )

        realization_candidates.sort(key=lambda item: (item[0], item[1].id))
        if realization_candidates:
            messages.append("Least flexible realizations (candidate room/time placements):")
            for candidate_count, realization in realization_candidates[:10]:
                messages.append(
                    f"  #{realization.id} {realization.activity.name} "
                    f"[{realization.activity.type}]; placements={candidate_count}"
                )
        messages.extend(self._build_workload_contention_messages(resources))
        return messages

    def _build_room_capacity_messages(
        self,
        realizations,
        candidate_rooms,
        qualifying_rooms,
        realization_tag_ids,
        size_adjustments,
        virtual_room_ids,
    ):
        """Highlight room choices that are narrowed materially by capacity."""
        pressure = []
        for realization in realizations:
            required = self._adjusted_size(
                realization, realization_tag_ids, size_adjustments
            )
            eligible = [
                room
                for room in qualifying_rooms.get(realization.id, [])
                if room.id not in virtual_room_ids
            ]
            pre_capacity = [
                room
                for room in candidate_rooms.get(realization.id, [])
                if room.id not in virtual_room_ids
            ]
            undersized = [room for room in pre_capacity if room.capacity < required]
            if not eligible:
                continue
            slack = min(room.capacity - required for room in eligible)
            if not undersized and slack > 25:
                continue
            pressure.append((len(eligible), slack, -required, realization, eligible, undersized))

        if not pressure:
            return []
        pressure.sort(key=lambda row: row[:3])
        messages = ["Classroom capacity pressure (required size and qualifying rooms):"]
        for _count, slack, _required_sort, realization, eligible, undersized in pressure[:15]:
            required = self._adjusted_size(
                realization, realization_tag_ids, size_adjustments
            )
            qualifying = ", ".join(
                "{}({})".format(room.short_name, room.capacity)
                for room in sorted(eligible, key=lambda room: (room.capacity, room.short_name))
            )
            excluded = ", ".join(
                "{}({})".format(room.short_name, room.capacity)
                for room in sorted(undersized, key=lambda room: (room.capacity, room.short_name))
            )
            message = (
                "  #{} {} [{}]; required={}, qualifying={}, minimum_slack={}"
            ).format(
                realization.id,
                realization.activity.name,
                realization.activity.type,
                required,
                qualifying,
                slack,
            )
            if excluded:
                message += "; excluded_by_capacity={}".format(excluded)
            messages.append(message)
        return messages

    def _build_workload_contention_messages(self, resources):
        """Expose hard workload rules omitted from raw candidate-slot contention."""
        constrained = []
        for entity_key, rules in self._build_value_constraints().items():
            resource = resources.get(entity_key)
            if resource is None:
                continue
            values = defaultdict(list)
            for name, value in rules:
                if value is not None:
                    values[name].append(value)
            if not values:
                continue

            max_days_values = values.get("MAXDAYSWEEK", [])
            max_hours_day_values = values.get("MAXHOURSDAY", [])
            min_days_values = values.get("MINDAYSWEEK", [])
            max_days = min(max_days_values) if max_days_values else None
            max_hours_day = min(max_hours_day_values) if max_hours_day_values else None
            day_capacities = [
                min(len(hours), max_hours_day) if max_hours_day is not None else len(hours)
                for hours in resource["slots_by_day"].values()
            ]
            if max_days is not None:
                day_capacities = sorted(day_capacities, reverse=True)[:max_days]
            capacity = sum(day_capacities)
            utilization = resource["demand"] / capacity if capacity else float("inf")
            candidate_days = len(resource["slots_by_day"])
            min_days = max(min_days_values) if min_days_values else None
            rule_text = ", ".join(
                "{}={}".format(name, "/".join(str(value) for value in sorted(set(rule_values))))
                for name, rule_values in sorted(values.items())
            )
            constrained.append(
                (
                    utilization,
                    min_days is not None and candidate_days < min_days,
                    resource,
                    capacity,
                    candidate_days,
                    rule_text,
                )
            )

        if not constrained:
            return []
        constrained.sort(key=lambda item: (not item[1], -item[0], item[2]["label"]))
        messages = ["Hard workload limits (demand / estimated available slots):"]
        for utilization, insufficient_days, resource, capacity, candidate_days, rule_text in constrained[:10]:
            impossible = " IMPOSSIBLE" if utilization > 1 or insufficient_days else ""
            realization_ids = ",".join(str(value) for value in sorted(resource["realizations"])[:12])
            messages.append(
                f"  {resource['label']}; demand={resource['demand']}, "
                f"estimated_slots={capacity}, utilization={utilization:.0%}, "
                f"candidate_days={candidate_days}, rules={rule_text}, "
                f"realizations={realization_ids}.{impossible}"
            )
        return messages

    def _build_forced_placement_messages(
        self,
        assignment_vars,
        realizations,
        realization_teacher_ids,
        realization_group_ids,
        realization_student_ids,
        overlapping_room_ids,
        weekday_codes,
        work_hours,
    ):
        """Report direct conflicts caused by a realization with one placement."""
        messages = []
        forced = [
            realization
            for realization in realizations
            if len(assignment_vars[realization.id]) == 1
        ]
        if not forced:
            return messages

        for forced_realization in forced:
            _var, day_idx, start_idx, room_id, duration = assignment_vars[forced_realization.id][0]
            forced_teachers = set(realization_teacher_ids.get(forced_realization.id, []))
            forced_groups = set(realization_group_ids.get(forced_realization.id, []))
            forced_students = set(realization_student_ids.get(forced_realization.id, []))
            for realization in realizations:
                if realization.id == forced_realization.id:
                    continue
                reasons = []
                if forced_teachers & set(realization_teacher_ids.get(realization.id, [])):
                    reasons.append("teacher")
                if forced_groups & set(realization_group_ids.get(realization.id, [])):
                    reasons.append("group")
                if forced_students & set(realization_student_ids.get(realization.id, [])):
                    reasons.append("student")
                candidates = assignment_vars[realization.id]
                if not reasons and not any(
                    candidate_room_id == room_id and room_id not in overlapping_room_ids
                    for _var, _day_idx, _start_idx, candidate_room_id, _duration in candidates
                ):
                    continue

                def conflicts(candidate):
                    _var, candidate_day, candidate_start, candidate_room, candidate_duration = candidate
                    overlaps = (
                        candidate_day == day_idx
                        and candidate_start < start_idx + duration
                        and start_idx < candidate_start + candidate_duration
                    )
                    return overlaps and (
                        bool(reasons)
                        or (candidate_room == room_id and room_id not in overlapping_room_ids)
                    )

                if candidates and all(conflicts(candidate) for candidate in candidates):
                    room_conflict = any(
                        candidate[3] == room_id and room_id not in overlapping_room_ids
                        for candidate in candidates
                    )
                    conflict_reasons = reasons + (["room"] if room_conflict else [])
                    messages.append(
                        "Forced placement conflict: #{} {} is fixed at {} {} in room {}; "
                        "it eliminates every placement for #{} {} via {}.".format(
                            forced_realization.id,
                            forced_realization.activity.name,
                            weekday_codes[day_idx],
                            work_hours[start_idx],
                            room_id,
                            realization.id,
                            realization.activity.name,
                            ", ".join(conflict_reasons),
                        )
                    )
                    if len(messages) == 10:
                        return ["Direct forced-placement conflicts:"] + messages
        return (["Direct forced-placement conflicts:"] + messages) if messages else []

    def _is_activity_ready_to_schedule(self, activity):
        """Return ``True`` for non-friprosveta activities or friprosveta
        activities flagged ``ready_to_schedule``. The multi-table inheritance
        means ``r.activity`` resolves to the timetable parent; we downcast to
        the friprosveta child when needed."""
        if hasattr(activity, "ready_to_schedule"):
            return bool(activity.ready_to_schedule)
        from friprosveta.models import Activity as FriActivity
        try:
            child = FriActivity.objects.filter(activity_ptr_id=activity.id).first()
        except FriActivity.DoesNotExist:
            return True
        if child is None:
            return True
        return bool(child.ready_to_schedule)

    @staticmethod
    def _is_placeholder_teacher(teacher):
        """`PROSTO, PROSTO` denotes an unassigned teacher, not one person."""
        user = teacher.user
        return (
            user.first_name.strip().casefold() == "prosto"
            and user.last_name.strip().casefold() == "prosto"
        )

    @staticmethod
    def _is_pad_group(group):
        """PAD groups are synthetic enrolment placeholders, not scheduling cohorts."""
        return group.short_name == "VSI_PADALCI" or group.short_name.endswith("_PAD")

    def _build_solver_realization_groups(self, realizations):
        groups_by_realization = {}
        ignored = []
        threshold = self.options.cross_section_group_razor
        for realization in realizations:
            included = []
            for group in realization.groups.all():
                if self._is_pad_group(group):
                    continue
                effective_size = group.size or 0
                if threshold is not None and effective_size < threshold:
                    ignored.append((realization.id, group, effective_size))
                    continue
                included.append(group)
            groups_by_realization[realization.id] = included
        return groups_by_realization, ignored

    def _debug(self, message):
        if self.options.debug:
            self.messages.append(message)

    def _build_room_blocked(self, rooms, weekday_codes, slots_per_day, room_unavailable):
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
        return room_blocked

    def _blocked_slots_for_realization(
        self,
        day_code,
        slots_per_day,
        teacher_ids,
        group_ids,
        teacher_unavailable,
        group_unavailable,
    ):
        blocked = [False] * slots_per_day
        for teacher_id in teacher_ids:
            for hour_idx in teacher_unavailable[teacher_id].get(day_code, set()):
                if 0 <= hour_idx < slots_per_day:
                    blocked[hour_idx] = True
        for group_id in group_ids:
            for hour_idx in group_unavailable[group_id].get(day_code, set()):
                if 0 <= hour_idx < slots_per_day:
                    blocked[hour_idx] = True
        return blocked

    def _build_want_preferences(self):
        prefset = self.timetable.preferenceset
        teacher_time_prefs = defaultdict(list)
        group_time_prefs = defaultdict(list)
        tag_time_prefs = defaultdict(list)
        if prefset is None:
            return teacher_time_prefs, group_time_prefs, tag_time_prefs

        for pref in TeacherTimePreference.objects.filter(preferenceset=prefset, level="WANT"):
            teacher_time_prefs[pref.teacher_id].append(
                (pref.day, set(preference_hours(pref)), pref.weight)
            )
        lineages = self._group_lineage_ids()
        group_preferences = defaultdict(list)
        for pref in GroupTimePreference.objects.filter(
            preferenceset=prefset, level="WANT", group_id__in=lineages
        ):
            group_preferences[pref.group_id].append(pref)
        for group_id, lineage in lineages.items():
            for ancestor_id in lineage:
                for pref in group_preferences[ancestor_id]:
                    group_time_prefs[group_id].append(
                        (pref.day, set(preference_hours(pref)), pref.weight)
                    )

        tagged_preferences = (
            TagTimePreference.objects.filter(preferenceset=prefset, level="WANT")
            .prefetch_related("tag__groups")
            .distinct()
        )
        tag_group_preferences = defaultdict(list)
        for pref in tagged_preferences:
            tag_time_prefs[pref.tag_id].append(
                (pref.day, set(preference_hours(pref)), pref.weight)
            )
            for group in pref.tag.groups.all():
                if group.id in lineages:
                    tag_group_preferences[group.id].append(pref)
        for group_id, lineage in lineages.items():
            for ancestor_id in lineage:
                for pref in tag_group_preferences[ancestor_id]:
                    group_time_prefs[group_id].append(
                        (pref.day, set(preference_hours(pref)), pref.weight)
                    )
        return teacher_time_prefs, group_time_prefs, tag_time_prefs

    def _build_allocation_locks(self, existing_allocations):
        if self.options.scheduling_mode == "scratch":
            return {}
        locks = {}
        for allocation in existing_allocations:
            locks[allocation.activityRealization_id] = allocation
        return locks

    def _build_hard_allocation_locks(self, existing_allocations):
        if self.options.scheduling_mode != "repair":
            return {}
        repair_ids = set(self.options.repair_realization_ids)
        locks = {}
        for allocation in existing_allocations:
            if allocation.activityRealization_id not in repair_ids:
                locks[allocation.activityRealization_id] = allocation
        return locks

    def _add_hard_allocation_lock(
        self, model, assignment_vars, allocation, weekday_codes, work_hours
    ):
        if allocation is None:
            return True
        try:
            day_idx = weekday_codes.index(allocation.day)
            start_idx = work_hours.index(allocation.start)
        except ValueError:
            return False
        matching_vars = [
            var
            for var, var_day_idx, var_start_idx, room_id, _duration in assignment_vars
            if var_day_idx == day_idx
            and var_start_idx == start_idx
            and room_id == allocation.classroom_id
        ]
        if not matching_vars:
            return False
        model.Add(sum(matching_vars) == 1)
        return True

    def _build_realization_tag_ids(self, realizations):
        tag_ids = {}
        for realization in realizations:
            ids = set(realization.tags.values_list("id", flat=True))
            ids.update(realization.activity.tags.values_list("id", flat=True))
            tag_ids[realization.id] = ids
        return tag_ids

    def _build_tag_size_adjustments(self):
        """Return per-tag size adjustment preferences keyed by tag id.

        Each entry is a tuple ``(kind, value)`` where ``kind`` is either
        ``SHRINKGROUPS`` (subtract the value from the realization size) or
        ``MULSIZE`` (multiply the realization size by ``value/100``).
        The most restrictive adjustment per tag wins (largest shrink).
        """
        prefset = self.timetable.preferenceset
        adjustments = {}
        if prefset is None:
            return adjustments
        for pref in TagValuePreference.objects.filter(
            preferenceset=prefset,
            name__in=("SHRINKGROUPS", "MULSIZE"),
        ).select_related("tag"):
            tag_id = pref.tag_id
            if pref.name == "SHRINKGROUPS":
                kind, value = "SHRINKGROUPS", pref.value
            else:
                kind, value = "MULSIZE", pref.value
            existing = adjustments.get(tag_id)
            if existing is None:
                adjustments[tag_id] = (kind, value)
                continue
            existing_kind, existing_value = existing
            if existing_kind == "SHRINKGROUPS":
                if kind == "SHRINKGROUPS":
                    adjustments[tag_id] = ("SHRINKGROUPS", max(existing_value, value))
                else:
                    adjustments[tag_id] = ("SHRINKGROUPS", max(existing_value, value))
            else:
                if kind == "SHRINKGROUPS":
                    adjustments[tag_id] = ("SHRINKGROUPS", value)
                else:
                    existing_factor = existing_value / 100.0
                    new_factor = value / 100.0
                    factor = min(existing_factor, new_factor)
                    adjustments[tag_id] = ("MULSIZE", int(round(factor * 100)))
        return adjustments

    def _adjusted_size(self, realization, realization_tag_ids, size_adjustments):
        """Apply ``SHRINKGROUPS`` and ``MULSIZE`` tag preferences to a
        realization's retained solver-group size."""
        size = getattr(self, "_solver_group_size_by_realization", {}).get(
            realization.id, realization.size
        )
        tag_ids = realization_tag_ids.get(realization.id, set())
        shrink_amount = 0
        mul_factor = 1.0
        for tag_id in tag_ids:
            adjustment = size_adjustments.get(tag_id)
            if adjustment is None:
                continue
            kind, value = adjustment
            if kind == "SHRINKGROUPS":
                shrink_amount = max(shrink_amount, value)
            else:
                mul_factor = min(mul_factor, value / 100.0)
        size = max(0, size - shrink_amount)
        size = math.ceil(size * mul_factor)
        return max(size, 0)

    def _build_teacher_unavailable(self):
        unavailable = defaultdict(lambda: defaultdict(set))
        prefset = self.timetable.preferenceset
        for teacher in self.timetable.teachers.all():
            for pref in teacher.time_preferences.filter(
                preferenceset=prefset, level__in=HARD_UNAVAILABLE_LEVELS
            ):
                unavailable[teacher.id][pref.day].update(preference_hours(pref))
            for pref in TagTimePreference.objects.filter(
                preferenceset=prefset,
                tag__teachers=teacher,
                level__in=HARD_UNAVAILABLE_LEVELS,
            ).distinct():
                unavailable[teacher.id][pref.day].update(preference_hours(pref))

        for allocation in self._respected_allocations():
            hours = hour_strings_to_indices(allocation.hours)
            for teacher in allocation.teachers.all():
                unavailable[teacher.id][allocation.day].update(hours)

        return unavailable

    def _group_lineage_ids(self):
        if hasattr(self, "_cached_group_lineage_ids"):
            return self._cached_group_lineage_ids

        groups = list(
            Group.objects.filter(groupset=self.timetable.groupset).select_related(
                "parent"
            )
        )
        group_by_id = {group.id: group for group in groups}
        lineages = {}
        for group in groups:
            lineage = []
            current = group
            visited = set()
            while current is not None and current.id not in visited:
                visited.add(current.id)
                lineage.append(current.id)
                current = group_by_id.get(current.parent_id)
            lineages[group.id] = lineage
        self._cached_group_lineage_ids = lineages
        return lineages

    def _build_group_unavailable(self):
        unavailable = defaultdict(lambda: defaultdict(set))
        prefset = self.timetable.preferenceset
        lineages = self._group_lineage_ids()
        group_preferences = defaultdict(list)
        for pref in GroupTimePreference.objects.filter(
            preferenceset=prefset,
            level__in=HARD_UNAVAILABLE_LEVELS,
            group_id__in=lineages,
        ):
            group_preferences[pref.group_id].append(pref)

        tag_preferences = defaultdict(list)
        tagged_preferences = (
            TagTimePreference.objects.filter(
                preferenceset=prefset,
                level__in=HARD_UNAVAILABLE_LEVELS,
                tag__groups__id__in=lineages,
            )
            .prefetch_related("tag__groups")
            .distinct()
        )
        for pref in tagged_preferences:
            for group in pref.tag.groups.all():
                if group.id in lineages:
                    tag_preferences[group.id].append(pref)

        for group_id, lineage in lineages.items():
            for ancestor_id in lineage:
                for pref in group_preferences[ancestor_id]:
                    unavailable[group_id][pref.day].update(preference_hours(pref))
                for pref in tag_preferences[ancestor_id]:
                    unavailable[group_id][pref.day].update(preference_hours(pref))

        for allocation in self._respected_allocations():
            hours = hour_strings_to_indices(allocation.hours)
            for group in allocation.groups.all():
                unavailable[group.id][allocation.day].update(hours)

        return unavailable

    def _build_room_unavailable(self):
        unavailable = defaultdict(lambda: defaultdict(set))
        for allocation in self._respected_allocations():
            if allocation.classroom is None:
                continue
            if allocation.classroom.allow_overlaps:
                continue
            unavailable[allocation.classroom.id][allocation.day].update(
                hour_strings_to_indices(allocation.hours)
            )
        return unavailable

    def _respected_allocations(self):
        if not hasattr(self, "_cached_respected_allocations"):
            respected_timetables = list(self.timetable.respects.all())
            respected_allocations = list(
                Allocation.objects.filter(timetable__in=respected_timetables)
            )

            if respected_timetables:
                timetable_ids_with_allocation = {
                    allocation.timetable_id for allocation in respected_allocations
                }
                empty_respected_timetables = [
                    timetable.slug
                    for timetable in respected_timetables
                    if timetable.id not in timetable_ids_with_allocation
                ]
                if empty_respected_timetables:
                    self.messages.append(
                        "Warning: respected timetable(s) "
                        + ", ".join(empty_respected_timetables)
                        + " have no allocations; they do not enforce any hard timetable locks."
                    )

            self._cached_respected_allocations = respected_allocations

        return self._cached_respected_allocations

    def _build_realization_student_ids(self, realizations, realization_groups=None):
        realization_student_ids = {}
        for realization in realizations:
            student_ids = set()
            groups = (
                realization_groups.get(realization.id, [])
                if realization_groups is not None
                else realization.groups.all()
            )
            for group in groups:
                if self._is_pad_group(group):
                    continue
                for student in group.students.all():
                    student_ids.add(student.id)
            if student_ids:
                realization_student_ids[realization.id] = student_ids
        return realization_student_ids

    def _build_fixed_allocation_occupancy(
        self,
        allocations,
        realization_groups,
        realization_student_ids,
        weekday_codes,
        work_hours,
    ):
        """Index allocations excluded from a ready-only run as fixed occupancy."""
        occupancy = defaultdict(
            lambda: {
                "teacher_ids": set(),
                "group_ids": set(),
                "student_sets": [],
                "room_ids": set(),
            }
        )
        group_lineages = self._group_lineage_ids()
        conflicting_group_ids = defaultdict(set)
        for group_id, lineage in group_lineages.items():
            for related_id in lineage:
                conflicting_group_ids[group_id].add(related_id)
                conflicting_group_ids[related_id].add(group_id)

        for allocation in allocations:
            try:
                day_idx = weekday_codes.index(allocation.day)
                start_idx = work_hours.index(allocation.start)
            except ValueError:
                return {}, (
                    "Preserved allocation {} for realization {} has an invalid day or "
                    "start time; aborting without writing allocations."
                ).format(allocation.id, allocation.activityRealization_id)

            duration = allocation.duration
            if duration <= 0 or start_idx + duration > len(work_hours):
                return {}, (
                    "Preserved allocation {} for realization {} has invalid duration {}; "
                    "aborting without writing allocations."
                ).format(
                    allocation.id,
                    allocation.activityRealization_id,
                    duration,
                )

            realization = allocation.activityRealization
            teacher_ids = {
                teacher.id
                for teacher in realization.teachers.all()
                if not self._is_placeholder_teacher(teacher)
            }
            group_ids = {
                related_id
                for group in realization_groups.get(realization.id, [])
                for related_id in conflicting_group_ids.get(group.id, {group.id})
            }
            student_ids = set(realization_student_ids.get(realization.id, set()))
            room_id = None
            if (
                allocation.classroom is not None
                and not allocation.classroom.allow_overlaps
                and not allocation.classroom.is_virtual
            ):
                room_id = allocation.classroom_id

            for hour_idx in range(start_idx, start_idx + duration):
                slot = occupancy[(day_idx, hour_idx)]
                slot["teacher_ids"].update(teacher_ids)
                slot["group_ids"].update(group_ids)
                if student_ids:
                    slot["student_sets"].append(student_ids)
                if room_id is not None:
                    slot["room_ids"].add(room_id)

        return occupancy, None

    def _placement_conflicts_with_fixed_occupancy(
        self,
        occupancy,
        day_idx,
        start_idx,
        duration,
        teacher_ids,
        group_ids,
        student_ids,
        room_id,
        overlapping_room_ids,
    ):
        teacher_ids = set(teacher_ids)
        group_ids = set(group_ids)
        student_ids = set(student_ids)
        for hour_idx in range(start_idx, start_idx + duration):
            slot = occupancy.get((day_idx, hour_idx))
            if slot is None:
                continue
            if teacher_ids & slot["teacher_ids"]:
                return True
            if group_ids & slot["group_ids"]:
                return True
            if self.options.cross_section_razor is None:
                if any(student_ids & fixed_ids for fixed_ids in slot["student_sets"]):
                    return True
            elif any(
                len(student_ids & fixed_ids) > self.options.cross_section_razor
                for fixed_ids in slot["student_sets"]
            ):
                return True
            if (
                room_id not in overlapping_room_ids
                and room_id in slot["room_ids"]
            ):
                return True
        return False

    def _teacher_site_cycles(self, realizations):
        """Map each activity/teacher pair to its required physical realizations."""
        from frinajave.models import TeacherSubjectCycles
        from friprosveta.models import Activity as FriActivity

        activities = {
            activity.activity_ptr_id: activity
            for activity in FriActivity.objects.filter(
                activity_ptr_id__in={r.activity_id for r in realizations}
            ).select_related("subject", "lecture_type")
        }
        entries = defaultdict(lambda: {"cycles": 0, "cycles_on_site": 0})
        for entry in TeacherSubjectCycles.objects.filter(
            timetable_set__timetables=self.timetable,
            cycles__gt=0,
        ):
            key = (entry.subject_code, entry.lecture_type, entry.teacher_code)
            entries[key]["cycles"] += entry.cycles
            entries[key]["cycles_on_site"] += (
                entry.cycles if entry.cycles_on_site is None else entry.cycles_on_site
            )

        realization_ids = defaultdict(list)
        teachers = {}
        for realization in realizations:
            activity = activities.get(realization.activity_id)
            if activity is None:
                continue
            for teacher in realization.teachers.all():
                teachers[teacher.id] = teacher
                realization_ids[(realization.activity_id, teacher.id)].append(realization.id)

        result = {}
        for (activity_id, teacher_id), ids in realization_ids.items():
            activity = activities[activity_id]
            teacher = teachers[teacher_id]
            entry = entries.get(
                (activity.subject.code, activity.lecture_type_id, teacher.code)
            )
            if entry is None:
                continue
            remote_count = math.ceil(entry["cycles"] - entry["cycles_on_site"])
            physical_count = max(0, len(ids) - max(0, remote_count))
            result[(activity_id, teacher_id)] = {
                "physical_count": physical_count,
                "realization_ids": ids,
            }
        return result

    def _add_teacher_site_cycle_constraints(
        self, model, assignment_vars, teacher_site_cycles, virtual_room_ids
    ):
        for data in teacher_site_cycles.values():
            physical_assignments = [
                var
                for realization_id in data["realization_ids"]
                for var, _day, _start, room_id, _duration in assignment_vars[realization_id]
                if room_id not in virtual_room_ids
            ]
            model.Add(sum(physical_assignments) == data["physical_count"])

    def _add_no_overlap_constraints(
        self,
        model,
        assignment_vars,
        realizations,
        realization_teacher_ids,
        realization_group_ids,
        realization_student_ids=None,
        overlapping_room_ids=None,
    ):
        teacher_map = defaultdict(list)
        group_map = defaultdict(list)
        room_map = defaultdict(list)
        student_map = defaultdict(list)
        enforce_individual_student_overlap = self.options.cross_section_razor is None
        parent_child_pairs = set()
        parent_by_group = dict(
            Group.objects.filter(groupset=self.timetable.groupset).values_list("id", "parent_id")
        )

        for realization in realizations:
            teacher_ids = realization_teacher_ids.get(realization.id, [])
            group_ids = realization_group_ids.get(realization.id, [])
            student_ids = []
            if enforce_individual_student_overlap and realization_student_ids is not None:
                student_ids = realization_student_ids.get(realization.id, [])
            for group_id in group_ids:
                parent_id = parent_by_group.get(group_id)
                while parent_id is not None:
                    parent_child_pairs.add((parent_id, group_id))
                    parent_id = parent_by_group.get(parent_id)
            for var, day_idx, start_idx, room_id, duration in assignment_vars.get(realization.id, []):
                for offset in range(duration):
                    hour_idx = start_idx + offset
                    for teacher_id in teacher_ids:
                        teacher_map[(teacher_id, day_idx, hour_idx)].append(var)
                    for group_id in group_ids:
                        group_map[(group_id, day_idx, hour_idx)].append(var)
                    for student_id in student_ids:
                        student_map[(student_id, day_idx, hour_idx)].append(var)
                    if room_id not in (overlapping_room_ids or set()):
                        room_map[(room_id, day_idx, hour_idx)].append(var)

        for vars_list in teacher_map.values():
            if len(vars_list) > 1:
                model.Add(sum(vars_list) <= 1)
        for vars_list in group_map.values():
            if len(vars_list) > 1:
                model.Add(sum(vars_list) <= 1)
        for parent_id, child_id in parent_child_pairs:
            for day_idx in range(len(WEEKDAYS)):
                for hour_idx in range(len(WORKHOURS)):
                    parent_vars = set(group_map[(parent_id, day_idx, hour_idx)])
                    child_vars = set(group_map[(child_id, day_idx, hour_idx)])
                    parent_only = parent_vars - child_vars
                    child_only = child_vars - parent_vars
                    if parent_only and child_only:
                        model.Add(sum(parent_only) + sum(child_only) <= 1)
        for vars_list in student_map.values():
            if len(vars_list) > 1:
                model.Add(sum(vars_list) <= 1)
        for vars_list in room_map.values():
            if len(vars_list) > 1:
                model.Add(sum(vars_list) <= 1)

    def _add_consecutive_teacher_room_preferences(
        self,
        model,
        objective_terms,
        assignment_vars,
        realizations,
        realization_teacher_ids,
    ):
        """Prefer a teacher's adjacent realizations to remain in one room."""
        realizations_by_teacher = defaultdict(list)
        for realization in realizations:
            for teacher_id in realization_teacher_ids.get(realization.id, []):
                realizations_by_teacher[teacher_id].append(realization)
        rewarded_pairs = set()
        for teacher_realizations in realizations_by_teacher.values():
            realizations_by_activity = defaultdict(list)
            for realization in teacher_realizations:
                realizations_by_activity[realization.activity_id].append(realization)
            for activity_realizations in realizations_by_activity.values():
                ordered_realizations = sorted(activity_realizations, key=lambda r: r.id)
                for first, second in zip(ordered_realizations, ordered_realizations[1:]):
                    second_starts = {
                        (day_idx, start_idx, room_id): (var, duration)
                        for var, day_idx, start_idx, room_id, duration in assignment_vars.get(
                            second.id, []
                        )
                    }
                    second_ends = {
                        (day_idx, start_idx + duration, room_id): (var, duration)
                        for var, day_idx, start_idx, room_id, duration in assignment_vars.get(
                            second.id, []
                        )
                    }
                    for first_var, day_idx, start_idx, room_id, first_duration in assignment_vars.get(
                        first.id, []
                    ):
                        for second_assignment in (
                            second_starts.get((day_idx, start_idx + first_duration, room_id)),
                            second_ends.get((day_idx, start_idx, room_id)),
                        ):
                            if second_assignment is None:
                                continue
                            second_var, _second_duration = second_assignment
                            pair = tuple(sorted((first_var.Index(), second_var.Index())))
                            if pair in rewarded_pairs:
                                continue
                            rewarded_pairs.add(pair)
                            adjacent_same_room = model.NewBoolVar(
                                "teacher_room_{}_{}".format(pair[0], pair[1])
                            )
                            model.Add(adjacent_same_room <= first_var)
                            model.Add(adjacent_same_room <= second_var)
                            model.Add(adjacent_same_room >= first_var + second_var - 1)
                            objective_terms.append(
                                self._automatic_weight(
                                    "consecutive_teacher_room_weight",
                                    CONSECUTIVE_TEACHER_ROOM_WEIGHT,
                                )
                                * adjacent_same_room
                            )

    def _add_room_compactness_preferences(
        self, model, objective_terms, assignment_vars, overlapping_room_ids
    ):
        """Prefer adjacent occupied slots in physical rooms to reduce idle gaps."""
        room_slots = defaultdict(list)
        for assignments in assignment_vars.values():
            for var, day_idx, start_idx, room_id, duration in assignments:
                if room_id in overlapping_room_ids:
                    continue
                for hour_idx in range(start_idx, start_idx + duration):
                    room_slots[(room_id, day_idx, hour_idx)].append(var)
        busy_slots = {}
        for key, vars_for_slot in room_slots.items():
            busy = model.NewBoolVar("room_busy_{}_{}_{}".format(*key))
            model.AddMaxEquality(busy, vars_for_slot)
            busy_slots[key] = busy
        for room_id, day_idx, hour_idx in list(busy_slots):
            next_busy = busy_slots.get((room_id, day_idx, hour_idx + 1))
            if next_busy is None:
                continue
            adjacent = model.NewBoolVar(
                "room_adjacent_{}_{}_{}".format(room_id, day_idx, hour_idx)
            )
            model.Add(adjacent <= busy_slots[(room_id, day_idx, hour_idx)])
            model.Add(adjacent <= next_busy)
            model.Add(adjacent >= busy_slots[(room_id, day_idx, hour_idx)] + next_busy - 1)
            objective_terms.append(
                self._automatic_weight("room_adjacency_weight", ROOM_ADJACENCY_WEIGHT)
                * adjacent
            )

    def _add_lecture_back_to_back_penalties(
        self, model, objective_terms, assignment_vars, realizations, realization_group_ids
    ):
        """Prefer a free slot between distinct lectures for each student group."""
        parent_by_group = dict(
            Group.objects.filter(groupset=self.timetable.groupset).values_list("id", "parent_id")
        )
        root_by_group = {}

        def root_group(group_id):
            if group_id not in root_by_group:
                root = group_id
                while parent_by_group.get(root) is not None:
                    root = parent_by_group[root]
                root_by_group[group_id] = root
            return root_by_group[group_id]

        lecture_starts = defaultdict(list)
        lecture_ends = defaultdict(list)
        for realization in realizations:
            if realization.activity.type != "P":
                continue
            group_roots = {
                root_group(group_id)
                for group_id in realization_group_ids.get(realization.id, [])
            }
            for var, day_idx, start_idx, _room_id, duration in assignment_vars.get(
                realization.id, []
            ):
                for group_root in group_roots:
                    lecture_starts[(group_root, day_idx, start_idx)].append(var)
                    lecture_ends[(group_root, day_idx, start_idx + duration)].append(var)

        for key, ending_vars in lecture_ends.items():
            starting_vars = lecture_starts.get(key)
            if not starting_vars:
                continue
            ending = model.NewBoolVar("lecture_ending_{}_{}_{}".format(*key))
            starting = model.NewBoolVar("lecture_starting_{}_{}_{}".format(*key))
            model.AddMaxEquality(ending, ending_vars)
            model.AddMaxEquality(starting, starting_vars)
            back_to_back = model.NewBoolVar("lecture_back_to_back_{}_{}_{}".format(*key))
            model.Add(back_to_back <= ending)
            model.Add(back_to_back <= starting)
            model.Add(back_to_back >= ending + starting - 1)
            objective_terms.append(
                -self._automatic_weight(
                    "lecture_back_to_back_penalty", LECTURE_BACK_TO_BACK_PENALTY
                )
                * back_to_back
            )

    def _add_workload_constraints(
        self,
        model,
        assignment_vars,
        realizations,
        realization_teacher_ids,
        realization_group_ids,
    ):
        occupancy = self._build_entity_occupancy(
            assignment_vars, realizations, realization_teacher_ids, realization_group_ids
        )
        value_constraints = self._build_value_constraints()
        slots_per_day = len(WORKHOURS)

        for entity_key, constraints in value_constraints.items():
            for name, value in constraints:
                if value is None:
                    continue
                if name == "MAXHOURSDAY":
                    for day_idx in range(len(WEEKDAYS)):
                        vars_for_day = []
                        for hour_idx in range(slots_per_day):
                            vars_for_day.extend(occupancy.get((entity_key, day_idx, hour_idx), []))
                        if vars_for_day:
                            model.Add(sum(vars_for_day) <= value)
                elif name == "MAXHOURSCONT":
                    window = value + 1
                    for day_idx in range(len(WEEKDAYS)):
                        for start_idx in range(0, slots_per_day - window + 1):
                            vars_for_window = []
                            for hour_idx in range(start_idx, start_idx + window):
                                vars_for_window.extend(
                                    occupancy.get((entity_key, day_idx, hour_idx), [])
                                )
                            if vars_for_window:
                                model.Add(sum(vars_for_window) <= value)
                elif name == "MAXSPANDAY":
                    for day_idx in range(len(WEEKDAYS)):
                        for first_hour in range(0, slots_per_day - value):
                            for last_hour in range(first_hour + value, slots_per_day):
                                endpoint_vars = (
                                    occupancy.get((entity_key, day_idx, first_hour), [])
                                    + occupancy.get((entity_key, day_idx, last_hour), [])
                                )
                                if endpoint_vars:
                                    model.Add(sum(endpoint_vars) <= 1)
                elif name in ("MAXDAYSWEEK", "MINDAYSWEEK"):
                    active_days = []
                    for day_idx in range(len(WEEKDAYS)):
                        day_vars = []
                        for hour_idx in range(slots_per_day):
                            day_vars.extend(occupancy.get((entity_key, day_idx, hour_idx), []))
                        if day_vars:
                            active = model.NewBoolVar(
                                f"active_{entity_key[0]}_{entity_key[1]}_{day_idx}"
                            )
                            model.AddMaxEquality(active, day_vars)
                            active_days.append(active)
                    if active_days and name == "MAXDAYSWEEK":
                        model.Add(sum(active_days) <= value)
                    elif active_days and name == "MINDAYSWEEK":
                        model.Add(sum(active_days) >= value)

    def _build_entity_occupancy(
        self,
        assignment_vars,
        realizations,
        realization_teacher_ids,
        realization_group_ids,
    ):
        occupancy = defaultdict(list)
        for realization in realizations:
            entity_keys = []
            entity_keys.extend(
                ("teacher", teacher_id)
                for teacher_id in realization_teacher_ids.get(realization.id, [])
            )
            entity_keys.extend(
                ("group", group_id)
                for group_id in realization_group_ids.get(realization.id, [])
            )
            for var, day_idx, start_idx, _room_id, duration in assignment_vars.get(
                realization.id, []
            ):
                for offset in range(duration):
                    for entity_key in entity_keys:
                        occupancy[(entity_key, day_idx, start_idx + offset)].append(var)
        return occupancy

    def _add_lecture_group_hour_limits(
        self, model, assignment_vars, realizations, realization_group_ids
    ):
        constraints = SolverConstraint.objects.filter(
            timetable=self.timetable,
            active=True,
            constraint_type="MAXLECTUREHOURSDAY",
            value__isnull=False,
        ).prefetch_related("groups")
        if not constraints:
            return

        parent_by_group = dict(
            Group.objects.filter(groupset=self.timetable.groupset).values_list("id", "parent_id")
        )
        root_by_group = {}

        def root_group(group_id):
            if group_id not in root_by_group:
                root = group_id
                while parent_by_group.get(root) is not None:
                    root = parent_by_group[root]
                root_by_group[group_id] = root
            return root_by_group[group_id]

        lecture_roots = {
            realization.id: {root_group(group_id) for group_id in realization_group_ids.get(realization.id, [])}
            for realization in realizations
            if realization.activity.type == "P"
        }
        for constraint in constraints:
            selected_roots = {root_group(group.id) for group in constraint.groups.all()}
            if not selected_roots:
                continue
            for selected_root in selected_roots:
                for day_idx in range(len(WEEKDAYS)):
                    terms = []
                    for realization in realizations:
                        if selected_root not in lecture_roots.get(realization.id, set()):
                            continue
                        terms.extend(
                            duration * var
                            for var, candidate_day, _start, _room, duration in assignment_vars.get(realization.id, [])
                            if candidate_day == day_idx
                        )
                    if terms:
                        model.Add(sum(terms) <= constraint.value)

    def _build_value_constraints(self):
        constraints = defaultdict(list)
        prefset = self.timetable.preferenceset
        for pref in TeacherValuePreference.objects.filter(preferenceset=prefset):
            constraints[("teacher", pref.teacher_id)].append((pref.name, pref.value))
        for pref in GroupValuePreference.objects.filter(preferenceset=prefset):
            constraints[("group", pref.group_id)].append((pref.name, pref.value))
        for constraint in SolverConstraint.objects.filter(
            timetable=self.timetable, active=True
        ):
            if constraint.constraint_type not in (
                "MAXDAYSWEEK",
                "MINDAYSWEEK",
                "MAXHOURSDAY",
                "MAXHOURSCONT",
                "MAXSPANDAY",
                "MINCHANGEGAP",
            ):
                continue
            for teacher_id in constraint.teachers.values_list("id", flat=True):
                constraints[("teacher", teacher_id)].append(
                    (constraint.constraint_type, constraint.value)
                )
            for group_id in constraint.groups.values_list("id", flat=True):
                constraints[("group", group_id)].append(
                    (constraint.constraint_type, constraint.value)
                )
        return constraints

    def _add_movement_constraints(
        self,
        model,
        assignment_vars,
        realizations,
        realization_teacher_ids,
        realization_group_ids,
        room_locations,
    ):
        value_constraints = self._build_value_constraints()
        min_change_gaps = {
            entity_key: max(value for name, value in constraints if name == "MINCHANGEGAP" and value is not None)
            for entity_key, constraints in value_constraints.items()
            if any(name == "MINCHANGEGAP" and value is not None for name, value in constraints)
        }
        if not min_change_gaps:
            return

        realization_entities = {}
        for realization in realizations:
            entities = set()
            entities.update(
                ("teacher", teacher_id)
                for teacher_id in realization_teacher_ids.get(realization.id, [])
            )
            entities.update(
                ("group", group_id)
                for group_id in realization_group_ids.get(realization.id, [])
            )
            realization_entities[realization.id] = entities

        for idx, r1 in enumerate(realizations):
            for r2 in realizations[idx + 1:]:
                shared_entities = realization_entities[r1.id] & realization_entities[r2.id]
                constrained_entities = [e for e in shared_entities if e in min_change_gaps]
                if not constrained_entities:
                    continue
                min_gap = max(min_change_gaps[e] for e in constrained_entities)
                for var1, day1, start1, room1, duration1 in assignment_vars.get(r1.id, []):
                    end1 = start1 + duration1
                    for var2, day2, start2, room2, duration2 in assignment_vars.get(r2.id, []):
                        if day1 != day2:
                            continue
                        if room_locations.get(room1) == room_locations.get(room2):
                            continue
                        end2 = start2 + duration2
                        if 0 <= start2 - end1 < min_gap or 0 <= start1 - end2 < min_gap:
                            model.Add(var1 + var2 <= 1)

    def _add_building_change_constraints(
        self,
        model,
        assignment_vars,
        realizations,
        realization_teacher_ids,
        realization_group_ids,
        room_locations,
        location_index,
    ):
        """Enforce ``MAXCHANGESDAY`` and ``MAXCHANGESWEEK`` value preferences for
        teachers and groups (and first-class ``SolverConstraint`` entries).

        The model uses adjacent-slot transitions: a transition counts when the
        entity is occupied in one building at hour ``h`` and a different
        building at hour ``h + 1`` on the same day. This captures the bulk of
        FET's "building changes between consecutive activities" semantics for
        back-to-back schedules; transitions across hour gaps are intentionally
        not counted, so this is a lower-bound approximation that should be
        refined with adjacency-aware ordering in a follow-up.
        """
        value_constraints = self._build_value_constraints()
        entity_limits = {}
        for entity_key, constraints in value_constraints.items():
            day_limit = None
            week_limit = None
            for name, value in constraints:
                if value is None:
                    continue
                if name == "MAXCHANGESDAY":
                    day_limit = value if day_limit is None else min(day_limit, value)
                elif name == "MAXCHANGESWEEK":
                    week_limit = value if week_limit is None else min(week_limit, value)
            if day_limit is not None or week_limit is not None:
                entity_limits[entity_key] = (day_limit, week_limit)
        if not entity_limits:
            return

        slots_per_day = len(WORKHOURS)
        days_count = len(WEEKDAYS)

        occupancy_by_edge = defaultdict(list)
        for realization in realizations:
            entity_keys = []
            entity_keys.extend(
                ("teacher", teacher_id)
                for teacher_id in realization_teacher_ids.get(realization.id, [])
            )
            entity_keys.extend(
                ("group", group_id)
                for group_id in realization_group_ids.get(realization.id, [])
            )
            entity_keys = [key for key in entity_keys if key in entity_limits]
            if not entity_keys:
                continue
            for var, day_idx, start_idx, room_id, duration in assignment_vars.get(realization.id, []):
                loc = room_locations.get(room_id)
                if loc is None:
                    continue
                loc_idx = location_index.get(loc)
                if loc_idx is None:
                    continue
                for offset in range(duration):
                    hour_idx = start_idx + offset
                    for entity_key in entity_keys:
                        occupancy_by_edge[(entity_key, day_idx, hour_idx, loc_idx)].append(var)

        per_day = defaultdict(list)
        per_week = defaultdict(list)
        for entity_key, day_limit, week_limit in [
            (key, limits[0], limits[1]) for key, limits in entity_limits.items()
        ]:
            for day_idx in range(days_count):
                for hour_idx in range(slots_per_day - 1):
                    edges = []
                    for loc_idx, vars_at_loc in self._group_by_location(
                        occupancy_by_edge, entity_key, day_idx, hour_idx
                    ).items():
                        next_locations = self._group_by_location(
                            occupancy_by_edge, entity_key, day_idx, hour_idx + 1
                        )
                        for other_loc_idx, next_vars in next_locations.items():
                            if other_loc_idx == loc_idx:
                                continue
                            occ_here = self._or_with_channeling(
                                model, vars_at_loc,
                                f"occ_{entity_key[0]}{entity_key[1]}_d{day_idx}_h{hour_idx}_L{loc_idx}",
                            )
                            occ_next = self._or_with_channeling(
                                model, next_vars,
                                f"occ_{entity_key[0]}{entity_key[1]}_d{day_idx}_h{hour_idx + 1}_L{other_loc_idx}",
                            )
                            pair = model.NewBoolVar(
                                f"chg_{entity_key[0]}{entity_key[1]}_d{day_idx}_h{hour_idx}_L{loc_idx}_{other_loc_idx}"
                            )
                            model.AddImplication(pair, occ_here)
                            model.AddImplication(pair, occ_next)
                            model.Add(occ_here + occ_next - 1 <= pair)
                            edges.append(pair)
                    if not edges:
                        continue
                    transition = model.NewBoolVar(
                        f"trans_{entity_key[0]}{entity_key[1]}_d{day_idx}_h{hour_idx}"
                    )
                    model.AddMaxEquality(transition, edges)
                    per_day[(entity_key, day_idx)].append(transition)
                    per_week[entity_key].append(transition)

        for (entity_key, day_idx), transitions in per_day.items():
            day_limit = entity_limits[entity_key][0]
            if day_limit is not None and transitions:
                model.Add(sum(transitions) <= day_limit)
        for entity_key, transitions in per_week.items():
            week_limit = entity_limits[entity_key][1]
            if week_limit is not None and transitions:
                model.Add(sum(transitions) <= week_limit)

    @staticmethod
    def _group_by_location(occupancy_by_edge, entity_key, day_idx, hour_idx):
        grouped = defaultdict(list)
        for (key, d, h, loc_idx), vars_list in occupancy_by_edge.items():
            if key != entity_key or d != day_idx or h != hour_idx:
                continue
            grouped[loc_idx].extend(vars_list)
        return grouped

    @staticmethod
    def _or_with_channeling(model, vars_list, name):
        if not vars_list:
            return model.NewConstant(0)
        result = model.NewBoolVar(name)
        model.AddMaxEquality(result, vars_list)
        return result

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
                        self._add_pair_no_overlap(model, start_vars, r1, r2)

        for realization in realizations:
            for after in realization.activity.before.all():
                for r1 in realizations_by_activity.get(realization.activity_id, []):
                    for r2 in realizations_by_activity.get(after.id, []):
                        model.Add(start_vars[r1.id] + r1.duration <= start_vars[r2.id])

    def _add_lv_av_parent_group_no_overlap(
        self, model, start_vars, realizations, realization_groups
    ):
        """Keep AV and LV realizations separate when their groups are siblings."""
        parent_ids_by_realization = {
            realization.id: {
                group.parent_id
                for group in realization_groups.get(realization.id, [])
                if group.parent_id is not None
            }
            for realization in realizations
        }
        lv_realizations = [r for r in realizations if r.activity.type == "LV"]
        av_realizations = [r for r in realizations if r.activity.type == "AV"]
        for lv_realization in lv_realizations:
            lv_parents = parent_ids_by_realization[lv_realization.id]
            if not lv_parents:
                continue
            for av_realization in av_realizations:
                if lv_parents.intersection(parent_ids_by_realization[av_realization.id]):
                    self._add_pair_no_overlap(
                        model, start_vars, lv_realization, av_realization)

    def _add_subject_lecture_exercise_no_overlap(self, model, start_vars, realizations):
        """Never overlap a subject's lectures with its LV or AV exercises."""
        lectures_by_subject = defaultdict(list)
        exercises_by_subject = defaultdict(list)
        for realization in realizations:
            try:
                subject_id = realization.activity.activity.subject_id
            except ObjectDoesNotExist:
                continue
            if subject_id is None:
                continue
            if realization.activity.type == "P":
                lectures_by_subject[subject_id].append(realization)
            elif realization.activity.type in ("LV", "AV"):
                exercises_by_subject[subject_id].append(realization)
        for subject_id, lectures in lectures_by_subject.items():
            for lecture in lectures:
                for exercise in exercises_by_subject.get(subject_id, []):
                    self._add_pair_no_overlap(model, start_vars, lecture, exercise)

    def _add_optional_activity_mandatory_lecture_no_overlap(
        self, model, start_vars, realizations
    ):
        """Keep optional-subject activities clear of their curriculum's mandatory lectures."""
        parent_by_group = dict(
            Group.objects.filter(groupset=self.timetable.groupset).values_list("id", "parent_id")
        )
        group_by_id = {
            group.id: group
            for group in Group.objects.filter(groupset=self.timetable.groupset)
        }
        ancestors_by_group = {}

        def ancestors(group_id):
            if group_id not in ancestors_by_group:
                result = set()
                parent_id = parent_by_group.get(group_id)
                while parent_id is not None:
                    result.add(parent_id)
                    parent_id = parent_by_group.get(parent_id)
                ancestors_by_group[group_id] = result
            return ancestors_by_group[group_id]

        mandatory_lectures = [
            realization
            for realization in realizations
            if realization.activity.type == "P"
        ]
        handled_pairs = set()
        for optional_realization in realizations:
            try:
                subject_code = optional_realization.activity.activity.subject.code
            except ObjectDoesNotExist:
                continue
            optional_group_ids = {
                group.id
                for group in optional_realization.groups.all()
                if any(
                    "({})".format(subject_code) in group_by_id[ancestor_id].short_name
                    for ancestor_id in ancestors(group.id) | {group.id}
                )
            }
            if not optional_group_ids:
                continue
            curriculum_group_ids = set().union(
                *(ancestors(group_id) for group_id in optional_group_ids)
            )
            for mandatory_lecture in mandatory_lectures:
                if mandatory_lecture.id == optional_realization.id:
                    continue
                if not curriculum_group_ids.intersection(
                    group.id for group in mandatory_lecture.groups.all()
                ):
                    continue
                key = tuple(sorted((optional_realization.id, mandatory_lecture.id)))
                if key not in handled_pairs:
                    handled_pairs.add(key)
                    self._add_pair_no_overlap(
                        model, start_vars, optional_realization, mandatory_lecture
                    )

    def _add_tag_descriptive_constraints(
        self,
        model,
        assignment_vars,
        start_vars,
        day_vars,
        realizations,
        realization_group_ids,
        realization_student_ids,
    ):
        prefset = self.timetable.preferenceset
        if prefset is None:
            return

        realizations_by_id = {r.id: r for r in realizations}
        for pref in TagDescriptivePreference.objects.filter(preferenceset=prefset).select_related("tag"):
            tagged = self._tagged_realizations(pref.tag, realizations)
            if len(tagged) < 2 and pref.typename != "ENDSSTUDENTSDAY":
                continue

            if pref.typename == "NOOVERLAP":
                for idx, r1 in enumerate(tagged):
                    for r2 in tagged[idx + 1:]:
                        self._add_pair_no_overlap(model, start_vars, r1, r2)
            elif pref.typename == "GROUPED":
                self._add_same_start(model, start_vars, tagged)
            elif pref.typename == "SAMESTARTINGTIME":
                self._add_same_start(model, start_vars, tagged)
            elif pref.typename == "SAMEDAY":
                self._add_same_day(model, day_vars, tagged)
            elif pref.typename == "CONSECUTIVE":
                ordered = sorted(tagged, key=lambda r: r.id)
                for previous, current in zip(ordered, ordered[1:]):
                    model.Add(day_vars[previous.id] == day_vars[current.id])
                    model.Add(start_vars[previous.id] + previous.duration == start_vars[current.id])
            elif pref.typename == "ENDSSTUDENTSDAY":
                self._add_ends_students_day(
                    model,
                    assignment_vars,
                    pref.tag,
                    tagged,
                    list(realizations_by_id.values()),
                    realization_group_ids,
                    realization_student_ids,
                )

    def _tagged_realizations(self, tag, realizations):
        tagged = []
        for realization in realizations:
            if (
                realization.tags.filter(id=tag.id).exists()
                or realization.activity.tags.filter(id=tag.id).exists()
            ):
                tagged.append(realization)
        return tagged

    def _add_same_start(self, model, start_vars, realizations):
        if len(realizations) < 2:
            return
        first = realizations[0]
        for other in realizations[1:]:
            model.Add(start_vars[first.id] == start_vars[other.id])

    def _add_same_day(self, model, day_vars, realizations):
        if len(realizations) < 2:
            return
        first = realizations[0]
        for other in realizations[1:]:
            model.Add(day_vars[first.id] == day_vars[other.id])

    def _add_ends_students_day(
        self,
        model,
        assignment_vars,
        tag,
        tagged,
        realizations,
        realization_group_ids,
        realization_student_ids,
    ):
        tagged_ids = {r.id for r in tagged}
        for tagged_realization in tagged:
            tagged_group_ids = set(realization_group_ids.get(tagged_realization.id, []))
            tagged_student_ids = set(realization_student_ids.get(tagged_realization.id, []))
            for other in realizations:
                if other.id == tagged_realization.id:
                    continue
                if other.id in tagged_ids:
                    continue
                other_group_ids = set(realization_group_ids.get(other.id, []))
                other_student_ids = set(realization_student_ids.get(other.id, []))
                if tagged_group_ids.isdisjoint(other_group_ids) and tagged_student_ids.isdisjoint(other_student_ids):
                    continue
                for var1, day1, start1, _room1, duration1 in assignment_vars.get(tagged_realization.id, []):
                    end1 = start1 + duration1
                    for var2, day2, start2, _room2, _duration2 in assignment_vars.get(other.id, []):
                        if day1 == day2 and start2 >= end1:
                            model.Add(var1 + var2 <= 1)

    def _add_cross_section_no_overlap_constraints(
        self, model, start_vars, realizations, realization_student_ids
    ):
        if self.options.cross_section_razor is None:
            return
        realization_ids = {r.id for r in realizations}
        enforced_pairs = []
        for r1_id, r2_id in self._cross_section_no_overlap_pairs(
            realizations, realization_student_ids
        ):
            if r1_id not in realization_ids or r2_id not in realization_ids:
                continue
            r1 = next(r for r in realizations if r.id == r1_id)
            r2 = next(r for r in realizations if r.id == r2_id)
            self._add_pair_no_overlap(model, start_vars, r1, r2)
            enforced_pairs.append((r1_id, r2_id))
        self.messages.append(
            "Cross-section razor: student overlaps up to {} are allowed by this "
            "rule; hard no-overlap pairs={}.".format(
                self.options.cross_section_razor, len(enforced_pairs)
            )
        )

    def _add_study_module_constraints(self, model, start_vars, realizations):
        """Keep activities in a module, and linked modules, conflict-free."""
        modules = list(
            StudyModule.objects.filter(timetable=self.timetable, active=True).prefetch_related(
                "activities", "non_overlapping_with"
            )
        )
        if not modules:
            return
        realizations_by_activity = defaultdict(list)
        for realization in realizations:
            realizations_by_activity[realization.activity_id].append(realization)
        module_realizations = {
            module.id: [
                realization
                for activity in module.activities.all()
                for realization in realizations_by_activity[activity.id]
            ]
            for module in modules
        }
        pairs = set()
        for module in modules:
            scoped = module_realizations[module.id]
            for index, first in enumerate(scoped):
                for second in scoped[index + 1:]:
                    pairs.add(tuple(sorted((first.id, second.id))))
            for related in module.non_overlapping_with.all():
                if related.id not in module_realizations:
                    continue
                for first in scoped:
                    for second in module_realizations[related.id]:
                        if first.id != second.id:
                            pairs.add(tuple(sorted((first.id, second.id))))
        realizations_by_id = {realization.id: realization for realization in realizations}
        for first_id, second_id in pairs:
            self._add_pair_no_overlap(
                model, start_vars, realizations_by_id[first_id], realizations_by_id[second_id]
            )

    def _cross_section_no_overlap_pairs(
        self, realizations=None, realization_student_ids=None
    ):
        if hasattr(self, "_cached_cross_section_no_overlap_pairs"):
            return self._cached_cross_section_no_overlap_pairs

        if realizations is not None and realization_student_ids is not None:
            pairs = []
            for index, first in enumerate(realizations):
                first_students = set(realization_student_ids.get(first.id, []))
                if not first_students:
                    continue
                for second in realizations[index + 1:]:
                    second_students = set(realization_student_ids.get(second.id, []))
                    if (
                        len(first_students & second_students)
                        > self.options.cross_section_razor
                    ):
                        pairs.append((first.id, second.id))
            self._cached_cross_section_no_overlap_pairs = pairs
            return self._cached_cross_section_no_overlap_pairs

        constraints = crossections.realizations_must_not_overlap_database(
            self.timetable,
            razor=self.options.cross_section_razor,
            groupset=self.timetable.groupset,
        )
        pairs = []
        for constraint in constraints:
            ids = []
            for item in constraint[2]:
                if item[0] == "Activity_Id":
                    ids.append(int(item[1]))
            if len(ids) == 2:
                pairs.append(tuple(ids))
        self._cached_cross_section_no_overlap_pairs = pairs
        return self._cached_cross_section_no_overlap_pairs

    def _add_tag_value_constraints(
        self, model, assignment_vars, start_vars, realizations, realization_group_ids=None
    ):
        prefset = self.timetable.preferenceset
        if prefset is None:
            return
        for pref in TagValuePreference.objects.filter(preferenceset=prefset).select_related("tag"):
            tagged = self._tagged_realizations(pref.tag, realizations)
            if pref.name == "TAGMAXHOURSDAILY":
                self._add_tag_max_hours_daily(
                    model, assignment_vars, pref.tag, tagged, realization_group_ids, pref.value
                )
                continue
            if len(tagged) < 2:
                continue
            if pref.name == "MAXROOMSREALIZATIONS":
                self._add_max_rooms_constraint(model, assignment_vars, tagged, pref.value)
            elif pref.name == "MINACTIVITYGAP":
                for idx, r1 in enumerate(tagged):
                    for r2 in tagged[idx + 1:]:
                        self._add_pair_min_gap(model, start_vars, r1, r2, pref.value)

    def _add_tag_max_hours_daily(
        self, model, assignment_vars, tag, tagged, realization_group_ids, max_hours
    ):
        if max_hours is None:
            return
        slots_per_day = len(WORKHOURS)
        for group in tag.groups.all():
            relevant = []
            for realization in tagged:
                if realization.id is None:
                    continue
                group_ids = realization_group_ids.get(realization.id, []) if realization_group_ids else []
                if group.id in group_ids:
                    relevant.append(realization)
            if not relevant:
                continue
            for day_idx in range(len(WEEKDAYS)):
                hour_vars = []
                for hour_idx in range(slots_per_day):
                    covering = []
                    for realization in relevant:
                        for var, var_day_idx, var_start_idx, _room_id, duration in assignment_vars.get(realization.id, []):
                            if var_day_idx != day_idx:
                                continue
                            if var_start_idx <= hour_idx < var_start_idx + duration:
                                covering.append(var)
                    if covering:
                        # No teacher/group overlap ensures sum(covering) <= 1.
                        hour_vars.append(sum(covering))
                if hour_vars:
                    model.Add(sum(hour_vars) <= max_hours)

    def _add_solver_constraints(
        self,
        model,
        assignment_vars,
        start_vars,
        day_vars,
        realizations,
        realization_teacher_ids,
        realization_group_ids,
        realization_student_ids,
    ):
        for constraint in SolverConstraint.objects.filter(
            timetable=self.timetable, active=True
        ):
            scoped = self._solver_constraint_realizations(constraint, realizations)
            if len(scoped) < 2 and constraint.constraint_type not in (
                "ENDSSTUDENTSDAY", "FIXEDPLACEMENT", "FIXEDTIME"
            ):
                continue

            if constraint.constraint_type == "NOOVERLAP":
                for idx, r1 in enumerate(scoped):
                    for r2 in scoped[idx + 1:]:
                        self._add_pair_no_overlap(model, start_vars, r1, r2)
            elif constraint.constraint_type in ("GROUPED", "SAMESTARTINGTIME"):
                self._add_same_start(model, start_vars, scoped)
            elif constraint.constraint_type == "SAMEDAY":
                self._add_same_day(model, day_vars, scoped)
            elif constraint.constraint_type == "CONSECUTIVE":
                ordered = sorted(scoped, key=lambda r: r.id)
                for previous, current in zip(ordered, ordered[1:]):
                    model.Add(day_vars[previous.id] == day_vars[current.id])
                    model.Add(start_vars[previous.id] + previous.duration == start_vars[current.id])
            elif constraint.constraint_type == "ENDSSTUDENTSDAY":
                self._add_ends_students_day_for_realizations(
                    model,
                    assignment_vars,
                    scoped,
                    realizations,
                    realization_group_ids,
                    realization_student_ids,
                )
            elif constraint.constraint_type == "MAXROOMSREALIZATIONS":
                self._add_max_rooms_constraint(model, assignment_vars, scoped, constraint.value)
            elif constraint.constraint_type == "SAMEROOM":
                self._add_max_rooms_constraint(model, assignment_vars, scoped, 1)
            elif constraint.constraint_type in ("FIXEDPLACEMENT", "FIXEDTIME"):
                fixed_room_ids = (
                    set(constraint.classrooms.values_list("id", flat=True))
                    if constraint.constraint_type == "FIXEDPLACEMENT"
                    else None
                )
                day_idx = [day[0] for day in WEEKDAYS].index(constraint.day)
                start_idx = [hour[0] for hour in WORKHOURS].index(constraint.start)
                for realization in scoped:
                    matching = [
                        var
                        for var, var_day_idx, var_start_idx, room_id, _duration in assignment_vars.get(
                            realization.id, []
                        )
                        if var_day_idx == day_idx
                        and var_start_idx == start_idx
                        and (fixed_room_ids is None or room_id in fixed_room_ids)
                    ]
                    model.Add(sum(matching) == 1)

    def _solver_constraint_realizations(self, constraint, realizations):
        realization_ids = set(constraint.realizations.values_list("id", flat=True))
        activity_ids = set(constraint.activities.values_list("id", flat=True))
        scoped = []
        for realization in realizations:
            if realization.id in realization_ids or realization.activity_id in activity_ids:
                scoped.append(realization)
        return scoped

    def _fixed_rooms_by_realization(self, realizations, rooms):
        """Return the fixed-room requirements configured for each realization."""
        available_room_ids = {room.id for room in rooms}
        fixed_rooms = defaultdict(list)
        for constraint in SolverConstraint.objects.filter(
            timetable=self.timetable,
            active=True,
            constraint_type__in=("FIXEDROOM", "FIXEDPLACEMENT"),
        ).prefetch_related("activities", "realizations", "classrooms"):
            allowed_rooms = set(constraint.classrooms.values_list("id", flat=True))
            allowed_rooms.intersection_update(available_room_ids)
            for realization in self._solver_constraint_realizations(constraint, realizations):
                fixed_rooms[realization.id].append(allowed_rooms)
        return fixed_rooms

    def _add_ends_students_day_for_realizations(
        self,
        model,
        assignment_vars,
        ending_realizations,
        realizations,
        realization_group_ids,
        realization_student_ids,
    ):
        ending_ids = {r.id for r in ending_realizations}
        for ending_realization in ending_realizations:
            ending_group_ids = set(realization_group_ids.get(ending_realization.id, []))
            ending_student_ids = set(realization_student_ids.get(ending_realization.id, []))
            for other in realizations:
                if other.id == ending_realization.id or other.id in ending_ids:
                    continue
                other_group_ids = set(realization_group_ids.get(other.id, []))
                other_student_ids = set(realization_student_ids.get(other.id, []))
                if ending_group_ids.isdisjoint(other_group_ids) and ending_student_ids.isdisjoint(other_student_ids):
                    continue
                for var1, day1, start1, _room1, duration1 in assignment_vars.get(ending_realization.id, []):
                    end1 = start1 + duration1
                    for var2, day2, start2, _room2, _duration2 in assignment_vars.get(other.id, []):
                        if day1 == day2 and start2 >= end1:
                            model.Add(var1 + var2 <= 1)

    def _add_max_rooms_constraint(self, model, assignment_vars, realizations, max_rooms):
        if max_rooms is None or not realizations:
            return
        room_vars = defaultdict(list)
        for realization in realizations:
            for var, _day_idx, _start_idx, room_id, _duration in assignment_vars.get(realization.id, []):
                room_vars[room_id].append(var)
        used_room_vars = []
        for room_id, vars_for_room in room_vars.items():
            used = model.NewBoolVar(f"room_used_{room_id}_{len(used_room_vars)}")
            model.AddMaxEquality(used, vars_for_room)
            used_room_vars.append(used)
        if used_room_vars:
            model.Add(sum(used_room_vars) <= max_rooms)

    def _add_pair_no_overlap(self, model, start_vars, r1, r2):
        if r1.id == r2.id:
            return
        order = model.NewBoolVar(f"order_{r1.id}_{r2.id}")
        model.Add(start_vars[r1.id] + r1.duration <= start_vars[r2.id]).OnlyEnforceIf(order)
        model.Add(start_vars[r2.id] + r2.duration <= start_vars[r1.id]).OnlyEnforceIf(order.Not())

    def _add_pair_min_gap(self, model, start_vars, r1, r2, min_gap):
        if r1.id == r2.id or min_gap is None:
            return
        order = model.NewBoolVar(f"gap_order_{r1.id}_{r2.id}")
        model.Add(start_vars[r1.id] + r1.duration + min_gap <= start_vars[r2.id]).OnlyEnforceIf(order)
        model.Add(start_vars[r2.id] + r2.duration + min_gap <= start_vars[r1.id]).OnlyEnforceIf(order.Not())

    def _add_preference_objective_terms(
        self,
        objective_terms,
        var,
        realization_id,
        teacher_ids,
        group_ids,
        tag_ids,
        day_code,
        hours,
        room_id,
        teacher_time_prefs,
        group_time_prefs,
        tag_time_prefs,
        allocation_locks,
    ):
        hours_set = set(hours)
        for teacher_id in teacher_ids:
            for pref_day, pref_hours, pref_weight in teacher_time_prefs.get(teacher_id, []):
                self._add_time_preference_term(
                    objective_terms, var, day_code, hours_set, pref_day, pref_hours, pref_weight
                )
        for group_id in group_ids:
            for pref_day, pref_hours, pref_weight in group_time_prefs.get(group_id, []):
                self._add_time_preference_term(
                    objective_terms, var, day_code, hours_set, pref_day, pref_hours, pref_weight
                )
        for tag_id in tag_ids:
            for pref_day, pref_hours, pref_weight in tag_time_prefs.get(tag_id, []):
                self._add_time_preference_term(
                    objective_terms, var, day_code, hours_set, pref_day, pref_hours, pref_weight
                )

        existing = allocation_locks.get(realization_id)
        if existing is not None:
            if existing.day == day_code and set(hour_strings_to_indices(existing.hours)) == hours_set:
                objective_terms.append(int(self.options.allocation_time_weight) * var)
            if existing.classroom_id == room_id:
                objective_terms.append(int(self.options.allocation_room_weight) * var)

    def _add_time_preference_term(
        self, objective_terms, var, day_code, hours_set, pref_day, pref_hours, pref_weight
    ):
        if pref_day != day_code:
            return
        if hours_set.isdisjoint(pref_hours):
            return
        objective_terms.append(int(math.ceil(pref_weight * 100)) * var)

    def _add_scheduling_window_objective_terms(
        self,
        objective_terms,
        var,
        start_idx,
        duration,
        window_start_idx,
        window_end_idx,
        window_weight,
    ):
        """Prefer each scheduled hour that falls inside its configured window."""
        if window_weight == 0:
            return
        weight = (
            self._automatic_weight("scheduling_window_weight", SCHEDULING_WINDOW_WEIGHT)
            * window_weight
            // 100
        )
        for hour_idx in range(start_idx, start_idx + duration):
            if window_start_idx <= hour_idx < window_end_idx:
                objective_terms.append(weight * var)

    def _add_activity_type_restriction_objective_terms(
        self, objective_terms, var, start_idx, duration, restriction_weights
    ):
        """Penalize FET-style soft unavailable slots without blocking them."""
        for hour_idx in range(start_idx, start_idx + duration):
            weight = restriction_weights.get(hour_idx, 0)
            if 0 < weight < 100:
                objective_terms.append(
                    -(
                        self._automatic_weight(
                            "scheduling_window_weight", SCHEDULING_WINDOW_WEIGHT
                        )
                        * weight
                        // 100
                    )
                    * var
                )



def preference_hours(pref):
    start_index = [h[0] for h in WORKHOURS].index(pref.start)
    return list(range(start_index, start_index + pref.duration))


def hour_strings_to_indices(hours):
    work_hours = [h[0] for h in WORKHOURS]
    return [work_hours.index(h) for h in hours if h in work_hours]
