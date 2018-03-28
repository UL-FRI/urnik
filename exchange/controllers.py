from abc import ABC, abstractmethod
import logging
from typing import Optional, Dict, List, Union
from datetime import datetime
from collections import Counter

import pytz
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F, Q, Model
from django.core.cache import cache
from django.conf import settings

from friprosveta.models import Student, Timetable, Subject, Teacher, Activity
from friprosveta.studis import Studenti
from timetable.models import Allocation, Group
from .models import Exchange, SubjectPreference, FormProcessingError, TIMETABLE_EXCHANGE_GROUP_PREFIX, ExchangeType

logger = logging.getLogger(__name__)


def get_student_from_user(user):
    """Get a `Student` object from a `User`.

    Args:
        user (User): The user to fetch student data for.
    Returns:
        Student: Student object.
    Raises:
        Student.DoesNotExist: If there is no such student.
        IOError: If something goes wrong with the API.
    """
    # email is more correct than username, so use that
    email = user.username

    # this isn't really testable, but let's avoid overengineering for now
    if settings.STUDENT_MAPPER_PRODUCTION:
        # initialise if no cached values
        print("REAL")
        mapping = cache.get("cached_user_student_map")
        if mapping is None:
            s = Studenti()
            data = s.get_confirmed_enrollments(datetime.utcnow().isoformat()[:10], unfinished=True)
            if not data:
                raise IOError("Error getting api data.")
            mapping = {a["upn"].strip(): a["vpisna_stevilka"].strip() for a in data if a["upn"] is not None}
            cache.set("cached_user_student_map", mapping)

        student_id = mapping.get(email, "this string is definitely not a student id")

        return Student.objects.get(studentId=student_id)
    else:
        return Student.objects.get(name__iexact=user.first_name, surname__iexact=user.last_name)


def get_available_exchanges(timetable, student):
    """Get the exchanges a student can potentially accept.

    This includes exchanges for cycles the student can't accept at the moment, but are from an enrolled subject.

    Args:
        timetable (Timetable): The requested timetable scope.
        student (Student): The student to get data for.
    Returns:
        list[Exchange]: The matching `Exchange` objects.
    """
    subjects = student.enrolledSubjects(timetable)
    result = []
    for subject in subjects:
        # the double __activity__activity link is because we first access timetable.models.Activity,
        # and then friprosveta.models.Activity, which is a subclass
        ex = Exchange.objects.filter(Q(date_finalized__isnull=True, date_cancelled__isnull=True) &
                                     Q(allocation_from__activityRealization__activity__activity__subject=subject))\
                             .exclude(initiator_student=student)\
                             .distinct()
        result.extend(ex)
    return result


def get_student_exchanges(timetable, student):
    """Get exchanges for a particular student and timetable scope, both pending and finalized.

    Args:
        timetable (Timetable): The requested timetable scope.
        student (Student): The student to get data for.

    Returns:
        list[Exchange]: The matching `Exchange` objects.

    Raises:
        (ValueError): If any argument is None.
    """
    if timetable is None:
        raise ValueError("Cannot get exchanges for an undefined timetable.")
    if student is None:
        raise ValueError("Cannot get exchanges for an undefined student.")
    # any exchange object that a student has a relation to, but only the ones related to the given timetable
    return Exchange.objects.filter((Q(initiator_student=student) | Q(requested_finalizer_student=student)) &
                                   Q(allocation_to__activityRealization__activity__activityset__timetable=timetable))\
                           .distinct()


def get_subject_exchanges(timetable, subject):
    """Get all exchanges for a particular subject and timetable scope.

    Args:
        timetable (Timetable): The requested timetable scope.
        subject (Subject): The subject to get data for.

    Returns:
        list[Exchange]: The matching `Exchange` objects.

    Raises:
        (ValueError): If any argument is None.
    """
    if timetable is None:
        raise ValueError("Cannot get exchanges for an undefined timetable.")
    if subject is None:
        raise ValueError("Cannot get exchanges for an undefined subject.")
    return Exchange.objects.filter(allocation_from__activityRealization__activity__activity__subject=subject,
                                   allocation_from__activityRealization__activity__activityset__timetable=timetable)


