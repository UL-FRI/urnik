from functools import wraps

from collections import defaultdict
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from exchange import controllers
from exchange.controllers import (
    get_teacher_subject_list,
    teacher_teaches_subject,
    get_student_subject_list,
    get_allocations_for_subject,
    process_new_exchange_request,
    get_current_student_subject_allocation,
    parse_student_from_ambiguous_identifier,
    get_available_exchanges,
    get_student_exchanges,
    get_subject_exchanges,
    get_student_subject_other_allocations,
    is_exchange_cancellable,
)
from exchange.forms import (
    ExchangeCreationForm,
    SubjectPreferenceForm,
    StudentSelectionForm,
    TeacherExchangeCreationForm,
)
from exchange.models import (
    FormProcessingError,
    SubjectPreference,
    Exchange,
    ExchangeType,
)
from friprosveta.models import Subject, Teacher, Activity, Student
from timetable.models import Timetable, default_timetable, Allocation


def restrict_to_student(func):
    """Authorisation helper: restricts a view to a logged-in student"""

    def user_is_student(user):
        return Student.from_user(user) is not None

    @wraps(func)
    @login_required
    @user_passes_test(user_is_student, login_url="/exchange/", redirect_field_name=None)
    def inner(*args, **kwargs):
        return func(*args, **kwargs)

    return inner


def restrict_to_teacher(func):
    """Authorisation helper: restricts a view to a logged-in student"""

    def user_is_teacher(user):
        return getattr(user, "teacher") is not None

    @wraps(func)
    @login_required
    @user_passes_test(user_is_teacher, login_url="/exchange/", redirect_field_name=None)
    def inner(*args, **kwargs):
        return func(*args, **kwargs)

    return inner


def _main_redirect_helper(request, timetable_slug):
    """Redirects to a student or teacher view for a specified timetable.

    Args:
        request (WSGIRequest): The request object.
        timetable_slug (str): The slug of the timetable to use.
    """
    # if the current user is a teacher, go to the teacher role, otherwise, assume the user is a student
    if hasattr(request.user, "teacher"):
        return redirect("landing_teacher", timetable_slug=timetable_slug)
    else:
        return redirect("landing_student", timetable_slug=timetable_slug)


@login_required
@require_http_methods(["GET"])
def main_redirect(request):
    timetable = default_timetable(request)
    return _main_redirect_helper(request, timetable.slug)


@login_required
@require_http_methods(["GET"])
def main_redirect_with_timetable(request, timetable_slug):
    return _main_redirect_helper(request, timetable_slug)


@restrict_to_student
@require_http_methods(["GET"])
def landing_student(request, timetable_slug):
    selected_timetable = get_object_or_404(Timetable, slug=timetable_slug)
    student = Student.from_user(request.user)

    student_exchanges = get_student_exchanges(selected_timetable, student)
    pending_exchanges = [ex for ex in student_exchanges if not ex.is_finalized()]
    completed_exchanges = [ex for ex in student_exchanges if ex.is_finalized()]

    student_subjects = get_student_subject_list(selected_timetable, student)
    available_subject_exchanges_allocations = []
    for s in student_subjects:
        # don't show the subject if the student doesn't attend any lab cycles
        try:
            a = get_current_student_subject_allocation(
                selected_timetable, student, s, ["LAB", "LV", "AV"]
            )
        except:
            continue
        available_subject_exchanges_allocations.append(
            (s, get_subject_exchanges(selected_timetable, s), a)
        )

    return render(
        request,
        "exchange/student_main.html",
        {
            "selected_timetable": selected_timetable.__dict__,
            "user": request.user.__dict__,
            "student": student,
            "pending_exchanges": pending_exchanges,
            "completed_exchanges": completed_exchanges,
            "available_subject_exchanges_allocations": available_subject_exchanges_allocations,
        },
    )


@restrict_to_teacher
@require_http_methods(["GET"])
def landing_teacher(request, timetable_slug):
    teacher = request.user.teacher
    selected_timetable = get_object_or_404(Timetable, slug=timetable_slug)

    subjects = get_teacher_subject_list(selected_timetable, teacher)
    return render(
        request,
        "exchange/teacher_main.html",
        {"selected_timetable": selected_timetable, "subjects": subjects},
    )


