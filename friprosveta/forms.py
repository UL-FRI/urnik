from decimal import Decimal

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import Coalesce
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
    site_cycles = forms.IntegerField(
        label="Cikli na FRI",
        min_value=0,
        required=False,
        help_text="Koliko ciklov želite izvajati na FRI.",
    )

    def __init__(self, *args, **kwargs):
        self.min_physical_cycle_percentage = kwargs.pop(
            "min_physical_cycle_percentage", 100
        )
        super().__init__(*args, **kwargs)
        # Set up the requirements field but don't make it globally required
        # We'll validate per resource group instead
        self.fields['requirements'].required = False
        if "lecture_split" in self.fields:
            if self.instance.type == "P" and self.instance.duration == 3:
                self.fields["lecture_split"].required = False
                self.fields["lecture_split"].help_text = (
                    "Če vam tri ure skupaj ne ustrezajo, izberite želeno razdelitev."
                )
            else:
                self.fields["lecture_split"].widget = forms.HiddenInput()
        all_cycles = getattr(self.instance, "all_cycles", None)
        if all_cycles is None:
            all_cycles = self._all_cycles()
            self.instance.all_cycles = all_cycles
        if all_cycles is not None:
            cycles_on_site = self.instance.cycles_on_site
            if cycles_on_site is None:
                cycles_on_site = all_cycles
            self.fields["site_cycles"].initial = cycles_on_site
            min_site_cycles = int(all_cycles * self.min_physical_cycle_percentage / 100)
            self.fields["site_cycles"].help_text = (
                "Koliko ciklov želite izvajati na FRI. Najmanj: {} od {}."
            ).format(min_site_cycles, all_cycles)

    def _all_cycles(self):
        if not self.instance or not self.instance.pk:
            return None
        if not hasattr(self.instance, "subject") or not self.instance.subject_id:
            return None
        timetable_set_ids = self.instance.activityset.timetable_set.values_list(
            "timetable_sets", flat=True
        )
        all_cycles = frinajave.models.TeacherSubjectCycles.objects.filter(
            subject_code=self.instance.subject.code,
            timetable_set_id__in=timetable_set_ids,
            lecture_type=self.instance.lecture_type_id,
        ).aggregate(suma=Coalesce(Sum("cycles"), Decimal(0)))["suma"]
        return int(round(all_cycles))
    
    def clean_requirements(self):
        """Validate that at least one resource is selected from each required group."""
        selected_resources = self.cleaned_data.get('requirements')
        if selected_resources is None:
            selected_resources = []
        
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
        selected_ids = [resource.id for resource in selected_resources]
        incompatible_resources = timetable.models.ResourceIncompatibility.objects.filter(
            Q(resource_a_id__in=selected_ids, resource_b_id__in=selected_ids)
            | Q(resource_b_id__in=selected_ids, resource_a_id__in=selected_ids)
        ).select_related("resource_a", "resource_b")
        for incompatibility in incompatible_resources:
            errors.append(
                "Zahtev '{}' in '{}' ni mogoče izbrati skupaj".format(
                    incompatibility.resource_a,
                    incompatibility.resource_b,
                )
            )
        
        if errors:
            raise forms.ValidationError(errors)
        
        return selected_resources

    def clean_site_cycles(self):
        site_cycles = self.cleaned_data.get("site_cycles")
        all_cycles = getattr(self.instance, "all_cycles", None)
        if site_cycles is None:
            site_cycles = all_cycles or 0
        if all_cycles is None:
            return site_cycles
        min_site_cycles = int(all_cycles * self.min_physical_cycle_percentage / 100)
        if site_cycles < min_site_cycles:
            raise forms.ValidationError(
                "Na FRI morate izbrati vsaj {} od {} ciklov.".format(
                    min_site_cycles,
                    all_cycles,
                )
            )
        if site_cycles > all_cycles:
            raise forms.ValidationError(
                "Število ciklov na FRI ne sme presegati vseh ciklov."
            )
        return site_cycles

    def save(self, commit=True):
        instance = super().save(commit=False)
        all_cycles = getattr(self.instance, "all_cycles", None)
        if all_cycles is not None:
            instance.cycles_on_site = self.cleaned_data.get("site_cycles") or 0
        if commit:
            instance.save()
            self.save_m2m()
        return instance

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