def get_teacher_subject_list(timetable, teacher):
    """Get a list of subjects the teacher is responsible for in the given timetable scope.

    Args:
        timetable (Timetable): The requested timetable scope.
        teacher (Teacher): The teacher to get data for.

    Returns:
        list[Subject]: The matching subjects.

    Raises:
        (ValueError): If any argument is None.
    """
    if timetable is None:
        raise ValueError("Cannot get subjects for an undefined timetable.")
    if teacher is None:
        raise ValueError("Cannot get subjects for an undefined teacher.")
    activities = Activity.objects.filter(teachers__exact=teacher, activityset__timetable__exact=timetable)
    return Subject.objects.filter(id__in=activities.values_list('subject', flat=True).distinct())


def get_student_subject_list(timetable, student):
    """Get a list of subjects the student is enrolled in in the given timetable scope.

    Args:
        timetable (Timetable): The requested timetable scope.
        student (Student): The student to get data for.

    Returns:
        list[Subject]: The matching subjects.
    """
    return student.enrolledSubjects(timetable)


def teacher_teaches_subject(timetable, teacher, subject):
    """Determine whether a teacher teaches a subject in a given timetable.

    Args:
        timetable (Timetable): The requested timetable scope.
        teacher (Teacher): The teacher to get data for.
        subject (Subject): The subject to get data for.

    Returns:
        bool: Whether a teacher teaches a subject in a given timetable.
    """
    subjects = get_teacher_subject_list(timetable, teacher)
    return subject in subjects


def get_allocations_for_subject(timetable, subject, activity_types=None):
    """Get a list of allocations for a given subject.

    Optionally filter by activity types (see `timetable.models.ACTIVITYTYPES`).

    Args:
        timetable (Timetable): The requested timetable scope.
        subject (Subject): The subject to get allocations for.
        activity_types (list[str]): A list of activity types for filter with or None to skip filtering.

    Returns:
        (list[Allocation]): A list of allocations for the subject matching the specified criteria.

    Raises:
        (ValueError): If any argument is None.
    """
    if timetable is None:
        raise ValueError("Cannot get allocations for a non-existent timetable.")
    if subject is None:
        raise ValueError("Cannot get allocations for an undefined subject.")
    allocations = Allocation.objects.filter(timetable=timetable, activityRealization__activity__activity__subject=subject)
    if activity_types is not None:
        allocations = allocations.filter(activityRealization__activity__type__in=activity_types)
    return allocations


def parse_student_from_ambiguous_identifier(student_string):
    """Obtain a student from a string, which can be either an enrollment number or an e-mail address.

    Args:
        student_string (str): A student's enrollment number or e-mail address.

    Returns:
        (Student): The matching student.

    Raises:
        (FormProcessingError): If anything went wrong. Message attached.
    """
    # best-effort: an enrollment number can always be parsed as a number (but is not a number)
    student: Student = None
    try:
        int(student_string)
        student = Student.objects.get(studentId=student_string)
    except (ValueError, Student.DoesNotExist):
        # it may be an email
        try:
            user = User.objects.get(email=student_string)
            student = get_student_from_user(user)
        except User.DoesNotExist:
            raise FormProcessingError("Student not found.", "'{}' is not a valid e-mail or "
                                                            "enrollment number.".format(student_string))
    if student is None:
        raise FormProcessingError("Student not found.", "No matching student found.")
    return student


def get_current_student_subject_allocation(timetable, student, subject, activity_types):
    """Get the allocation the student is currently attending.

    Args:
        timetable (Timetable): The requested timetable scope.
        student (Student): The student to get the allocation for.
        subject (Subject): The subject of which to get the allocation for.
        activity_types (list[str]): Limit the types of activities (e.g. labs, lectures).

    Returns:
        (Allocation): The student's current allocation.

    Raises:
        (Allocation.DoesNotExist): If no matching allocation is found.
        (Allocation.MultipleObjectsReturned): If there are multiple matching allocations.
        (ValueError): If any argument is None.
    """
    if student is None:
        raise ValueError("Cannot get allocations for an unspecified student.")
    subject_allocations = get_allocations_for_subject(timetable, subject, activity_types=activity_types)
    return subject_allocations.get(activityRealization__groups__students=student)


def get_student_subject_other_allocations(timetable, student, subject, activity_types):
    """Get allocations for a subject that a student is _not_ currently attending.

    Args:
        timetable (Timetable): The requested timetable scope.
        student (Student): The student to get the allocations for.
        subject (Subject): The subject of which to get the allocations for.
        activity_types (list[str]): Limit the types of activities (e.g. labs, lectures).

    Returns:
        QuerySet[Allocation]: An allocation different from the student's current allocation.
    """
    available_allocations = get_allocations_for_subject(timetable, subject, activity_types=activity_types)
    student_allocation = get_current_student_subject_allocation(timetable, student, subject, activity_types)
    return available_allocations.exclude(id=student_allocation.id)


