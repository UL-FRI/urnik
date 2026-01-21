"""
Timetable-related models: Timetable, TimetableSet, TimetableSite, and Allocation.
"""
import datetime

from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy

from .constants import WEEKDAYS, WEEKDAYSSLO, WORKHOURS, AFTERHOURS


class PreferenceSet(models.Model):
    def __str__(self):
        return self.name

    # children = models.ManyToManyField(PreferenceSet, symetrical = False)
    created = models.DateTimeField(default=datetime.datetime.now)
    slug = models.SlugField()
    name = models.CharField(max_length=64)
    locked = models.BooleanField(default=False)


class TimetableSet(models.Model):
    def __str__(self):
        return self.name

    slug = models.SlugField()
    public = models.BooleanField(default=False)
    name = models.CharField(max_length=64)
    modified = models.DateTimeField(auto_now_add=True)
    timetables = models.ManyToManyField("Timetable", related_name="timetable_sets")

    @property
    def allocations(self):
        return Allocation.objects.filter(
            Q(timetable__timetable_sets__pk=self.pk)
            | Q(timetable__respected_by__timetable_sets__pk=self.pk)
        ).distinct()


def default_timetable_set():
    return TimetableSet.objects.filter(public=True).order_by("-modified")[0]


def default_timetable(request):
    """
    Get the default Timetable for the given site.
    When more than one Timetable is default the latest is chosen.
    When no public Timetable is default for the given Site the exception is thrown.

    The exception is:
    - Site.NotFoundException when site is not found.
    - IndexError when no public timetable exists for a given site.
    """
    all_timetables = Timetable.objects.all()
    current_site = get_current_site(request)
    current_site_default_timetables = all_timetables.filter(
        timetablesite__site=current_site, public=True, timetablesite__default=True
    )
    return current_site_default_timetables.order_by("-start")[0]


class TimetableSite(models.Model):
    """
    Mapping between sites and timetables. Only timetables connected to the given site
    are available on the site. Some timetables for the site can be marked as default.
    """

    timetable = models.ForeignKey(
        "Timetable",
        on_delete=models.CASCADE,
        help_text=_("Timetable to show on the given site"),
        verbose_name=_("Timetable"),
    )
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    default = models.BooleanField()

    def __str__(self):
        desc = "{} => {}".format(self.site.domain, self.timetable.name)
        if self.default:
            desc += " (DEFAULT)"
        return desc


class Timetable(models.Model):
    def __str__(self):
        return self.name

    # respects = models.ManyToManyField('self', blank=True)
    activityset = models.ForeignKey(
        "ActivitySet", blank=True, null=True, on_delete=models.CASCADE
    )

    preferenceset = models.ForeignKey(
        "PreferenceSet", blank=True, null=True, on_delete=models.CASCADE
    )
    groupset = models.ForeignKey(
        "GroupSet",
        blank=True,
        null=True,
        related_name="timetables",
        on_delete=models.CASCADE,
    )
    classroomset = models.ForeignKey(
        "ClassroomSet",
        blank=True,
        null=True,
        related_name="timetables",
        on_delete=models.CASCADE,
    )

    respects = models.ManyToManyField(
        "self", related_name="respected_by", symmetrical=False, blank=True
    )

    @property
    def allocations(self):
        return Allocation.objects.filter(
            Q(timetable__pk=self.pk) | Q(timetable__respected_by__pk=self.pk)
        )

    @property
    def classrooms(self):
        return self.classroomset.classrooms

    @property
    def realizations(self):
        from .activities import ActivityRealization
        return ActivityRealization.objects.filter(
            activity__activityset=self.activityset
        )

    @property
    def preferences(self):
        return self.preferenceset.preferences

    name = models.CharField(max_length=64)
    slug = models.SlugField()
    public = models.BooleanField(default=False)
    start = models.DateField(default=datetime.date.today)
    end = models.DateField(default=datetime.date.today)
    preference_deadline = models.DateField(default=datetime.date.today)
    trading_enabled = models.BooleanField(default=True, help_text="Allow teachers to create and manage trade requests")

    @property
    def activities(self):
        return self.activityset.activities

    @property
    def teachers(self):
        return self.activityset.teachers

    @property
    def groups(self):
        return self.groupset.groups