@restrict_to_teacher
@require_http_methods(["GET", "POST"])
def subject_management(request, timetable_slug, subject_code):
    teacher = request.user.teacher
    selected_timetable = get_object_or_404(Timetable, slug=timetable_slug)
    subject = get_object_or_404(Subject, code=subject_code)
    subject_exchanges = get_subject_exchanges(selected_timetable, subject)

    print(selected_timetable)
    subject_students = subject.get_enrolled_students(selected_timetable).order_by(
        "surname"
    )
    student_selection_form = StudentSelectionForm(subject_students)

    if not teacher_teaches_subject(selected_timetable, teacher, subject):
        raise PermissionDenied

    subject_preference, _ = SubjectPreference.objects.get_or_create(subject=subject)
    form_notification_text = ""
    if request.method == "POST":
        subject_preference_form = SubjectPreferenceForm(
            data=request.POST, instance=subject_preference
        )
        if subject_preference_form.is_valid():
            if subject_preference_form.cleaned_data["subject"] == subject:
                subject_preference_form.save()
                form_notification_text = "Preference change applied!"
            else:
                raise PermissionDenied("Managed and modified subjects do not match.")
    else:
        subject_preference_form = SubjectPreferenceForm(instance=subject_preference)

    return render(
        request,
        "exchange/teacher_subject_management.html",
        {
            "selected_timetable": selected_timetable,
            "subject": subject,
            "subject_exchanges": subject_exchanges,
            "subject_students": subject_students,
            "student_selection_form": student_selection_form,
            "subject_preference_form": subject_preference_form,
            "form_notification_text": form_notification_text,
        },
    )


@restrict_to_student
@require_http_methods(["GET", "POST"])
def create_exchange_student(request, timetable_slug):
    selected_timetable = get_object_or_404(Timetable, slug=timetable_slug)

    student = Student.from_user(request.user)
    subjects = get_student_subject_list(selected_timetable, student)
    subject_available_allocation_map = {}
    subject_attending_allocation_map = {}
    for subject in subjects:
        activity_types = ["LAB", "LV", "AV"]
        try:
            student_allocation = get_current_student_subject_allocation(
                selected_timetable, student, subject, activity_types
            )
            allocations = get_student_subject_other_allocations(
                selected_timetable, student, subject, activity_types
            )
            subject_available_allocation_map[subject] = allocations
            subject_attending_allocation_map[subject] = student_allocation
        except Allocation.DoesNotExist:
            # don't show subjects the student doesn't have attend labs for
            pass

    if request.method == "POST":
        form = ExchangeCreationForm(
            subject_available_allocation_map,
            subject_attending_allocation_map,
            data=request.POST,
        )
        if form.is_valid():
            try:
                requested_student_string = form.get_requested_student()
                requested_student = None
                if requested_student_string:
                    requested_student = parse_student_from_ambiguous_identifier(
                        requested_student_string
                    )
                any_fulfilled = process_new_exchange_request(
                    selected_timetable,
                    student,
                    requested_student,
                    form.get_subject_transfers(keep_empty=False),
                )
            except FormProcessingError as e:
                return render(
                    request,
                    "exchange/exchange_create_result.html",
                    {
                        "selected_timetable": selected_timetable,
                        "header": e.header,
                        "message": e.message,
                    },
                )
            if any_fulfilled:
                header = "Exchange fulfilled immediately!"
                message = "Your request was fulfilled immediately. Check your new slot on your timetable."
            else:
                header = "Request added to the queue."
                message = (
                    "Your request could not be fulfilled immediately and was placed into the queue for it to "
                    "be fulfilled in the future. Check back at a later date!"
                )
            return render(
                request,
                "exchange/exchange_create_result.html",
                {
                    "selected_timetable": selected_timetable,
                    "header": header,
                    "message": message,
                },
            )
        # otherwise fall through to rendering the same form, with the data filled out, as is tradition
    else:
        form = ExchangeCreationForm(
            subject_available_allocation_map, subject_attending_allocation_map
        )

    return render(
        request,
        "exchange/exchange_create.html",
        {"selected_timetable": selected_timetable, "form": form},
    )


