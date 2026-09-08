from django import forms

from timetable.models import AFTERHOURS, WORKHOURS, Teacher

from .models import ActivityRealizationSchedulingWindow, TeacherSchedulingWindow
from .solver_forms import _realization_queryset


class ActivityRealizationSchedulingWindowForm(forms.ModelForm):
    class Meta:
        model = ActivityRealizationSchedulingWindow
        fields = ("realization", "day", "unrestricted", "start", "end", "weight")

    def __init__(self, *args, timetable, **kwargs):
        self.timetable = timetable
        super().__init__(*args, **kwargs)
        self.fields["realization"].queryset = _realization_queryset(timetable)
        self.fields["start"].choices = WORKHOURS
        self.fields["end"].choices = WORKHOURS + (AFTERHOURS,)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("unrestricted"):
            cleaned["start"] = None
            cleaned["end"] = None
            cleaned["weight"] = 0
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.timetable = self.timetable
        if commit:
            existing = ActivityRealizationSchedulingWindow.objects.filter(
                timetable=self.timetable,
                realization=instance.realization,
                day=instance.day,
            ).first()
            if existing is not None:
                for field in self.Meta.fields:
                    setattr(existing, field, getattr(instance, field))
                instance = existing
            instance.full_clean()
            instance.save()
        return instance


class TeacherSchedulingWindowForm(forms.ModelForm):
    class Meta:
        model = TeacherSchedulingWindow
        fields = ("teacher", "day", "unrestricted", "start", "end", "weight")

    def __init__(self, *args, timetable, **kwargs):
        self.timetable = timetable
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = (
            timetable.teachers.select_related("user")
            if timetable.activityset_id is not None
            else Teacher.objects.none()
        )
        self.fields["start"].choices = WORKHOURS
        self.fields["end"].choices = WORKHOURS + (AFTERHOURS,)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("unrestricted"):
            cleaned["start"] = None
            cleaned["end"] = None
            cleaned["weight"] = 0
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.timetable = self.timetable
        if commit:
            existing = TeacherSchedulingWindow.objects.filter(
                timetable=self.timetable,
                teacher=instance.teacher,
                day=instance.day,
            ).first()
            if existing is not None:
                for field in self.Meta.fields:
                    setattr(existing, field, getattr(instance, field))
                instance = existing
            instance.full_clean()
            instance.save()
        return instance
