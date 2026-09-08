"""Enabled/disabled weekday-hour grid for activity-type scheduling windows."""
from django import forms

from timetable.models import ACTIVITYTYPES, WEEKDAYS, WORKHOURS

from .models import ActivityTypeSchedulingRestriction, TeacherSchedulingWindow


FULL_DAY_START = WORKHOURS[0][0]
FULL_DAY_END = "22:00"


class ActivityTypeSchedulingWindowForm(forms.Form):
    """FET-style unavailable-time weights for each activity-type time slot."""

    def __init__(self, *args, timetable, **kwargs):
        self.timetable = timetable
        super().__init__(*args, **kwargs)
        existing = {
            (restriction.activity_type, restriction.day, restriction.start): restriction.weight
            for restriction in ActivityTypeSchedulingRestriction.objects.filter(timetable=timetable)
        }
        self.grids = []
        for activity_type, type_label in ACTIVITYTYPES:
            rows = []
            for hour_index, (hour, hour_label) in enumerate(WORKHOURS):
                cells = []
                for day, _day_label in WEEKDAYS:
                    field_name = f"weight_{activity_type}_{day}_{hour_index}"
                    self.fields[field_name] = forms.IntegerField(
                        min_value=0,
                        max_value=100,
                        initial=existing.get((activity_type, day, hour), 0),
                        label="",
                        widget=forms.NumberInput(
                            attrs={
                                "class": "window-weight",
                                "aria-label": f"{type_label}, {day}, {hour} unavailable weight",
                            }
                        ),
                    )
                    cells.append({"field": self[field_name]})
                rows.append({"hour": hour_label, "cells": cells})
            self.grids.append({"type_label": type_label, "activity_type": activity_type, "rows": rows})

    def save(self):
        restrictions = []
        for activity_type, _type_label in ACTIVITYTYPES:
            for day, _day_label in WEEKDAYS:
                for hour_index, (hour, _hour_label) in enumerate(WORKHOURS):
                    weight = self.cleaned_data[f"weight_{activity_type}_{day}_{hour_index}"]
                    if weight:
                        restrictions.append(
                            ActivityTypeSchedulingRestriction(
                                timetable=self.timetable,
                                activity_type=activity_type,
                                day=day,
                                start=hour,
                                weight=weight,
                            )
                        )
        ActivityTypeSchedulingRestriction.objects.filter(timetable=self.timetable).delete()
        ActivityTypeSchedulingRestriction.objects.bulk_create(restrictions)


class TeacherSchedulingWindowGridForm(forms.Form):
    """Najave-style enabled/disabled grid for one teacher's weekly window."""

    def __init__(self, *args, timetable, teacher=None, **kwargs):
        self.timetable = timetable
        self.teacher = teacher
        super().__init__(*args, **kwargs)
        self.rows = []
        if teacher is None:
            return
        existing = {
            window.day: window
            for window in TeacherSchedulingWindow.objects.filter(
                timetable=timetable, teacher=teacher
            )
        }
        for hour_index, (hour, hour_label) in enumerate(WORKHOURS):
            cells = []
            for day, _day_label in WEEKDAYS:
                window = existing.get(day)
                enabled = (
                    not window
                    or window.unrestricted
                    or (not window.unavailable and window.start <= hour < window.end)
                )
                field_name = f"enabled_{day}_{hour_index}"
                self.fields[field_name] = forms.BooleanField(
                    required=False, initial=enabled, label=""
                )
                cells.append({"field": self[field_name]})
            self.rows.append({"hour": hour_label, "cells": cells})
        self.weight_cells = []
        for day, _day_label in WEEKDAYS:
            window = existing.get(day)
            field_name = f"weight_{day}"
            self.fields[field_name] = forms.IntegerField(
                min_value=0, max_value=100,
                initial=(
                    100
                    if window and window.unavailable
                    else window.weight if window and not window.unrestricted else 0
                ),
                label="",
            )
            self.weight_cells.append({"field": self[field_name]})

    def _enabled_hours(self, day):
        return [
            hour
            for hour_index, (hour, _label) in enumerate(WORKHOURS)
            if self.cleaned_data.get(f"enabled_{day}_{hour_index}")
        ]

    def clean(self):
        cleaned = super().clean()
        if self.teacher is None:
            raise forms.ValidationError("Select a teacher before saving a scheduling window.")
        hours = [hour for hour, _label in WORKHOURS]
        for day, _day_label in WEEKDAYS:
            selected = self._enabled_hours(day)
            if not selected:
                continue
            indexes = [hours.index(hour) for hour in selected]
            if indexes != list(range(indexes[0], indexes[-1] + 1)):
                self.add_error(None, f"{day}: enabled time slots must be contiguous.")
        return cleaned

    def save(self):
        hours = [hour for hour, _label in WORKHOURS]
        for day, _day_label in WEEKDAYS:
            selected = self._enabled_hours(day)
            if not selected:
                defaults = {
                    "start": None,
                    "end": None,
                    "unrestricted": False,
                    "unavailable": True,
                    "weight": 100,
                }
                existing = TeacherSchedulingWindow.objects.filter(
                    timetable=self.timetable, teacher=self.teacher, day=day
                ).first()
                if existing is None:
                    TeacherSchedulingWindow.objects.create(
                        timetable=self.timetable, teacher=self.teacher, day=day, **defaults
                    )
                else:
                    for field, value in defaults.items():
                        setattr(existing, field, value)
                    existing.save()
                continue
            start = selected[0]
            final_index = hours.index(selected[-1])
            end = hours[final_index + 1] if final_index + 1 < len(hours) else FULL_DAY_END
            existing = TeacherSchedulingWindow.objects.filter(
                timetable=self.timetable, teacher=self.teacher, day=day
            ).first()
            if start == FULL_DAY_START and end == FULL_DAY_END:
                if existing is not None:
                    existing.delete()
                continue
            defaults = {
                "start": start,
                "end": end,
                "unrestricted": False,
                "unavailable": False,
                "weight": self.cleaned_data[f"weight_{day}"],
            }
            if existing is None:
                TeacherSchedulingWindow.objects.create(
                    timetable=self.timetable, teacher=self.teacher, day=day, **defaults
                )
            else:
                for field, value in defaults.items():
                    setattr(existing, field, value)
                existing.save()
