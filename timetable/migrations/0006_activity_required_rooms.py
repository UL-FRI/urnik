# Generated by Django 4.2.2 on 2023-08-31 19:21

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("timetable", "0005_alter_activity_mustnotoverlap"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="required_rooms",
            field=models.ManyToManyField(to="timetable.classroom"),
        ),
    ]
