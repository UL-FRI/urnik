# OR-Tools Constraint Inventory

This document inventories the scheduling constraints that need to be accounted
for when replacing the FET workflow with Google OR-Tools CP-SAT.

The current FET behavior is primarily defined in
`friprosveta/management/commands/django2fet.py`. The OR-Tools implementation is
in `friprosveta/services/ortools_solver.py`, with command-line orchestration in
`friprosveta/management/commands/ortools_generate.py`.

## Goals

- Preserve the scheduling semantics that users currently rely on through FET.
- Make each constraint explicit as hard, soft, or configurable.
- Identify which constraints are already modeled by OR-Tools and which are not.
- Provide a checklist for designing a maintainable CP-SAT model.
- Improve on FET where the current model can offer better or clearer constraint
  options, especially for teacher-entered preferences.

## Domain Objects

- `Timetable`: scheduling context. Defines the activity set, preference set,
  group set, classroom set, and timetables it respects.
- `Activity`: course/activity definition. Defines duration, teachers, groups,
  locations, room/resource requirements, tags, ordering, and no-overlap links.
- `ActivityRealization`: concrete schedulable unit. Has teachers, groups,
  duration via its activity, size, and preferred rooms.
- `Allocation`: scheduled result. Assigns one realization to a timetable, room,
  day, and start hour.
- `Teacher`, `Group`, `Student`, `Classroom`, `Location`, `Resource`: resources
  consumed by allocations.
- `PreferenceSet`: container for teacher, group, and tag preferences.
- `SolverConstraint`: first-class OR-Tools constraint model for relation,
  workload, movement, and room-stability rules that should not be encoded
  through FET-style tags.

## Solver Decision Variables

The current OR-Tools prototype uses one boolean variable for each feasible
assignment:

```text
realization -> day, start slot, room
```

This is a reasonable base model because most constraints can be expressed as
filters over assignment variables or sums over resource/time buckets.

Useful derived variables may be needed for later constraints:

- start index per realization
- day index per realization
- room/building per realization
- occupied hour indicators per teacher/group/student/room/day/hour
- active day indicators per teacher/group/student/tag
- first and last occupied slot per teacher/group/student/day
- building-change indicators between consecutive allocations

## First-Class Solver Constraints

`SolverConstraint` is available for constraints that should be configured
directly for OR-Tools instead of indirectly through tags.

Currently supported constraint types:

- `NOOVERLAP`
- `GROUPED`
- `CONSECUTIVE`
- `SAMEDAY`
- `SAMESTARTINGTIME`
- `ENDSSTUDENTSDAY`
- `MAXROOMSREALIZATIONS`
- `MAXDAYSWEEK`
- `MINDAYSWEEK`
- `MAXHOURSDAY`
- `MAXHOURSCONT`
- `MINCHANGEGAP`
- `MAXCHANGESDAY`
- `MAXCHANGESWEEK`

## Hard Core Constraints

These are required for a valid timetable.

### One Placement Per Realization

Every schedulable `ActivityRealization` must receive exactly one assignment.

FET source:

- `ConstraintBasicCompulsoryTime`
- `ConstraintBasicCompulsorySpace`

Current OR-Tools status: implemented.

Notes:

- We need a clear policy for skipped/disabled/invalid realizations.
- `--ready-only` currently schedules only activities marked `ready_to_schedule`.

### Working Time Bounds

Allocations must fit inside `WEEKDAYS` and `WORKHOURS` and may not run past the
last slot.

Current OR-Tools status: implemented by candidate generation.

### Room Feasibility

Each realization must be assigned to a room that satisfies:

- timetable classroom set
- activity locations
- activity required rooms, if explicit
- activity resource requirements
- per-student resource requirements
- capacity, using realization size

FET source:

- `activity_requirements_to_preferred_rooms`
- `ConstraintActivityPreferredRooms`
- `ConstraintActivityPreferredRoom`

Current OR-Tools status: mostly implemented via
`realization.preferred_rooms(timetable).filter(capacity__gte=realization.size)`.

Open questions:

- FET uses `_shrunken_students()` for some tag-driven size adjustments. OR-Tools
  does not yet account for this.