def number_of_students_in_allocation(allocation):
    """Get the number of students currently attending an allocation.

    Args:
        allocation (Allocation): The allocations to get data for.

    Returns:
        (int): The number of students.

    Raises:
        (ValueError): If `allocation` is None.
    """
    if allocation is None:
        raise ValueError("Cannot count the number of students in a non-existent allocation.")
    return Student.objects.filter(groups__in=list(allocation.groups.all())).count()


def is_exchange_acceptable(exchange, student):
    """Determine if a student can accept an exchange.

    Args:
        exchange (Exchange): The exchange.
        student (Student): The student.

    Returns:
        (bool): Whether the student can accept the given exchange.

    Raises:
        (ValueError): If `exchange` or `student` are None.
    """
    if exchange is None:
        raise ValueError("Cannot determine whether an exchange is acceptable for an undefined exchange.")
    if student is None:
        raise ValueError("Cannot determine whether an exchange is acceptable for an undefined student.")

    subject = Activity.from_timetable_activity(exchange.allocation_from.activityRealization.activity).subject
    timetable = exchange.allocation_from.timetable

    allocation_from = get_current_student_subject_allocation(timetable, student, subject, ["LAB", "LV", "AV"])
    allocation_to = exchange.allocation_from
    initiator_student = student
    requested_finalizer_student = exchange.initiator_student if exchange.requested_finalizer_student else None

    # creating this enables us to use consolidated matching logic
    dummy_exchange = Exchange(
        allocation_from=allocation_from,
        allocation_to=allocation_to,
        initiator_student=initiator_student,
        requested_finalizer_student=requested_finalizer_student,
        date_created=datetime.utcnow()
    )
    return dummy_exchange.matches(exchange)


def is_exchange_cancellable(exchange, student):
    """Determine if a student can cancel the exchange.

    Args:
        exchange (Exchange): The exchange.
        student (Student): The student.

    Returns:
        (bool): Whether the exchange is cancellable by the student.

    Raises:
        (ValueError): If `exchange` or `student` are None.
    """
    if exchange is None:
        raise ValueError("Cannot determine whether an exchange is cancellable for an undefined exchange.")
    if student is None:
        raise ValueError("Cannot determine whether an exchange is cancellable for an undefined student.")

    return not exchange.is_cancelled() and not exchange.is_finalized() and exchange.initiator_student == student


@transaction.atomic
def cancel_exchange(exchange):
    """Cancel the exchange.

    Args:
        exchange (Exchange): The exchange.
    """
    # no errors here, checking should be done externally, we just want to keep data clean
    if exchange.is_finalized() or exchange.is_cancelled():
        return
    exchange.date_cancelled = datetime.utcnow()
    exchange.save()


@transaction.atomic
def process_exchange_request_matches(exchange_left, exchange_right):
    """Perform the matching procedure with two requests.

    Modifies and saves the completed requests, as well as transfers students between groups.

    Args:
        exchange_left (Exchange): One exchange request.
        exchange_right (Exchange): The other exchange request.
    """

    # the exchanges match, but we might not have two students to exchange with
    if exchange_left.initiator_student and exchange_right.initiator_student:
        # here this is either ExchangeType.REQUEST_OFFER or ExchangeType.SPECIFIC_STUDENT
        # in both cases, we have two students and all allocations set
        group_source_left = get_allocation_student_group(exchange_left.allocation_from, exchange_left.initiator_student)
        group_source_right = get_allocation_student_group(exchange_right.allocation_from, exchange_right.initiator_student)

        group_exchange_left = get_allocation_exchange_group(exchange_left.allocation_from) or \
                              create_allocation_exchange_group(exchange_left.allocation_from)
        group_exchange_right = get_allocation_exchange_group(exchange_left.allocation_to) or \
                               create_allocation_exchange_group(exchange_left.allocation_to)
        move_student(exchange_left.initiator_student, group_source_left, group_exchange_right)
        move_student(exchange_right.initiator_student, group_source_right, group_exchange_left)
    else:
        # this is one of
        # ExchangeType.TEACHER_OFFER: has both allocations, but no initiator_student
        # ExchangeType.FREE_CHANGE: only has allocation_from, and no initiator_student
        # the other exchange (the finalizer - either existing or new) has all of these set
        if exchange_left.initiator_student:
            initiating_exchange = exchange_right
            finalizer_exchange = exchange_left
        else:  # new_exchange.initiator_student
            initiating_exchange = exchange_left
            finalizer_exchange = exchange_right

        # the finalizer exchange (the one made by the student) has all the information we need
        group_from = get_allocation_student_group(finalizer_exchange.allocation_from, finalizer_exchange.initiator_student)
        group_to = get_allocation_exchange_group(finalizer_exchange.allocation_to) or \
                   create_allocation_exchange_group(finalizer_exchange.allocation_to)
        # because there is no student on the other end, we only move once
        move_student(finalizer_exchange.initiator_student, group_from, group_to)

    exchange_left.finalizer_exchange = exchange_right
    exchange_right.finalizer_exchange = exchange_left

    now = datetime.utcnow()
    exchange_left.date_finalized = now
    exchange_right.date_finalized = now

    exchange_left.save()
    exchange_right.save()