class Allocation(models.Model):
    def __str__(self):
        # return "{0} {1} {2}".format(self.classroom, self.day, self.start)
        name = ""
        teachers = ""
        duration = "0"
        tt = "?"
        try:
            name = self.activityRealization.activity.name
            teachers = " ".join(
                [str(i) for i in self.activityRealization.teachers.all()]
            )
            duration = str(self.duration)
            tt = str(self.timetable)
        except Exception:
            return "Error"
        s = (
            teachers
            + " ["
            + name
            + "]"
            + " "
            + str(self.classroom)
            + " "
            + self.day
            + " "
            + self.start
            + " (+"
            + duration
            + ")"
            + " "
            + tt
        )
        return s

    def mail_representation_from(self):
        return "{0}, {1}, {2} ob {3}".format(
            self.activityRealization.activity.name,
            self.classroom,
            WEEKDAYSSLO[self.day],
            self.start,
        )

    def mail_representation_to(self):
        return "{0}, {1} ob {2}".format(
            self.classroom, WEEKDAYSSLO[self.day], self.start
        )

    timetable = models.ForeignKey(
        Timetable, related_name="own_allocations", on_delete=models.CASCADE
    )
    # respected_by = models.ManyToManyField(Timetable, related_name='allocations')
    activityRealization = models.ForeignKey(
        "ActivityRealization", related_name="allocations", on_delete=models.CASCADE
    )
    classroom = models.ForeignKey("Classroom", null=True, on_delete=models.CASCADE)
    day = models.CharField(max_length=3, choices=WEEKDAYS)
    start = models.CharField(max_length=5, choices=WORKHOURS)

    @property
    def end(self):
        endi = WORKHOURS.index((self.start, self.start)) + self.duration
        if endi >= len(WORKHOURS):
            return AFTERHOURS[0]
        return WORKHOURS[endi][0]

    @property
    def duration(self):
        return self.activityRealization.duration

    @property
    def teachers(self):
        return self.activityRealization.teachers

    @property
    def groups(self):
        """
        Return the QuerySet of groups on this realization.
        """
        return self.activityRealization.groups.all()

    @property
    def hours(self):
        i = WORKHOURS.index((self.start, self.start))
        hours = WORKHOURS[i : min(len(WORKHOURS), i + self.duration)]
        return [hour[0] for hour in hours]

    @property
    def are_groups_available(self):
        """
        Return True if groups on this allocation are available according to
        their GroupTimePreferences (with level CANT).
        Returns False otherwise.
        """
        return len(self.groups_not_available) == 0

    @property
    def groups_not_available(self):
        """
        Return the list of not-available groups in the allocation timeslot.
        """
        return [
            group
            for group in self.groups
            if not group.is_available(self.day, set(self.hours))
        ]

    @property
    def start_within_working_hours(self):
        """
        Return the set of allocations that starts when this allocation is active.
        """
        return Allocation.objects.filter(
            timetable=self.timetable, day=self.day, start__in=self.hours
        ).exclude(id=self.id)

    def is_classroom_too_small(self):
        """
        Return True if the classroom is too small for this allocation.
        """
        return self.activityRealization.size > self.classroom.capacity

    def is_classroom_too_big(self, percentage):
        """
        Return True if the classroom is too big for this allocation.
        At least percentage (given as float between 0 and 1)
        has to be filled.
        """
        min_group_size = self.classroom.capacity * percentage
        return self.activityRealization.size < min_group_size


