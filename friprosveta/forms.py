from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.forms.utils import ErrorList

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


class ActivityLongRequirementsForm(forms.ModelForm):
    class Meta:
        model = friprosveta.models.Activity
        exclude = ("groups", "locations", "mustNotOverlap", "before", "teachers")

    class Media:
        js = ("js/jquery-1.7.1.min.js", "js/activities.js")

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=":",
        empty_permitted=False,
        instance=None,
    ):
        super(ActivityLongRequirementsForm, self).__init__(
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            instance,
        )


class ActivityMinimalForm(forms.ModelForm):
    cycles_on_site = forms.IntegerField(
        min_value=0, error_messages={"min_value": "Vnesite nenegativno celo število"}
    )

    class Meta(ActivityLongRequirementsForm.Meta):
        model = friprosveta.models.Activity
        exclude = (
            "groups",
            "short_name",
            "locations",
            "mustNotOverlap",
            "before",
            "teachers",
            "activityRealizations",
            "requirements_per_student",
            "ready_to_schedule",
            "lecture_type",
            "subject",
        )
        widgets = {
            "requirements": FilteredSelectMultiple("Zahteve", is_stacked=False),
            "name": forms.HiddenInput(),
            "short_name": forms.HiddenInput(),
            "activityset": forms.HiddenInput(),
            "type": forms.HiddenInput(),
            "duration": forms.HiddenInput(),
        }

    class Media:
        extend = False  # remove this once django is fixed. See below.
        css = {"all": ("admin/css/forms.css",)}
        js = (
            "admin/js/jsi18n.js",
            "admin/js/vendor/jquery/jquery.js",
            "admin/js/jquery.init.js",
            "admin/js/core.js",
            "admin/js/SelectBox.js",
            "admin/js/SelectFilter2.js",
        )


ActivityMinimalFormset = forms.models.modelformset_factory(
    friprosveta.models.Activity, form=ActivityMinimalForm, extra=0, can_delete=False
)
