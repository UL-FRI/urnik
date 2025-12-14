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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set up the requirements field but don't make it globally required
        # We'll validate per resource group instead
        self.fields['requirements'].required = False
    
    def clean_requirements(self):
        """Validate that at least one resource is selected from each required group."""
        selected_resources = self.cleaned_data.get('requirements')
        
        # Get all resource groups with constraints
        required_groups = timetable.models.ResourceGroup.objects.filter(required=True)
        exactly_one_groups = timetable.models.ResourceGroup.objects.filter(exactly_one=True)
        
        errors = []
        
        # Check required groups (at least one)
        for group in required_groups:
            group_resources = group.resources.all()
            selected_count = sum(1 for resource in selected_resources if resource in group_resources)
            
            if selected_count == 0:
                errors.append(f"Prosimo, izberite vsaj eno zahtevo iz skupine '{group.name}'")
        
        # Check exactly_one groups (exactly one)
        for group in exactly_one_groups:
            group_resources = group.resources.all()
            selected_count = sum(1 for resource in selected_resources if resource in group_resources)
            
            if selected_count == 0:
                errors.append(f"Prosimo, izberite natančno eno zahtevo iz skupine '{group.name}'")
            elif selected_count > 1:
                errors.append(f"Iz skupine '{group.name}' lahko izberete samo eno zahtevo (trenutno izbranih: {selected_count})")
        
        if errors:
            raise forms.ValidationError(errors)
        
        return selected_resources

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
            "required_rooms",
            "cycles_on_site",
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