class TradeRequest(models.Model):
    """
    Represents a request from a teacher to trade the TIME SLOT of one of their allocations
    with another teacher's allocation time slot. The subject and teacher remain the same,
    only the day/time changes. For example: Teacher A teaches "Math" on Monday 8AM and 
    wants to trade with Teacher B who teaches "Physics" on Wednesday 10AM - after the trade,
    Teacher A teaches "Math" on Wednesday 10AM and Teacher B teaches "Physics" on Monday 8AM.
    """
    
    STATUS_CHOICES = [
        ('OPEN', gettext_lazy('Open')),
        ('MATCHED', gettext_lazy('Matched')),
        ('PENDING_APPROVAL', gettext_lazy('Pending Approval')),
        ('APPROVED', gettext_lazy('Approved')),
        ('REJECTED', gettext_lazy('Rejected')),
        ('CANCELLED', gettext_lazy('Cancelled')),
        ('EXPIRED', gettext_lazy('Expired')),
    ]
    
    # The teacher making the request
    requesting_teacher = models.ForeignKey(
        'Teacher', 
        related_name='trade_requests_made',
        on_delete=models.CASCADE
    )
    
    # The allocation the teacher wants to give away
    offered_allocation = models.ForeignKey(
        Allocation,
        related_name='trade_requests_offering',
        on_delete=models.CASCADE
    )
    
    # The allocation the teacher wants to receive (optional - can be "any suitable")
    desired_allocation = models.ForeignKey(
        Allocation,
        related_name='trade_requests_wanting',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Specific allocation desired, leave empty for 'any suitable'"
    )
    
    # Alternative criteria for desired allocation when desired_allocation is None
    desired_day = models.CharField(
        max_length=3, 
        choices=WEEKDAYS, 
        null=True, 
        blank=True,
        help_text="Preferred day for the trade"
    )
    desired_start_time = models.CharField(
        max_length=5, 
        choices=WORKHOURS, 
        null=True, 
        blank=True,
        help_text="Preferred start time"
    )
    desired_duration = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Preferred duration in hours"
    )
    desired_classroom = models.ForeignKey(
        'Classroom',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='trade_requests_desired_classroom',
        help_text="Preferred classroom for the new time slot"
    )
    
    # Request details
    reason = models.TextField(
        blank=True,
        help_text=gettext_lazy("Optional reason for the trade request")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this request expires (optional)"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='OPEN'
    )
    
    # For matched requests
    matched_with = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='matched_request',
        help_text="The trade request this one is matched with"
    )
    
    # Approval tracking
    approved_by = models.ForeignKey(
        'Teacher',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_trades',
        help_text="Administrator who approved/rejected the trade"
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(
        blank=True,
        help_text="Notes from the administrator about the approval/rejection"
    )
    
    # Teacher rejection tracking (when a teacher rejects before admin approval)
    teacher_rejected_by = models.ForeignKey(
        'Teacher',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rejected_trade_offers',
        help_text="Teacher who rejected this trade offer"
    )
    teacher_rejection_reason = models.TextField(
        blank=True,
        help_text="Reason given by teacher for rejecting the trade"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['requesting_teacher', 'status']),
            models.Index(fields=['offered_allocation']),
            models.Index(fields=['desired_allocation']),
        ]
    
    def clean(self):
        """Validate the trade request."""
        from django.core.exceptions import ValidationError
        
        # Ensure the requesting teacher actually teaches the offered allocation
        # Only check this if both fields are set (during form validation, requesting_teacher might not be set yet)
        if hasattr(self, 'offered_allocation') and self.offered_allocation and hasattr(self, 'requesting_teacher') and self.requesting_teacher:
            if not self.offered_allocation.teachers.filter(id=self.requesting_teacher.id).exists():
                raise ValidationError("You can only trade allocations that you teach.")
        
        # Ensure desired allocation criteria are not conflicting
        if hasattr(self, 'desired_allocation') and self.desired_allocation and (self.desired_day or self.desired_start_time or self.desired_duration):
            raise ValidationError("Cannot specify both a specific desired allocation and desired criteria.")
    
    def save(self, *args, **kwargs):
        """Save the trade request without automatic matching to prevent admin hanging."""
        # Clean the model before saving
        self.clean()
        
        # Call the original save method
        super().save(*args, **kwargs)
        
        # Note: Automatic matching is disabled to prevent performance issues in admin.
        # Use the admin action "Find potential matches" or call find_potential_matches() manually.
    
    def __str__(self):
        teacher_str = str(self.requesting_teacher) if hasattr(self, 'requesting_teacher') and self.requesting_teacher else "Unknown Teacher"
        offered_str = str(self.offered_allocation) if hasattr(self, 'offered_allocation') and self.offered_allocation else "Unknown Allocation"
        
        if self.desired_allocation:
            return f"{teacher_str} wants to trade {offered_str} for {self.desired_allocation}"
        else:
            criteria = []
            if self.desired_day:
                criteria.append(f"day:{self.desired_day}")
            if self.desired_start_time:
                criteria.append(f"time:{self.desired_start_time}")
            if self.desired_duration:
                criteria.append(f"duration:{self.desired_duration}h")
            
            criteria_str = ", ".join(criteria) if criteria else "any suitable allocation"
            return f"{teacher_str} wants to trade {offered_str} for {criteria_str}"
    
    def is_expired(self):
        """Check if this trade request has expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def can_match_with(self, other_request):
        """
        Check if this trade request can be matched with another trade request.
        Returns True if they form a valid trade pair.
        """
        if not isinstance(other_request, TradeRequest):
            return False
        
        if self.status != 'OPEN' or other_request.status != 'OPEN':
            return False
        
        if self.requesting_teacher == other_request.requesting_teacher:
            return False
        
        # Skip teacher validation check here for performance - it's validated in clean() method
        # when the TradeRequest is created
        
        # Case 1: Both have specific desired allocations and they match cross-wise
        if (self.desired_allocation and other_request.desired_allocation and
            self.desired_allocation == other_request.offered_allocation and
            other_request.desired_allocation == self.offered_allocation):
            return True
        
        # Case 2: One has specific desired allocation, the other has criteria
        if self.desired_allocation == other_request.offered_allocation:
            return self._matches_criteria(other_request, self.offered_allocation)
        
        if other_request.desired_allocation == self.offered_allocation:
            return self._matches_criteria(self, other_request.offered_allocation)
        
        # Case 3: Both have criteria - check if they mutually satisfy
        if (not self.desired_allocation and not other_request.desired_allocation):
            return (self._matches_criteria(self, other_request.offered_allocation) and
                    self._matches_criteria(other_request, self.offered_allocation))
        
        return False
    
    def _matches_criteria(self, request, allocation):
        """Check if an allocation matches the criteria specified in a trade request."""
        if request.desired_day and allocation.day != request.desired_day:
            return False
        
        if request.desired_start_time and allocation.start != request.desired_start_time:
            return False
        
        if request.desired_duration and allocation.duration != request.desired_duration:
            return False
        
        return True
    
    def find_potential_matches(self):
        """Find all potential matching trade requests for this request."""
        # Use select_related and prefetch_related to avoid N+1 queries
        potential_matches = TradeRequest.objects.filter(
            status='OPEN'
        ).exclude(
            requesting_teacher=self.requesting_teacher
        ).exclude(
            id=self.id
        ).select_related(
            'requesting_teacher', 
            'offered_allocation__activityRealization',
            'desired_allocation__activityRealization'
        ).prefetch_related(
            'offered_allocation__activityRealization__teachers',
            'desired_allocation__activityRealization__teachers'
        )
        
        matches = []
        for request in potential_matches:
            if self.can_match_with(request):
                matches.append(request)
        
        return matches
    
    def auto_match(self):
        """
        Automatically match this trade request with the first suitable match found.
        Returns the created TradeMatch or None if no match found.
        """
        if self.status != 'OPEN':
            return None
        
        potential_matches = self.find_potential_matches()
        if potential_matches:
            return self.create_match(potential_matches[0])
        return None
    
    def create_match(self, other_request):
        """Create a match between this request and another request."""
        if not self.can_match_with(other_request):
            raise ValueError("Cannot match these trade requests")
        
        # Update both requests to matched status
        self.status = 'MATCHED'
        self.matched_with = other_request
        self.save()
        
        other_request.status = 'MATCHED'
        other_request.matched_with = self
        other_request.save()
        
        # Create a trade match record for approval queue
        trade_match = TradeMatch.objects.create(
            request_1=self,
            request_2=other_request,
            status='PENDING_APPROVAL'
        )
        
        return trade_match
    
    def reject_by_teacher(self, teacher, reason=""):
        """Reject this trade request by a teacher (before admin approval)."""
        if self.status != 'OPEN':
            raise ValueError("Can only reject open trade requests")
        
        self.status = 'REJECTED'
        self.teacher_rejected_by = teacher
        self.teacher_rejection_reason = reason
        self.approval_date = timezone.now()
        self.save()


class TradeMatch(models.Model):
    """
    Represents a matched pair of trade requests that are pending approval.
    """
    
    STATUS_CHOICES = [
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('EXECUTED', 'Executed'),
    ]
    
    request_1 = models.ForeignKey(
        TradeRequest,
        related_name='matches_as_request_1',
        on_delete=models.CASCADE
    )
    request_2 = models.ForeignKey(
        TradeRequest,
        related_name='matches_as_request_2',
        on_delete=models.CASCADE
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING_APPROVAL'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Approval details
    reviewed_by = models.ForeignKey(
        'Teacher',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Administrator who reviewed this match"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(
        blank=True,
        help_text="Notes from the reviewer"
    )
    
    # Execution details
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the trade was actually executed"
    )
    executed_by = models.ForeignKey(
        'Teacher',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='executed_trades',
        help_text="Who executed the trade"
    )
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['request_1', 'request_2']
    
    def __str__(self):
        return f"Trade Match: {self.request_1.requesting_teacher} ↔ {self.request_2.requesting_teacher}"
    
    def approve(self, reviewer, notes=""):
        """Approve this trade match and swap the allocations."""
        from django.db import transaction
        
        with transaction.atomic():
            # Swap the timeslots (day and start time only)
            alloc1 = self.request_1.offered_allocation
            alloc2 = self.request_2.offered_allocation
            
            # Store original timeslot info
            temp_day = alloc1.day
            temp_start = alloc1.start
            
            # Swap allocation 1 to allocation 2's timeslot
            alloc1.day = alloc2.day
            alloc1.start = alloc2.start
            alloc1.save()
            
            # Swap allocation 2 to allocation 1's original timeslot
            alloc2.day = temp_day
            alloc2.start = temp_start
            alloc2.save()
            
            # Update the trade match status
            self.status = 'APPROVED'
            self.reviewed_by = reviewer
            self.reviewed_at = timezone.now()
            self.review_notes = notes
            self.save()
            
            # Update the trade requests
            self.request_1.status = 'APPROVED'
            self.request_1.approved_by = reviewer
            self.request_1.approval_date = self.reviewed_at
            self.request_1.approval_notes = notes
            self.request_1.save()
            
            self.request_2.status = 'APPROVED'
            self.request_2.approved_by = reviewer
            self.request_2.approval_date = self.reviewed_at
            self.request_2.approval_notes = notes
            self.request_2.save()
    
    def reject(self, reviewer, notes=""):
        """Reject this trade match."""
        self.status = 'REJECTED'
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()
        
        # Mark the trade requests as rejected
        self.request_1.status = 'REJECTED'
        self.request_1.approved_by = reviewer
        self.request_1.approval_date = self.reviewed_at
        self.request_1.approval_notes = notes
        self.request_1.matched_with = None
        self.request_1.save()
        
        self.request_2.status = 'REJECTED'
        self.request_2.approved_by = reviewer
        self.request_2.approval_date = self.reviewed_at
        self.request_2.approval_notes = notes
        self.request_2.matched_with = None
        self.request_2.save()
    
    def execute_trade(self, executor):
        """Execute the approved trade by swapping the allocations."""
        if self.status != 'APPROVED':
            raise ValueError("Can only execute approved trades")
        
        # Swap the teachers on the allocations
        allocation_1 = self.request_1.offered_allocation
        allocation_2 = self.request_2.offered_allocation
        
        # Store the original teachers
        teachers_1 = list(allocation_1.activityRealization.teachers.all())
        teachers_2 = list(allocation_2.activityRealization.teachers.all())
        
        # Swap teachers between allocations
        allocation_1.activityRealization.teachers.clear()
        allocation_1.activityRealization.teachers.set(teachers_2)
        
        allocation_2.activityRealization.teachers.clear()
        allocation_2.activityRealization.teachers.set(teachers_1)
        
        # Update match status
        self.status = 'EXECUTED'
        self.executed_at = timezone.now()
        self.executed_by = executor
        self.save()
        
        # Update request statuses
        self.request_1.status = 'APPROVED'
        self.request_1.save()
        
        self.request_2.status = 'APPROVED'
        self.request_2.save()