@transaction.atomic
def process_new_exchange_request(timetable, source_person, requested_student, subject_transfer_to_map, force_allocation_from=None):
    """
    Args:
        timetable (Timetable): The requested timetable scope.
        source_person (typing.Union[Teacher, Student, None]): The teacher or student that initiated this request.
                                                              None in case of `ExchangeType.FREE_CHANGE`.
        requested_student (Optional[Student]): The optional requested student counterpart.
        subject_transfer_to_map (typing.Dict[int, Allocation]): A mapping of subjects to their destination allocations.
        force_allocation_from (Optional[Allocation]): Optionally, an allocation to use in the `Exchange.allocation_from`
                                                      field, e.g. when creating an `ExchangeType.TEACHER_OFFER`.

    Returns:
        (bool): True if this request (or any of its contents) was immediately processed and accepted, or False
                if no requested exchanges have been immediately fulfilled.
    """
    logger.debug("Processing new exchange request.")
    # for each transfer request, build the Exchange object
    created_exchanges: List[Exchange] = []
    for subject, transfer_to in subject_transfer_to_map.items():
        try:
            subject = Subject.objects.get(id=subject)
        except Subject.DoesNotExist:
            raise FormProcessingError("Invalid subject.", "An error occurred when processing subjects.")

        # this is the only place where we create preferences
        preference, preference_created = SubjectPreference.objects.get_or_create(subject=subject)
        current_date = datetime.utcnow().date()
        if not preference.exchange_allowed:
            raise FormProcessingError("Exchange not allowed.", "Exchanges for this subject have been disabled.")
        elif preference.exchange_deadline and current_date > preference.exchange_deadline:
            local_tz = pytz.timezone('Europe/Ljubljana')
            dt = datetime.combine(preference.exchange_deadline, datetime.min.time())
            deadline_display = pytz.utc.localize(dt, is_dst=None).astimezone(local_tz)
            # deadline_display = preference.exchange_deadline.replace(tzinfo=pytz.utc).astimezone(local_tz)
            raise FormProcessingError("Exchange not allowed.", "The exchange deadline has passed ({})".format(
                                      deadline_display.strftime("%Y-%m-%d %H:%M")))

        if force_allocation_from:
            allocation_from = force_allocation_from
        else:
            if source_person is None:
                raise FormProcessingError("Invalid exchange creation parameters.",
                                          "Free changes must force source allocations.")
            elif isinstance(source_person, Teacher):
                raise FormProcessingError("Invalid exchange creation parameters.",
                                          "Teachers must always manually provide a from value.")
            else:
                allocation_from = get_current_student_subject_allocation(timetable, source_person, subject,
                                                                         activity_types=["LAB", "LV", "AV"])

        if source_person is None or isinstance(source_person, Teacher):
            initiator_student = None
        else:
            initiator_student = source_person

        # now that the parameters are processed, do some final security checks
        # check that the student actually attends allocation_from (and with that, the subject)
        if initiator_student:
            a = get_current_student_subject_allocation(timetable, initiator_student, subject, ["LAB", "LV", "AV"])
            if a != allocation_from:
                raise FormProcessingError("Operation not permitted",
                                          "You do not satisfy attendance prerequisites.")

        # check that from and to are the same subject
        # also that from and to are not the same (sanity)
        if transfer_to:
            subject_from = Activity.from_timetable_activity(allocation_from.activityRealization.activity).subject
            subject_to = Activity.from_timetable_activity(transfer_to.activityRealization.activity).subject
            if subject_from != subject_to:
                raise FormProcessingError("Operation not permitted",
                                          "Subjects do not match.")

            if allocation_from == transfer_to:
                raise FormProcessingError("Operation not permitted",
                                          "Allocations are the same.")

        created = Exchange.objects.create(
            allocation_from=allocation_from,
            allocation_to=transfer_to,
            initiator_student=initiator_student,
            requested_finalizer_student=requested_student,
            date_created=datetime.utcnow()
        )
        logger.info("Created a new exchange of type {}: {}".format(created.get_type(), created))
        created_exchanges.append(created)

    # now that we have the new exchange objects, try to match them to existing ones
    any_matches = False
    for exchange in created_exchanges:
        match = exchange.get_match()
        if match:
            logger.info("Found a match for {}: {}".format(exchange, match))
            process_exchange_request_matches(exchange, match)

            # create exchanges if we processed an ExchangeType.FREE_CHANGE, but only if the other slot has space
            # then process those
            if exchange.get_type() == ExchangeType.FREE_CHANGE or match.get_type() == ExchangeType.FREE_CHANGE:
                if exchange.get_type() == ExchangeType.FREE_CHANGE:
                    freed_up_allocation = match.allocation_from
                else:
                    freed_up_allocation = exchange.allocation_from

                attendance_ratio = number_of_students_in_allocation(freed_up_allocation) / freed_up_allocation.classroom.capacity
                if attendance_ratio < 1:
                    logger.info("Exchange request was of type ExchangeType.FREE_CHANGE and the inverse direction has"
                                "space available, creating a new free change request.")
                    friprosveta_activity = Activity.objects.get(activity_ptr=freed_up_allocation.activityRealization.activity)
                    any_matches |= process_new_exchange_request(
                        timetable,
                        None,
                        None,
                        {friprosveta_activity.subject_id: None},
                        force_allocation_from=freed_up_allocation
                    )
                else:
                    logger.info("Exchange request was of type ExchangeType.FREE_CHANGE but the inverse direction does "
                                "not have space available, thus a new free change request will not be created.")
            any_matches = True
    logger.debug("Exchange request processed {} matches.".format("with" if any_matches else "without"))
    return any_matches


