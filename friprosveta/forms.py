from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple

import frinajave
import friprosveta.models
import timetable.models
from timetable.models import Allocation


class ActivityAntiDemocraticForm(forms.ModelForm):
    class Meta:
        model = timetable.models.Activity
        exclude = ("groups", "locations", "mustNotOverlap")
        widgets = {
            "name": forms.HiddenInput(),
            "short_name": forms.HiddenInput(),
            "activityset": forms.HiddenInput(),
            "type": forms.HiddenInput(),
            "duration": forms.HiddenInput(),
        }


class AllocationMoveForm(forms.ModelForm):
    class Meta:
        model = Allocation
        fields = ("id", "start", "day", "classroom")


class AllocationNoIdPlaceForm(forms.ModelForm):
    class Meta:
        model = Allocation
        fields = ("start", "day", "classroom")


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = friprosveta.models.Activity
        fields = ("teachers",)
        widgets = {"teachers": FilteredSelectMultiple("Izvajalci", is_stacked=False)}

    class Media:
        extend = False  # remove this once django is fixed. See below.
        css = {"all": ("admin/css/forms.css",)}
        # This is an ugly workaround because SelectFilter depends on jquery which is not in Media
        # js = ('/admin/jsi18n/', 'admin/js/jquery.js', 'admin/js/jquery.init.js',
        #    'admin/js/core.js', 'admin/js/SelectBox.js', 'admin/js/SelectFilter2.js')
        js = (
            "admin/js/jsi18n.js",
            "admin/js/jquery.js",
            "admin/js/jquery.init.js",
            "admin/js/core.js",
            "admin/js/SelectBox.js",
            "admin/js/SelectFilter2.js",
        )


class NajavePercentageForm(forms.ModelForm):
    class Meta:
        model = frinajave.models.TeacherSubjectCycles
        # fields = ('cycles', 'percentage', 'instruction_type', 'comment')
        fields = ("cycles", "instruction_type", "comment")
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 1, "cols": 20}),
        }