@restrict_to_student
@require_http_methods(["GET"])
def accept_exchange(request, timetable_slug, exchange_id):
    selected_timetable = get_object_or_404(Timetable, slug=timetable_slug)
    student = Student.from_user(request.user)
    exchange = get_object_or_404(Exchange, id=exchange_id)

    if exchange.is_finalized():
        header = "Exchange already finalized."
        message = "This exchange has already been finalized."
    elif exchange.is_cancelled():
        header = "Exchange cancelled."
        message = "This exchange is cancelled."
    else:
        subject = Activity.from_timetable_activity(
            exchange.allocation_from.activityRealization.activity
        ).subject
        try:
            any_fulfilled = process_new_exchange_request(
                selected_timetable,
                student,
                exchange.initiator_student
                if exchange.get_type() == ExchangeType.SPECIFIC_STUDENT
                else None,
                {subject.id: exchange.allocation_from},
            )
        except FormProcessingError as e:
            return render(
                request,
                "exchange/exchange_create_result.html",
                {
                    "selected_timetable": selected_timetable,
                    "header": e.header,
                    "message": e.message,
                },
            )
        if any_fulfilled:
            header = "Exchange fulfilled!"
            message = (
                "Your request was fulfilled. Check your new slot on your timetable."
            )
        else:
            header = "Request added to the queue."
            message = (
                "Your request could not be fulfilled immediately and was placed into the queue for it to "
                "be fulfilled in the future. Check back at a later date!"
            )
    return render(
        request,
        "exchange/exchange_create_result.html",
        {
            "selected_timetable": selected_timetable,
            "header": header,
            "message": message,
        },
    )


@require_http_methods(["GET"])
def cancel_exchange(request, timetable_slug, exchange_id):
    selected_timetable = get_object_or_404(Timetable, slug=timetable_slug)
    exchange = get_object_or_404(Exchange, id=exchange_id)

    if getattr(request.user, "teacher", None) is not None:
        cancellable = True
    else:
        student = Student.from_user(request.user)
        cancellable = is_exchange_cancellable(exchange, student)

    if cancellable:
        controllers.cancel_exchange(exchange)
        header = "Exchange cancelled."
        message = "The selected exchange has been cancelled."
    else:
        header = "Cancellation unauthorised,"
        message = "You do not have permission to cancel this exchange."

    return render(
        request,
        "exchange/exchange_create_result.html",
        {
            "selected_timetable": selected_timetable,
            "header": header,
            "message": message,
        },
    )


@restrict_to_teacher
@require_http_methods(["GET", "POST"])
def create_exchange_teacher(request, timetable_slug, subject_code):
    selected_timetable = get_object_or_404(Timetable, slug=timetable_slug)
    teacher = request.user.teacher
    subject = get_object_or_404(Subject, code=subject_code)

    if not teacher_teaches_subject(selected_timetable, teacher, subject):
        raise PermissionDenied

    activity_types = ["LAB", "LV", "AV"]

    student_selection_form = StudentSelectionForm(Student.objects, data=request.GET)
    if not student_selection_form.is_valid():
        return HttpResponseBadRequest()
    selected_student = student_selection_form.cleaned_data["selected_student"]

    try:
        student_allocation = get_current_student_subject_allocation(
            selected_timetable, selected_student, subject, activity_types
        )
        available_allocations = get_student_subject_other_allocations(
            selected_timetable, selected_student, subject, activity_types
        )
    except Allocation.DoesNotExist:
        raise Http404(
            "The student does not attend the subject or no allocations have been found."
        )

    exchange_creation_form = TeacherExchangeCreationForm(
        available_allocations,
        data=request.POST or None,
        initial={
            "timetable": selected_timetable,
            "teacher": teacher,
            "student": selected_student,
            "current_student_allocation": student_allocation,
        },
    )

    # first way into this is with a submitted form with a selected student
    if request.method == "GET":
        return render(
            request,
            "exchange/exchange_create.html",
            {"selected_timetable": selected_timetable, "form": exchange_creation_form},
        )
    else:
        if exchange_creation_form.is_valid():
            any_fulfilled = process_new_exchange_request(
                exchange_creation_form.cleaned_data["timetable"],
                exchange_creation_form.cleaned_data["teacher"],
                exchange_creation_form.cleaned_data["student"],
                exchange_creation_form.get_subject_transfer_map(),
                # the teacher acts as if they attend the allocation the student wants
                force_allocation_from=exchange_creation_form.cleaned_data[
                    "requested_student_allocation"
                ],
            )
            if any_fulfilled:
                header = "Exchange fulfilled immediately!"
                message = "The request was fulfilled immediately. Verify the new slot on the timetable.."
            else:
                header = "Request added to the queue."
                message = (
                    "The request could not be fulfilled immediately and was placed into the queue for it to "
                    "be fulfilled in the future."
                )
            return render(
                request,
                "exchange/exchange_create_result.html",
                {
                    "selected_timetable": selected_timetable,
                    "header": header,
                    "message": message,
                },
            )
            pass
        else:
            return render(
                request,
                "exchange/exchange_create.html",
                {
                    "selected_timetable": selected_timetable,
                    "form": exchange_creation_form,
                },
            )
