# Solver Setup UI — Design

Server-rendered Django UI for staff to configure OR-Tools CP-SAT solver
constraints per timetable. No React, no external frontend dependencies.
Reuses the existing `base.html` / `navigation.html` shell and the visual
language already shipped across `friprosveta` preference pages.

## 1. Scope and honesty

The UI exposes the solver's existing generated rule sources first, plus only
the optional `SolverConstraint` types the solver actually consumes
(see `friprosveta/services/ortools_solver.py`):

- Relation types (`_add_solver_constraints`): `NOOVERLAP`, `GROUPED`,
  `CONSECUTIVE`, `SAMEDAY`, `SAMESTARTINGTIME`, `MAXROOMSREALIZATIONS`,
  `ENDSSTUDENTSDAY`.
- Workload / movement types (`_build_value_constraints`,
  `_add_movement_constraints`): `MAXDAYSWEEK`, `MINDAYSWEEK`, `MAXHOURSDAY`,
  `MAXHOURSCONT`, `MINCHANGEGAP`.

The solver ignores `hard`, `weight`, and `classrooms` on `SolverConstraint`
(all constraints are hard). These fields are **not** exposed in the UI; the
dashboard help text states this truthfully so operators do not expect soft
weights or room scoping that the solver does not provide.

The generation and repair pages are **command previews only**. Whole-timetable
generation contains no realization picker; repair is a separate advanced flow.
CP-SAT is never executed inside an HTTP request and allocations are never
deleted through this UI. The preview
maps the existing `ortools_generate` management command options
(`time_limit`, `debug`, `progress_every`, `build_timeout`, `clear_existing`,
`ready_only`, `allocation_time_weight`, `allocation_room_weight`,
`cross_section_razor`, `mode`, `repair_realization`) into a copy-pasteable
shell command. Repair realization ids are selected from a timetable-scoped
multiple-select so the preview only emits realization IDs belonging to the
timetable.

## 2. Information architecture

All routes are staff-only (`@login_required` + `is_staff`), scoped to a
`timetable_slug`. Objects accessed by `pk` are verified to belong to that
timetable to prevent cross-timetable selection.

| Route | Purpose |
|---|---|
| `solver/<slug>/` | Dashboard: category cards, constraint count, links |
| `solver/<slug>/constraints/` | List all `SolverConstraint` for the timetable |
| `solver/<slug>/constraints/new/` | Create (category picker → typed form) |
| `solver/<slug>/constraints/<pk>/edit/` | Edit (typed form by category) |
| `solver/<slug>/constraints/<pk>/delete/` | Delete (confirmation) |
| `solver/<slug>/run/` | Whole-timetable generation command preview (no execution) |
| `solver/<slug>/repair/` | Advanced repair command preview with realization selection |
| `solver/<slug>/groups/` | Student/group rules explanation + links |

## 3. Constraint categories and typed validation

| Category | Types | Required fields | Disabled/cleared fields |
|---|---|---|---|
| Relation (≥2 effective realizations) | `NOOVERLAP`, `GROUPED`, `CONSECUTIVE`, `SAMEDAY`, `SAMESTARTINGTIME` | `name`, `constraint_type`, activities/realizations expanding to ≥2 distinct realizations | `teachers`, `groups`, `value` |
| Relation with value | `MAXROOMSREALIZATIONS` | same as above + positive `value` | `teachers`, `groups` |
| Ends students' day (≥1 effective realization) | `ENDSSTUDENTSDAY` | `name`, `constraint_type`, ≥1 activity/realization | `teachers`, `groups`, `value` |
| Workload / movement | `MAXDAYSWEEK`, `MINDAYSWEEK`, `MAXHOURSDAY`, `MAXHOURSCONT`, `MINCHANGEGAP` | `name`, `constraint_type`, positive `value`, ≥1 teacher/group | `activities`, `realizations` |

### Effective realizations

Relation and ends-day validation mirrors the solver's
`_solver_constraint_realizations`: the effective set is the union of
directly-selected realizations and all realizations of selected activities,
restricted to the timetable's activityset. Selecting one activity with a single
realization, or an activity plus its own realization, produces one distinct
effective realization and is rejected for relation constraints (requires ≥2).

### Per-category field disabling

Fields the solver ignores for a given category are disabled in the form and
cleared on save so ignored selections never persist:
- relation / ends_day: `teachers` and `groups` are disabled and cleared.
- workload: `activities` and `realizations` are disabled and cleared.
- relation (non-MAXROOMS): `value` is shown so MAXROOMS can be configured in
  the same typed form, but it is set to None on save unless the selected type
  is `MAXROOMSREALIZATIONS`.

### Teacher choices

Teacher choices are scoped to teachers assigned to realizations in the
timetable (`ActivityRealization.teachers`), matching the solver's
`realization_teachers` source — not the broader activity-teacher relation.

`active` is editable on the list/edit views. `hard`, `weight`, `classrooms`
are never exposed.

## 4. Scoping

All selectable `Activity`, `ActivityRealization`, `Teacher`, `Group` querysets
are filtered to the timetable's `activityset` / `groupset` so an operator
cannot attach a constraint to objects belonging to a different timetable.

## 5. Visual language (tokens reused from existing CSS)

No new CSS file. Reuse `friprosveta/static/css/main.css` and `cgp.css`:

- `h1` (Georgia, `#2B4F89`) for page titles — matches `group_list.html`,
  `preference_types_list.html`.
- `h2` / `h3` (`#2B4F89`) for section headings.
- Links: `#AC0E02` / `#B30D01` (existing `a` color in `main.css`).
- Tables: `#content .podatkiTwo table` styling (bordered, `#EFEFEF` header).
- Forms: default Django form rendering inside `#content p` line height.
- Category cards: simple `<div>` blocks with `h3` titles and `<p>` body,
  matching the plain, non-framework look of existing pages.

No emojis. No icon fonts. No JavaScript frameworks. Plain server-rendered
HTML forms with Django's `{{ form.as_p }}` / `{{ form.as_table }}`.

## 6. Accessibility and responsiveness

- Labels are real `<label>` elements (Django default `as_p`).
- Tables have `<thead>` / `<tbody>` for screen readers.
- No fixed pixel widths; the existing `#container` / `.wrap` layout is fluid
  and works on mobile. Forms stack vertically.
- Color is never the only signal: status uses text (`active`/`inactive`).

## 7. Accepted debt

- The run page does not execute the solver; it only previews the command.
  This is intentional (CP-SAT in an HTTP request is unsafe).
- `hard` / `weight` / `classrooms` are hidden rather than removed from the
  model, because the model is shared with the solver and migrations are out
  of scope. Help text explains the current hard-only behavior.
- No live diagnostics of solver feasibility are exposed; the dashboard links
  to the existing allocations views for read-only inspection instead.