def get_allocation_student_group(allocation, student):
    """Get a timetable group for an allocation that a student attends.

    Args:
        allocation (Allocation): The allocation to get a group for.
        student (Student): The student to get a group for.

    Returns:
        (Optional[Group]): The matching timetable group or None if no such group exists.
    """
    return allocation.activityRealization.groups.filter(students=student).first()


def get_allocation_exchange_group(allocation):
    """Get an exchange timetable group for an allocation.

    Args:
        allocation (Allocation): The allocation to get a group for.

    Returns:
        (Optional[Group]): The matching timetable group or None if no such group exists.
    """
    groups = allocation.activityRealization.groups.filter(short_name__startswith=TIMETABLE_EXCHANGE_GROUP_PREFIX)
    return groups.first()


def create_allocation_exchange_group(allocation):
    """Creates an exchange timetable group groups for an allocation.

    Creates a group even if one such group already exists.

    Args:
        allocation (Allocation): The allocation to create a group for.

    Returns:
        (Group): The created group.
    """
    # ctivity = Activity.objects.get(activity=Subject.objects.get(allocation.activityRealization.activity))
    activity = Activity.objects.get(activity_ptr=allocation.activityRealization.activity)
    subject = activity.subject

    # place this in the common groupset
    groupset_ids = allocation.activityRealization.groups.values_list("groupset_id", flat=True)
    common_groupset_id, count = Counter(gid for gid in groupset_ids if gid is not None).most_common(1)[0]

    descriptor = "{}_{}_{}_{}".format(subject.short_name, activity.type, allocation.day, allocation.start)
    new_group = Group.objects.create(
        name="99 - Skupina za menjave - {}".format(descriptor),
        short_name="{}_{}".format(TIMETABLE_EXCHANGE_GROUP_PREFIX, descriptor),
        groupset_id=common_groupset_id,
        # size and parent are both None, as they don't make sense
    )
    allocation.activityRealization.groups.add(new_group)
    allocation.activityRealization.save()

    return new_group


@transaction.atomic
def move_student(student, group_from, group_to):
    """Move a student between groups.

    Args:
        student (Student): The student to move.
        group_from (Group): The group to move from.
        group_to (Group): The group to move the student to.
    """
    group_from.students.remove(student)
    group_to.students.add(student)