- Resource incompatibilities should be checked explicitly if they are not fully
  captured by `preferred_rooms()`.

### Room No-Overlap

A room cannot host more than one allocation in the same occupied slot.

FET source:

- `ConstraintBasicCompulsorySpace`

Current OR-Tools status: implemented.

### Teacher No-Overlap

A teacher cannot teach more than one realization in the same occupied slot.

FET source:

- `ConstraintBasicCompulsoryTime`

Current OR-Tools status: implemented.

### Group No-Overlap

A group cannot attend more than one realization in the same occupied slot.

FET source:

- `ConstraintBasicCompulsoryTime`

Current OR-Tools status: implemented.

### Student No-Overlap

A student should not be assigned overlapping realizations.

FET source:

- `crossections.realizations_must_not_overlap_database(...)`

Current OR-Tools status: partially implemented from concrete
`group.students` membership.

Gap:

- FET also derives overlap pairs from enrollment/cross-section data and a `razor`
  threshold. The CP-SAT model needs the same pair-generation logic or an explicit
  replacement policy.

### Teacher And Group Unavailability

Teacher and group `CANT` time preferences make affected slots unavailable.

FET source:

- `teacher_not_available_preferences`
- `students_not_available_preferences`
- `generic_not_available_preferences`

Current OR-Tools status: implemented for direct teacher/group `CANT`
and `HATE` preferences.

Gap:

- FET also applies tag-based `TagTimePreference` with `HATE` or `CANT` to tagged
  teachers/groups. OR-Tools now models these as hard unavailable times.

### Respected Timetables

Allocations from timetables listed in `timetable.respects` block conflicting use
of teachers, groups, and rooms.

FET source:

- `respected_to_teachers_not_available`
- `respected_to_students_not_available`
- `respected_to_rooms_not_available`

Current OR-Tools status: implemented for teachers, groups, and rooms.

## Activity Relation Constraints

### Activity Must Not Overlap

Activities linked through `Activity.mustNotOverlap` cannot overlap.

FET source:

- `activities_not_overlapping`
- `ConstraintActivitiesNotOverlapping`

Current OR-Tools status: implemented.

### Activity Ordering

Activities linked through `Activity.before` must be ordered.

FET source:

- `activities_ordered`
- `ConstraintTwoActivitiesOrdered`

Current OR-Tools status: implemented.

Open question:

- The current OR-Tools implementation orders by flattened week start index. That
  allows the second activity to occur later in the week, not necessarily later on
  the same day. This appears consistent with FET's ordered constraint but should
  be verified with users.

### Tag NOOVERLAP

Realizations matching a tag with `TagDescriptivePreference.typename = NOOVERLAP`
must not overlap.

FET source:

- `activities_not_overlapping`

Current OR-Tools status: implemented for tags attached to activities or
realizations.
Also implemented through first-class `SolverConstraint`.

### Tag GROUPED

Realizations matching a tag with `typename = GROUPED` should be grouped into the
same time slot, up to FET's two/three-activity limit.

FET source:

- `activities_grouped`
- `ConstraintTwoActivitiesGrouped`
- `ConstraintThreeActivitiesGrouped`

Current OR-Tools status: implemented for tags attached to activities or
realizations. Unlike FET, CP-SAT can group more than three realizations.
Also implemented through first-class `SolverConstraint`.

Design note:

- CP-SAT can support more than three activities, so we should decide whether to
  preserve FET's limit or implement the intended general behavior.

### Tag CONSECUTIVE

Realizations matching a tag with `typename = CONSECUTIVE` should be scheduled
back-to-back.

FET source:

- `activities_consecutive`
- `ConstraintTwoActivitiesConsecutive`

Current OR-Tools status: implemented for tags attached to activities or
realizations, ordered by realization id.
Also implemented through first-class `SolverConstraint`.

Design note:

- Need to define ordering. FET uses sorted IDs when collecting activities but the
  set conversion may lose deterministic order in places.

### Tag SAMEDAY

Realizations matching a tag with `typename = SAMEDAY` should start on the same
day.

FET source:

- `activities_same_day`
- `ConstraintActivitiesSameStartingDay`

Current OR-Tools status: implemented for tags attached to activities or
realizations.
Also implemented through first-class `SolverConstraint`.

### Tag SAMESTARTINGTIME

Realizations matching a tag with `typename = SAMESTARTINGTIME` should start at
the same day and hour.

FET source:

- `activities_same_time`
- `ConstraintActivitiesSameStartingTime`

Current OR-Tools status: implemented for tags attached to activities or
realizations.
Also implemented through first-class `SolverConstraint`.

### Tag ENDSSTUDENTSDAY

Realizations matching a tag with `typename = ENDSSTUDENTSDAY` should end the
students' day.

FET source:

- `activity_ends_students_day`
- `ConstraintActivityEndsStudentsDay`

Current OR-Tools status: implemented for tagged realizations that share a group
or concrete students with later realizations.
Also implemented through first-class `SolverConstraint`.

Design note:

- This requires knowing, for each affected group/student on that day, whether any
  later allocation exists.

### Minimum Gaps Between Tagged Activities

Realizations matching a tag with `TagValuePreference.name = MINACTIVITYGAP`
should have at least the configured number of gaps between them.

FET source:

- `min_gaps_between_activities`
- `ConstraintMinGapsBetweenActivities`

Current OR-Tools status: implemented for tag value preference `MINACTIVITYGAP`.

## Time Preferences And Workload Constraints

### Teacher WANT/HATE Time Preferences

Teacher `WANT` preferences reward matching slots. Teacher `HATE` preferences
should penalize or forbid matching slots depending on policy.

FET source:

- `teacher_time_preferences_to_preferred_times`
- `teacher_not_available_preferences`

Current OR-Tools status: direct `WANT` preferences are modeled as objective
rewards. Direct `HATE` preferences are hard unavailable times.

Gap:

- Tag-derived teacher `WANT` preferences are implemented when the tag is attached
  to the activity or realization being scheduled.

### Group WANT/HATE Time Preferences

Group `WANT` preferences reward matching slots. Group `HATE` preferences should
penalize or forbid matching slots depending on policy.

FET source:

- `students_not_available_preferences`

Current OR-Tools status: direct `WANT` preferences are modeled as objective
rewards. Direct `HATE` preferences are hard unavailable times.

Gap:

- FET does not appear to export direct group `WANT` as preferred time slots in
  the same way teacher `WANT` is exported. OR-Tools currently does reward group
  `WANT`, which may be an intentional improvement or a behavior change.
- Tag-derived group `WANT` preferences are implemented when the tag is attached
  to the activity or realization being scheduled.

### Tag WANT Time Preferences

Activities/realizations with a tag may prefer specific slots.

FET source:

- `tag_time_preferences_to_preferred_times`

Current OR-Tools status: implemented for tags attached to activities or
realizations.

### Existing Allocations As Soft Locks

Existing allocations can be converted into preferred starting times and preferred
rooms with configurable weights.

FET source:

- `allocations_to_preferred_times`
- `allocations_to_preferred_room`

Current OR-Tools status: implemented for existing allocations on the timetable
being replaced.

Important implementation issue:

- The OR-Tools command now refuses to replace existing allocations unless
  `--clear-existing` is passed, and only deletes/replaces after a feasible
  complete solution is found.
- Existing allocations are used as weighted soft locks for time and room when
  replacing with `--clear-existing`.

Command modes:

- `scratch`: ignores existing allocation soft locks.
- `improve`: prefers keeping existing allocation times/rooms.
- `repair`: hard-locks existing allocations except explicitly listed repaired
  realizations.

### Teacher Value Time Preferences

Teacher value preferences can constrain workload shape.

FET source:

- `teacher_value_time_preferences`

Preference names currently exported:

- `MAXDAYSWEEK`
- `MINDAYSWEEK`
- `MAXHOURSDAY`
- `MAXSPANDAY`
- `MAXHOURSCONT`
- `MAXGAPSDAY`
- `MAXGAPSWEEK`

