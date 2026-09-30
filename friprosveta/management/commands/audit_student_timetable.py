from django.core.management.base import BaseCommand, CommandError

from friprosveta.models import Student, StudentEnrollment, Timetable
from timetable.models import ActivityRealization, Allocation


class Command(BaseCommand):
    help = "Report why an enrolled student's activities are absent from a timetable."

    def add_arguments(self, parser):
        parser.add_argument("timetable_slug")
        parser.add_argument("student_id")

    def handle(self, *args, **options):
        try:
            timetable = Timetable.objects.get(slug=options["timetable_slug"])
            student = Student.objects.get(studentId=options["student_id"])
        except (Timetable.DoesNotExist, Student.DoesNotExist) as error:
            raise CommandError(str(error)) from error

        enrollments = (
            StudentEnrollment.objects.filter(
                groupset=timetable.groupset, student=student
            )
            .select_related("subject", "study")
            .order_by("subject__code")
        )
        followed_ids = set(student.follows.values_list("id", flat=True))
        student_group_ids = set(
            student.groups.filter(groupset=timetable.groupset).values_list("id", flat=True)
        )
        attended_ids = followed_ids or set(
            ActivityRealization.objects.filter(groups__students=student).values_list(
                "id", flat=True
            )
        )
        timetable_ids = [timetable.id, *timetable.respects.values_list("id", flat=True)]
        public_timetable_ids = set(
            Timetable.objects.filter(id__in=timetable_ids, public=True).values_list(
                "id", flat=True
            )
        )
        self.stdout.write(
            "{}: {} current enrollments, {} current groups, {} followed realizations".format(
                student.studentId,
                enrollments.count(),
                len(student_group_ids),
                len(followed_ids),
            )
        )
        if followed_ids:
            self.stdout.write("Explicit follows take precedence over group membership on the timetable page.")

        for enrollment in enrollments:
            subject = enrollment.subject
            self.stdout.write(
                "{} {}: {} year {}".format(
                    subject.code,
                    subject.name,
                    enrollment.study.short_name if enrollment.study else "unknown study",
                    enrollment.classyear,
                )
            )
            activities = subject.activities.filter(activityset=timetable.activityset)
            if not activities.exists():
                self.stdout.write("  no activity in this timetable")
                continue
            for activity in activities.order_by("type", "id"):
                groups = list(activity.groups.filter(groupset=timetable.groupset))
                own_group_ids = {g.id for g in groups} & student_group_ids
                scheduled = Allocation.objects.filter(
                    timetable_id__in=public_timetable_ids,
                    activityRealization__activity=activity,
                    activityRealization_id__in=attended_ids,
                ).exists()
                if scheduled:
                    status = "scheduled"
                elif followed_ids:
                    status = "not followed (explicit follows override groups)"
                elif not groups:
                    status = "no activity groups"
                elif not own_group_ids and not any((g.size or 0) > 0 for g in groups):
                    status = "no positive-size groups"
                elif not own_group_ids:
                    status = "not assigned to an activity group"
                elif not ActivityRealization.objects.filter(
                    activity=activity, groups__id__in=own_group_ids
                ).exists():
                    status = "group not assigned to a realization"
                else:
                    status = "realization has no public allocation in this timetable"
                self.stdout.write(
                    "  {} activity {}: {}; groups: {}; own: {}".format(
                        activity.type,
                        activity.id,
                        status,
                        ", ".join("{} ({})".format(g.short_name, g.size) for g in groups)
                        or "none",
                        ", ".join(g.short_name for g in groups if g.id in own_group_ids)
                        or "none",
                    )
                )
