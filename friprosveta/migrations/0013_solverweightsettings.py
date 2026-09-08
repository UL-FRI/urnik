from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("friprosveta", "0012_activitytypeschedulingrestriction"),
    ]

    operations = [
        migrations.CreateModel(
            name="SolverWeightSettings",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("scheduling_window_weight", models.PositiveIntegerField(default=10000)),
                ("lecture_grid_alignment_weight", models.PositiveIntegerField(default=8)),
                ("consecutive_teacher_room_weight", models.PositiveIntegerField(default=10)),
                ("room_adjacency_weight", models.PositiveIntegerField(default=2)),
                ("lecture_back_to_back_penalty", models.PositiveIntegerField(default=10)),
                (
                    "timetable",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="solver_weight_settings",
                        to="timetable.timetable",
                    ),
                ),
            ],
        ),
    ]