Current OR-Tools status: implemented for `MAXDAYSWEEK`, `MINDAYSWEEK`,
`MAXHOURSDAY`, and `MAXHOURSCONT` through teacher value preferences and
first-class `SolverConstraint`.

### Group Value Time Preferences

Group value preferences can constrain student workload shape.

FET source:

- `students_value_time_preferences`

Preference names currently exported:

- `MAXDAYSWEEK`
- `MINDAYSWEEK`
- `MAXHOURSDAY`
- `MAXHOURSCONT`
- `MAXGAPSDAY`
- `MAXGAPSWEEK`

Current OR-Tools status: implemented for `MAXDAYSWEEK`, `MINDAYSWEEK`,
`MAXHOURSDAY`, and `MAXHOURSCONT` through group value preferences and
first-class `SolverConstraint`.

### Tag Max Hours Daily

Groups attached to a tag can have a maximum number of hours per day for
activities with that tag.

FET source:

- `activities_tag_max_hour_daily`
- `TAGMAXHOURSDAILY`

Current OR-Tools status: implemented for `MINCHANGEGAP` through teacher value
preferences and first-class `SolverConstraint`.

## Space And Building Constraints

### Teacher Building Changes

Teacher value preferences can constrain building changes.

FET source:

- `teacher_value_space_preferences`

Preference names currently exported:

- `MAXCHANGESWEEK`
- `MAXCHANGESDAY`
- `MINCHANGEGAP`

Current OR-Tools status: implemented for `MINCHANGEGAP` through group value
preferences and first-class `SolverConstraint`.

### Group Building Changes

Group value preferences can constrain building changes.

FET source:

- `students_value_space_preferences`

Preference names currently exported:

- `MAXCHANGESWEEK`
- `MAXCHANGESDAY`
- `MINCHANGEGAP`

Current OR-Tools status: implemented for tag value preference
`MAXROOMSREALIZATIONS` and first-class `SolverConstraint`.

### Max Rooms Across Tagged Realizations

Realizations matching a tag with `TagValuePreference.name = MAXROOMSREALIZATIONS`
should use at most the configured number of different rooms.

FET source:

- `activitiesMaxNumberOfRooms`
- `ConstraintActivitiesOccupyMaxDifferentRooms`

Current OR-Tools status: implemented for tag value preference
`MAXROOMSREALIZATIONS` and first-class `SolverConstraint`.

### Tag Max Hours Daily

Groups attached to a tag with `TagValuePreference.name = TAGMAXHOURSDAILY`
can have a maximum number of hours per day for activities with that tag.

FET source:

- `activities_tag_max_hour_daily`
- `ConstraintStudentsSetActivityTagMaxHoursDaily`

Current OR-Tools status: implemented for tag value preference
`TAGMAXHOURSDAILY` over groups attached to the tag.

### Teacher Building Changes Per Day/Week

Teacher value preferences can constrain building changes per day or per week.

FET source:

- `teacher_value_space_preferences`
- `ConstraintTeacherMaxBuildingChangesPerDay`
- `ConstraintTeacherMaxBuildingChangesPerWeek`

Current OR-Tools status: implemented for `MAXCHANGESDAY` and
`MAXCHANGESWEEK` through teacher and group value preferences and first-class
`SolverConstraint`. The model uses adjacent-slot transitions: a transition
counts when an entity is occupied in one building at hour `h` and a different
building at hour `h + 1` on the same day. This is a lower-bound
approximation of FET's "between consecutive activities" semantics for
back-to-back schedules and intentionally does not count transitions across
hour gaps.

### Group Building Changes Per Day/Week

Group value preferences can constrain building changes per day or per week.

FET source:

- `students_value_space_preferences`
- `ConstraintStudentsSetMaxBuildingChangesPerDay`
- `ConstraintStudentsSetMaxBuildingChangesPerWeek`

Current OR-Tools status: implemented through the same adjacent-slot
transition model as for teachers.

## Size Adjustment Constraints

Some tag value preferences affect computed group size or room capacity needs.

Preference names defined in `TAGVALUEPREFERENCES`:

- `MULSIZE`: multiply group size for activities with the tag by `value/100`
- `SHRINKGROUPS`: reduce group size for activities with the tag by `value`

