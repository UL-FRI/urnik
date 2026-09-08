from django.core.management.base import BaseCommand, CommandError

import friprosveta.models
from friprosveta.services.ortools_solver import (
    ORToolsSolverOptions,
    ORToolsTimetableSolver,
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
            help="Solver time limit in seconds; 0 runs until CP-SAT proves optimal or infeasible (default: 60).",
        )
        parser.add_argument(
            "--num-search-workers",
            type=int,
            default=8,
            help="Parallel CP-SAT search workers (default: 8).",
        )
        parser.add_argument(
            "--max-memory-mb",
            type=int,
            default=4096,
            help="Maximum CP-SAT memory in MiB (default: 4096).",
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
            help="Replace existing allocations after a feasible solution is found.",
        )
        parser.add_argument(
            "--ready-only",
            action="store_true",
            default=False,
            help="Schedule only activities marked ready_to_schedule.",
        )
        parser.add_argument(
            "--allocation-time-weight",
            type=int,
            default=100,
            help="Soft reward for keeping an existing allocation time (default: 100).",
        )
        parser.add_argument(
            "--allocation-room-weight",
            type=int,
            default=25,
            help="Soft reward for keeping an existing allocation room (default: 25).",
        )
        parser.add_argument(
            "--cross-section-razor",
            type=int,
            default=None,
            help=(
                "Allow student cross-section overlaps up to this threshold and add "
                "hard no-overlap pairs above it. When omitted, every shared student "
                "prevents overlap."
            ),
        )
        parser.add_argument(
            "--cross-section-group-razor",
            type=int,
            default=None,
            help=(
                "Ignore realization group assignments whose group size is below "
                "this threshold. Database assignments remain unchanged."
            ),
        )
        parser.add_argument(
            "--mode",
            choices=("scratch", "improve", "repair"),
            default="improve",
            help=(
                "Scheduling mode: scratch ignores existing allocation soft locks, "
                "improve prefers keeping existing allocations, repair hard-locks "
                "existing allocations except listed repaired realizations."
            ),
        )
        parser.add_argument(
            "--repair-realization",
            type=int,
            action="append",
            default=[],
            help="Realization id to allow moving in repair mode. Can be repeated.",
        )

    def handle(self, *args, **options):
        timetable = friprosveta.models.Timetable.objects.get(
            slug=options["timetable_slug"]
        )
        solver_options = ORToolsSolverOptions(
            time_limit=options["time_limit"],
            num_search_workers=max(1, options["num_search_workers"]),
            max_memory_in_mb=max(1, options["max_memory_mb"]),
            clear_existing=options["clear_existing"],
            ready_only=options["ready_only"],
            debug=options["debug"],
            progress_every=max(1, options["progress_every"]),
            build_timeout=max(0, options["build_timeout"]),
            allocation_time_weight=options["allocation_time_weight"],
            allocation_room_weight=options["allocation_room_weight"],
            cross_section_razor=options["cross_section_razor"],
            cross_section_group_razor=options["cross_section_group_razor"],
            scheduling_mode=options["mode"],
            repair_realization_ids=tuple(options["repair_realization"]),
        )
        result = ORToolsTimetableSolver(timetable, solver_options).solve_and_save()
        if not result.success:
            raise CommandError("\n".join(result.messages) or "Solver generation failed.")
        for message in result.messages:
            self.stdout.write(message)
