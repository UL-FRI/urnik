from collections import defaultdict

from django.core.management.base import BaseCommand

from frinajave.models import TeacherSubjectCycles
from friprosveta.models import Teacher, Timetable
from timetable.models import TimetableSet


class Command(BaseCommand):
    help = "Report teacher codes in imported najave that have no Teacher record."

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug")
        parser.add_argument("timetable_set_slug")

    def handle(self, *args, **options):
        timetable = Timetable.objects.get(slug=options["timetable_slug"])
        timetable_set = TimetableSet.objects.get(slug=options["timetable_set_slug"])
        subject_codes = timetable.subjects.values_list("code", flat=True)
        cycles = TeacherSubjectCycles.objects.filter(
            timetable_set=timetable_set,
            subject_code__in=subject_codes,
            cycles__gt=0,
        ).values_list("teacher_code", "subject_code")
        cycle_data = list(cycles)
        known_codes = set(
            Teacher.objects.filter(code__in={teacher_code for teacher_code, _ in cycle_data})
            .values_list("code", flat=True)
        )
        missing_by_teacher = defaultdict(set)
        for teacher_code, subject_code in cycle_data:
            if teacher_code not in known_codes:
                missing_by_teacher[teacher_code].add(subject_code)

        if not missing_by_teacher:
            self.stdout.write("All teachers referenced by najave exist.")
            return

        for teacher_code in sorted(missing_by_teacher):
            self.stdout.write(
                "{}: {}".format(
                    teacher_code, ", ".join(sorted(missing_by_teacher[teacher_code]))
                )
            )
