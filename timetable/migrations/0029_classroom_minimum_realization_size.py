from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetable", "0028_classroomactivitystarttime"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroom",
            name="minimum_realization_size",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Minimum realization size required to use this room. Set 0 for no minimum.",
            ),
        ),
    ]
