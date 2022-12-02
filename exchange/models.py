from enum import Enum
import logging

from django.db import models
from django.db.models import Model, Q

from friprosveta.models import Subject, Student
from timetable.models import Allocation


logger = logging.getLogger(__name__)


TIMETABLE_EXCHANGE_GROUP_PREFIX = "EX"
"""The prefix to use for timetable groups where exchanged students are moved."""


class ExchangeType(Enum):
    """Defines the possible exchange types.

    See the get_type function for how these are determined.

    Attributes:
         ExchangeType.REQUEST_OFFER: A regular exchange made from a request and an offer.
         ExchangeType.SPECIFIC_STUDENT: An exchange where one student offers to another, specific student.
         ExchangeType.FREE_CHANGE: This exchange was free because there were available spaces in another activity cycle.
         ExchangeType.TEACHER_OFFER: A teacher created this offer to allow a student to change cycles without a match.
    """

    REQUEST_OFFER = 0
    SPECIFIC_STUDENT = 1
    FREE_CHANGE = 2
    TEACHER_OFFER = 4


class InvalidExchangeTypeError(Exception):
    """Raised when an exchange is determined to be of an impossible type."""

    pass


class FormProcessingError(Exception):
    """Raised when a form encounters an error."""

    def __init__(self, header, message):
        super().__init__(message)
        self.header = header
        self.message = message
        logger.warning("FormProcessingError - {}: {}".format(self.header, self.message))


class SubjectPreference(models.Model):
    subject = models.OneToOneField(
        Subject,
        related_name="exchange_preference",
        unique=True,
        on_delete=models.CASCADE,
    )

    exchange_allowed = models.BooleanField(default=True)
    exchange_deadline = models.DateField(blank=True, null=True)


