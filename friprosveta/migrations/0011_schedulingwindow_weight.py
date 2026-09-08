from django.db import migrations, models
from django.core.validators import MaxValueValidator, MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ("friprosveta", "0010_teacherschedulingwindow"),
    ]

    operations = [
        migrations.AddField(
            model_name="activitytypeschedulingwindow",
            name="weight",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="100 makes this window hard; lower values make it a soft preference.",
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
        migrations.AddField(
            model_name="activityrealizationschedulingwindow",
            name="weight",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="100 makes this window hard; lower values make it a soft preference.",
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
        migrations.AddField(
            model_name="teacherschedulingwindow",
            name="weight",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="100 makes this window hard; lower values make it a soft preference.",
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
    ]