FET source:

- `_shrunken_students`
- `activity_requirements_to_preferred_rooms`

Current OR-Tools status: implemented for `SHRINKGROUPS` and `MULSIZE`.
Both adjustments are applied when computing the candidate room set per
realization, mirroring the FET `_shrunken_students` helper that was used to
filter `preferred_rooms` by capacity.

Design note:

- This is not a standalone scheduling constraint. It changes candidate room
  feasibility and capacity/resource calculations.

## Hard Vs Soft Policy

The database has `Preference.level` values:

- `CANT`: should normally become hard infeasibility.
- `HATE`: hard infeasibility. A solution that violates a `HATE` preference is not
  acceptable.
- `WANT`: should normally become a soft reward.

Before implementing missing constraints, we should classify each existing FET
constraint into one of these categories:

- hard compatibility behavior
- soft compatibility behavior
- intentional improvement over FET behavior
- deprecated or ignored behavior

OR-Tools does not need to match every FET limitation exactly. The replacement is
allowed to improve semantics where that gives users nicer, clearer, or more
expressive constraint options.

Partial schedules are not acceptable. A solve is successful only when all
required realizations are placed and all hard constraints are satisfied.

## Existing OR-Tools Coverage Summary

Implemented:

- one assignment per realization
- working time bounds
- room candidate filtering by preferred rooms and capacity
- direct teacher/group `CANT` and `HATE` unavailability
- tag-derived teacher/group `CANT` and `HATE` unavailability
- guarded replacement of existing allocations after a feasible solution
- respected timetable teacher/group/room blocking
- teacher/group/student/room no-overlap
- activity `mustNotOverlap`
- activity `before`
- direct teacher/group `WANT` objective terms
- tag-derived activity/realization `WANT` objective terms
- tag `NOOVERLAP`, `GROUPED`, `CONSECUTIVE`, `SAMEDAY`, `SAMESTARTINGTIME`, and
  `ENDSSTUDENTSDAY` constraints
- existing allocation soft locks for iterative generation
- iterative modes: `scratch`, `improve`, and `repair`
- first-class `SolverConstraint` model and migration
- teacher/group max days, min days, max hours daily, and max continuous hours
- teacher/group minimum building-change gap
- teacher/group maximum building changes per day and per week
- tag and first-class max-room constraints across realization sets
- tag minimum activity gap
- tag max hours daily
- size adjustment preferences (`SHRINKGROUPS`, `MULSIZE`)
- optional cross-section/enrollment no-overlap constraints parsed from the
  legacy FET helper
- `--ready-only` correctly resolves `friprosveta.Activity.ready_to_schedule`
  through the multi-table inheritance link
- improved capacity diagnostics when no suitable rooms are available
- declared `ortools` dependency

Missing or incomplete:

- full fidelity for building-change transitions across hour gaps (the
  current model only counts adjacent-slot transitions)
- direct tests against realistic cross-section/enrollment fixtures with
  cross-section completion remaining high
- richer infeasibility diagnostics describing which hard constraint caused
  failure

## Recommended Implementation Order

1. Stabilize the current command behavior.
2. Add `ortools` as a declared dependency.
3. Split model building, solving, and allocation writing into testable functions.
4. Add small fixture-based tests for the constraints already implemented.
5. Fix existing allocation deletion and add soft-lock support.
6. Add cross-section/enrollment overlap generation.
7. Add tag time and tag descriptive constraints.
8. Add teacher/group workload constraints.
9. Add building-change constraints.
10. Add diagnostics for no feasible assignments and infeasible models.

## Interface Policy

The solver should remain command-line driven for now. The long-term direction is
to make the whole scheduling process available online, but the first OR-Tools
replacement should stabilize the command-line workflow and model behavior before
adding web orchestration.

## Open Design Questions

- Should tag constraints support more activities than FET did?
- How should soft weights be normalized across very different constraint types?
- Should the solver optimize for user preferences only, schedule stability only,
  or a weighted combination?
- What diagnostics should be shown when no complete feasible solution exists?
- Which parts of the process should be moved online first after the command-line
  workflow is stable?
