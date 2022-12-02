from typing import Dict, List

from django import forms

from exchange.controllers import get_current_student_subject_allocation
from friprosveta.models import Student, Activity, Teacher
from timetable.models import Timetable
from .models import Allocation, SubjectPreference


class AllocationChoiceField(forms.ModelChoiceField):
    def __init__(self, allocation_queryset, *args, **kwargs):
        if allocation_queryset:
            allocation_queryset = allocation_queryset.order_by(
                "-day", "start", "classroom"
            )
        super().__init__(
            allocation_queryset, *args, empty_label="Select other instance", **kwargs
        )

    def label_from_instance(self, obj):
        """Create a description of the allocation.

        Args:
            obj (Allocation): The Allocation object.

        Returns:
            (str): The descriptive choice label for the allocation.
        """
        return "{} at {} in {}".format(obj.day, obj.start, obj.classroom.name)


class ExchangeCreationForm(forms.Form):

    # TODO: use validation here instead of in views, like in the teacher exchange creation form

    requested_student = forms.CharField(
        required=False,
        label="Request a specific student to exchange with you",
        widget=forms.TextInput(attrs={"placeholder": "Email or enrollment number"}),
    )

    def __init__(
        self,
        subject_available_allocation_map,
        subject_attending_allocation_map,
        *args,
        **kwargs
    ):
        """Create a dynamic form.

        Args:
            subject_available_allocation_map (Dict[Subject -> List[Allocation]]): A mapping from subjects to a list of allocations.
            subject_attending_allocation_map (Dict[Subject -> Allocation]): A mapping from subjects the student's of allocation.
        """
        super().__init__(*args, **kwargs)
        subject_fields = []
        for subject in subject_available_allocation_map:
            available_allocations = subject_available_allocation_map[subject]
            attending_allocation = subject_attending_allocation_map[subject]

            # if there are no allocations (subjects without them, subjects in other, but related timetables),
            # don't display that subject
            if not available_allocations:
                continue
            field_key = "subject_{}".format(subject.id)
            subject_fields.append(field_key)
            self.fields[field_key] = AllocationChoiceField(
                available_allocations,
                required=False,
                label="{}: swap your {} at {} in {} for".format(
                    subject.name.strip(),
                    attending_allocation.day,
                    attending_allocation.start,
                    attending_allocation.classroom.name,
                ),
            )
        self.order_fields(subject_fields)

    def get_requested_student(self):
        return self.cleaned_data["requested_student"]

    def get_subject_transfers(self, keep_empty=False):
        result = {}
        for key, value in self.cleaned_data.items():
            if key.startswith("subject_") and (keep_empty or value is not None):
                subject_id = int(key[len("subject_") :])
                result[subject_id] = value
        return result


class SubjectPreferenceForm(forms.ModelForm):
    class Meta:
        model = SubjectPreference
        fields = ["subject", "exchange_allowed", "exchange_deadline"]
        widgets = {
            "subject": forms.HiddenInput(),
            "exchange_deadline": forms.TextInput(
                attrs={"placeholder": "e.g. 2018-02-14"}
            ),
        }


class StudentSelectionField(forms.ModelChoiceField):
    def __init__(self, queryset, *args, **kwargs):
        super().__init__(queryset, *args, empty_label="Select a student...", **kwargs)

    def label_from_instance(self, student):
        return "{} {} ({})".format(
            self._fix_name_caps(student.name),
            self._fix_name_caps(student.surname),
            student.studentId,
        )

    @classmethod
    def _fix_name_caps(cls, name):
        return " ".join(n.title() for n in name.split(" "))


class StudentSelectionForm(forms.Form):
    selected_student = StudentSelectionField(None)

    def __init__(self, available_students, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selected_student"].queryset = available_students


class TeacherExchangeCreationForm(forms.Form):

    # TODO: unit test this

    timetable = forms.ModelChoiceField(None, widget=forms.HiddenInput())
    teacher = forms.ModelChoiceField(None, widget=forms.HiddenInput())
    student = StudentSelectionField(None)
    current_student_allocation: Allocation = forms.ModelChoiceField(None)
    requested_student_allocation: Allocation = None

    def __init__(self, available_allocations, *args, **kwargs):
        super().__init__(*args, **kwargs)

        initial_timetable = (kwargs or {}).get("initial", {}).get("timetable", None)
        initial_teacher = (kwargs or {}).get("initial", {}).get("teacher", None)
        initial_student = (kwargs or {}).get("initial", {}).get("student", None)
        initial_allocation_from = (
            (kwargs or {}).get("initial", {}).get("current_student_allocation", None)
        )

        self.fields["timetable"].queryset = Timetable.objects.filter(
            id=initial_timetable.id if initial_timetable else -1
        )
        self.fields["teacher"].queryset = Teacher.objects.filter(
            id=initial_teacher.id if initial_teacher else -1
        )
        self.fields["student"].queryset = Student.objects.filter(
            id=initial_student.id if initial_student else -1
        )
        self.fields["current_student_allocation"].queryset = Allocation.objects.filter(
            id=initial_allocation_from.id if initial_allocation_from else -1
        )
        self.fields["requested_student_allocation"] = AllocationChoiceField(
            available_allocations
        )

    def get_subject_transfer_map(self):
        # assumes clean
        # the teacher here acts as if they have the wanted lab cycle, and transfer to the one the student attends
        allocation = self.cleaned_data["current_student_allocation"]
        subject = Activity.from_timetable_activity(
            allocation.activityRealization.activity
        ).subject
        return {subject.id: allocation}

    def clean(self):
        # the fields have already been cleaned, all are required by default
        super_result = super().clean()

        # fail-fast if anything is undefined
        timetable = self.cleaned_data.get("timetable")
        teacher = self.cleaned_data.get("teacher")
        student = self.cleaned_data.get("student")
        current_student_allocation = self.cleaned_data.get("current_student_allocation")
        requested_student_allocation = self.cleaned_data.get(
            "requested_student_allocation"
        )
        if not (
            timetable
            and teacher
            and student
            and current_student_allocation
            and requested_student_allocation
        ):
            return super_result

        # ensure allocations are for the same subject
        subject_from = Activity.from_timetable_activity(
            current_student_allocation.activityRealization.activity
        ).subject
        subject_to = Activity.from_timetable_activity(
            requested_student_allocation.activityRealization.activity
        ).subject
        if subject_from != subject_to:
            raise forms.ValidationError(
                "The allocations do not belong to the same subject."
            )

        # ensure the student attends the source allocation
        student_allocation = get_current_student_subject_allocation(
            timetable, student, subject_from, ["LAB", "LV", "AV"]
        )
        if current_student_allocation != student_allocation:
            raise forms.ValidationError(
                "The student does not currently attend the source allocation."
            )

        # ensure the teacher is the owner of the subject
        if teacher not in subject_from.teachers(timetable):
            raise forms.ValidationError("You are not an owner of this subject.")

        return super_result