class Exchange(models.Model):
    allocation_from = models.ForeignKey(
        Allocation, related_name="from_exchanges", on_delete=models.CASCADE
    )
    """The `Allocation` that this `Exchange` object changes from.

    Notes:
        Assertion:
          - `Exchange.allocation_from` and `Exchange.allocation_to` belong to the same `timetable.models.Activity`,
            and, with that, the same subject.
    """

    allocation_to = models.ForeignKey(
        Allocation,
        related_name="to_exchanges",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    """The `Allocation` that this `Exchange` object changes to. 

    Notes:
        Nullable. When:
          - `ExchangeType.FREE_CHANGE` (there is no set allocation to change to, however, the linked `Exchange` does
            have this and allocation_from set)
        Assertion:
          - `Exchange.allocation_from` and `Exchange.allocation_to` belong to the same `timetable.models.Activity`,
            and, with that, the same subject.
    """

    initiator_student = models.ForeignKey(
        Student,
        related_name="initiated_exchanges",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    """The `Student` that created this exchange. 
    
    For initiating exchange objects, this is the initiated/requested this exchange. For finalizing exchange objects,
    this is the student that accepted this exchange (and is therefore always non-null).
    
    Notes:
        Nullable. When:
          - `ExchangeType.FREE_CHANGE` (students cannot offer up a free slot of this type)
          - `ExchangeType.TEACHER_OFFER` (these offers are created by teachers)
    """

    finalizer_exchange = models.OneToOneField(
        "self",
        related_name="finalized_exchange",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    """The `Exchange` that finalized this one.
    
    Currently, `finalizer_exchange` and `finalized_exchange` have the same meaning. If, in the future, we decide to
    support matching multiple at once (e.g. A -> B -> C -> A), the meaning may change. 
    
    Notes:
        Nullable. When:
          - this exchange has not been finalized yet.
    """

    requested_finalizer_student = models.ForeignKey(
        Student,
        related_name="requested_exchange_finalizations",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    """An exchange can have a request for a specific `Student` to finalize it.
    
    Notes:
        Nullable. When:
          - `ExchangeType.FREE_CHANGE` (these are free for anyone to finalize)
          - `ExchangeType.REQUEST_OFFER` (these are regular requests and offers without this request)
    """

    date_created = models.DateTimeField()
    """The date this `Exchange` was created."""

    date_finalized = models.DateTimeField(blank=True, null=True)
    """The date this `Exchange` was finalized.
    
    Notes:
        This is the definitive source on whether this exchange has been finalized, as `Exchange.finalizer_exchange`
        is only set on the initiating exchange.
        Nullable. When:
          - this exchange has not been finalized yet
    """

    date_cancelled = models.DateTimeField(blank=True, null=True)
    """The date this `Exchange` was cancelled.
    
    Notes:
        Nullable. When:
          - this exchange is not cancelled
    """

    def __str__(self):
        return "Exchange ({}, {}) from {} to {}, initiated by {}".format(
            self.get_type().name,
            "cancelled"
            if self.is_cancelled()
            else "finalised"
            if self.is_finalized()
            else "not finalised",
            str(self.allocation_from),
            str(self.allocation_to) if self.allocation_to is not None else "N/A",
            str(self.initiator_student)
            if self.initiator_student is not None
            else "N/A",
        )

    def __repr__(self):
        return str(self)

    def is_finalized(self):
        return self.date_finalized is not None

    def is_cancelled(self):
        return self.date_cancelled is not None

    def _get_type_isolated(self):
        """Internal: determines the type of the exchange entry, without regard of the finalization status."""

    def get_type(self):
        """Get the type of this exchange entry.

        The criteria for determining the type of an entry are based on the presence of some attributes:
          1) allocation_to
          2) initiator_student
          3) requested_finalizer_student

        If all of them are present, this is an offer from a student to a specific student.
        If none of them are present, this is a free change, where there is space in another cycle.
        If only 1) and 3) are present, it is an offer for a specific student made by a teacher.
        If only 1) and 2) are present, it is a basic offer made to be completed by any student.
        Other combinations produce an invalid exchange.

        The criteria for determining the type if a finalized or unfinalized entry do not differ.
        An exchange pair may consist of multiple types.
        """
        has_allocation_to = self.allocation_to is not None
        has_initiator_student = self.initiator_student is not None
        has_requested_finalizer_student = self.requested_finalizer_student is not None

        if (
            has_allocation_to
            and not has_initiator_student
            and has_requested_finalizer_student
        ):
            return ExchangeType.TEACHER_OFFER
        elif (
            has_allocation_to
            and has_initiator_student
            and has_requested_finalizer_student
        ):
            return ExchangeType.SPECIFIC_STUDENT
        elif (
            not has_allocation_to
            and not has_initiator_student
            and not has_requested_finalizer_student
        ):
            return ExchangeType.FREE_CHANGE
        elif (
            has_allocation_to
            and has_initiator_student
            and not has_requested_finalizer_student
        ):
            return ExchangeType.REQUEST_OFFER
        else:
            raise InvalidExchangeTypeError()

    def _get_all_matching(self):
        """Find all matching exchange requests.

        The matching functionality is symmetric, even if it does not necessarily need to be.
        That means that a newly-added `ExchangeType.FREE_CHANGE` request will match existing requests,
        as will a newly-added `ExchangeType.TEACHER_OFFER`.

        Returns:
            (QuerySet[Exchange]): A matching exchange request.
        """
        if self.is_finalized() or self.is_cancelled():
            return Exchange.objects.none()

        t = self.get_type()
        initial = Exchange.objects.filter(
            Q(date_finalized__isnull=True) & Q(date_cancelled__isnull=True)
        )
        if t == ExchangeType.REQUEST_OFFER:
            # matching these is the most complex
            # we can match this with anything but a SPECIFIC_STUDENT type
            matches = initial.filter(
                # these candidates are TEACHER_OFFERs, which match completely
                (
                    Q(
                        requested_finalizer_student__isnull=False,
                        initiator_student__isnull=True,
                    )
                    & Q(requested_finalizer_student=self.initiator_student)
                    & Q(allocation_from=self.allocation_to)
                    & Q(allocation_to=self.allocation_from)
                )
                |
                # these can be REQUEST_OFFER or FREE_CHANGE
                (
                    Q(requested_finalizer_student__isnull=True)
                    &
                    # REQUEST_OFFER, matches both from and to
                    (
                        (
                            Q(allocation_to__isnull=False)
                            & Q(allocation_from=self.allocation_to)
                            & Q(allocation_to=self.allocation_from)
                        )
                        |
                        # FREE_CHANGE, the candidate's from matches our to
                        (
                            Q(allocation_to__isnull=True)
                            & Q(allocation_from=self.allocation_to)
                        )
                    )
                )
            )
        elif t == ExchangeType.TEACHER_OFFER:
            # these can only be matched with an offer initiated by the student
            # also, both allocations must be set to their proper values
            matches = initial.filter(
                Q(initiator_student=self.requested_finalizer_student),
                Q(allocation_from=self.allocation_to)
                & Q(allocation_to=self.allocation_from),
            )
        elif t == ExchangeType.SPECIFIC_STUDENT:
            # these can only match other SPECIFIC_STUDENT offers
            matches = initial.filter(
                Q(allocation_from=self.allocation_to)
                & Q(allocation_to=self.allocation_from)
                & Q(initiator_student=self.requested_finalizer_student)
                & Q(requested_finalizer_student=self.initiator_student)
            )
        elif t == ExchangeType.FREE_CHANGE:
            # free changes must not match specific students, teacher offers, or other free changes
            # only matches request-offers
            matches = initial.filter(
                Q(initiator_student__isnull=False)
                & Q(requested_finalizer_student__isnull=True)
                & Q(allocation_to__isnull=False)
                & Q(allocation_to=self.allocation_from)
            )
            pass
        else:
            # this should have been handled upstream, fail hard
            raise ValueError("Invalid exchange type.")

        return matches

    def get_match(self):
        """Get the best match for this exchange.

        Returns:
            (Optional[Exchange]): The best matching exchange or None if no matching exchanges exist.
        """
        matches = self._get_all_matching()
        # for multiple matches, we prioritise any manually created ones, followed by the free exchanges
        # within that, matches are ordered by the time of their creation
        match_manual = matches.filter(allocation_to__isnull=False)
        match_free_exchange = matches.filter(allocation_to__isnull=True)
        if match_manual:
            matches = match_manual
        else:
            matches = match_free_exchange

        # we may have found multiple appropriate matches, but the one that we want to return is the earliest one
        match = matches.order_by("date_created").first()
        return match

    def matches(self, other):
        """Determine whether two exchanges match.

        Args:
            other (Exchange): The other exchange.

        Returns:
            (bool): Whether the two exchanges match.
        """
        matches = self._get_all_matching()
        return other in matches
