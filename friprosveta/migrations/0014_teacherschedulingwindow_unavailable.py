from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("friprosveta", "0013_solverweightsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherschedulingwindow",
            name="unavailable",
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveConstraint(
            model_name="teacherschedulingwindow",
            name="teacher_scheduling_window_valid_bounds",
        ),
        migrations.AddConstraint(
            model_name="teacherschedulingwindow",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(end__isnull=True, start__isnull=True, unavailable=False, unrestricted=True)
                    | models.Q(end__isnull=True, start__isnull=True, unavailable=True, unrestricted=False)
                    | models.Q(
                        end__isnull=False,
                        start__isnull=False,
                        start__lt=models.F("end"),
                        unavailable=False,
                        unrestricted=False,
                    )
                ),
                name="teacher_scheduling_window_valid_bounds",
            ),
        ),
    ]
