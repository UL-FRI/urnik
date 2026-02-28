import json
import logging
from datetime import date, datetime, timedelta
from collections import OrderedDict, namedtuple

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.forms import formsets
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template import RequestContext
from django.utils import timezone
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView
from django.views.generic.list import ListView

from timetable.forms import (
    ActivityRequirementsFormset,
    GroupPreferenceForm,
    TeacherPreferenceForm,
    TradeRequestForm,
    TradeRequestSearchForm,
)
from timetable.models import (
    WEEKDAYS,
    WORKHOURS,
    Activity,
    Allocation,
    Classroom,
    Group,
    Teacher,
    Timetable,
)
from timetable.models.timetables import TradeRequest, TradeMatch

logger = logging.getLogger(__name__)


def index(request):
    params = {}
    return render(request, "timetable/index.html", params)


def results(request):
    class TimetableChoiceForm(forms.Form):
        timetable = forms.ModelMultipleChoiceField(
            Timetable.objects.all(), label="Urnik:"
        )

    params = {
        "timetable": TimetableChoiceForm,
        "teachers": Teacher.objects.filter().order_by(
            "user__first_name", "user__last_name"
        ),
        "classrooms": Classroom.objects.all(),
        "studyGroups": Group.objects.filter(parent=None),
    }
    return render(request, "timetable/results.html", params)


def timetable_preference_links(request):
    timetables = Timetable.objects.order_by("period.start").all()
    return render(
        request, "timetable/teacher_preference_links.html", {"timetables": timetables}
    )


def teacher_preference_links(request, timetable_id=None):
    teachers = Teacher.objects.order_by("surname", "name", "sifra").filter()
    return render(
        request,
        "timetable/teacher_preference_links.html",
        {"teachers": teachers, "timetable_id": timetable_id},
    )


def show_allocations(allocations):
    def first_free_index(integer_set):
        for i in range(len(integer_set)):
            if i not in integer_set:
                return i

    running_allocations = set()
    taken_indices = set()
    events = set(
        [(allocation.start, "start", allocation) for allocation in allocations]
        + [(allocation.end, "end", allocation) for allocation in allocations]
    )
    for hour, event_type, allocation in sorted(events):
        if event_type == "start":
            running_allocations.append(allocation)
            index = first_free_index(taken_indices)
            taken_indices.add(index)
            allocation.index = allocation.max_index = index
        else:
            running_allocations.remove(allocation)
            taken_indices.remove(allocation.index)
            for allocation in running_allocations:
                allocation.max_index = max(allocation.max_index, allocation.index)
    return allocations


def allocations(request):
    allocations_by_hour = OrderedDict()
    filtered_allocations = Allocation.objects.filter()
    timetable = None
    r = request.REQUEST
    teacher = None
    classroom = None
    activity = None
    group = None
    if "timetable" in r:
        timetable = Timetable.objects.get(id=r["timetable"])
        filtered_allocations = filtered_allocations.filter(timetable=timetable)
    if "teacher" in r:
        teacher = Teacher.objects.get(id=r["teacher"])
        filtered_allocations = filtered_allocations.filter(
            activityRealization__teachers__exact=teacher
        )
    if "classroom" in r:
        classroom = Classroom.objects.get(id=r["classroom"])
        filtered_allocations = filtered_allocations.filter(classroom=classroom)
    if "activity" in r:
        activity = Activity.objects.get(id=r["activity"])
        filtered_allocations = filtered_allocations.filter(activity__activity=activity)
    groups_listed = [None]
    if "group" in r:
        group = Group.objects.get(id=r["group"])
        groups_listed = group.children() + [group]

    # Limit the number of allocations in response to MAX_ALLOCATIONS
    filters = ["timetable", "teacher", "classroom", "activity", "group"]
    if not any([filter in r for filter in filters]):
        # Request is not filtered
        # Limit response to 10 allocations
        MAX_ALLOCATIONS = 10
        filtered_allocations = filtered_allocations[:MAX_ALLOCATIONS]

    max_overlaps_day = []
    whdict = dict([(WORKHOURS[i][0], i) for i in range(len(WORKHOURS))])
    for hour in [i[0] for i in WORKHOURS]:
        allocations_by_hour[hour] = [[] for j in WEEKDAYS]
    space_taken_list = []
    Span = namedtuple("Span", ["start", "duration", "w", "action"])
    for day in range(len(WEEKDAYS)):
        # create the set of all activities for this day
        sa = set()
        for g in groups_listed:
            fa = filtered_allocations.filter(day=WEEKDAYS[day][0])
            if g is not None:
                fa = fa.filter(activity__studyGroups__exact=g.id)
            for a in fa:
                if a not in sa:
                    sa.add(a)
        allocation_tab = []
        start_hours = []
        for a in sorted(sa, key=lambda x: whdict[x.start]):
            placed = False
            j = 0
            while (j < len(allocation_tab)) and not placed:
                last = allocation_tab[j][-1]
                last_end = last.start + last.duration
                new_start = whdict[a.start]
                if last_end <= new_start:
                    new_pre_last_duration = new_start - last_end
                    if new_pre_last_duration > 0:
                        allocation_tab[j].append(
                            Span(
                                start=last_end,
                                duration=new_pre_last_duration,
                                w=1,
                                action=None,
                            )
                        )
                    allocation_tab[j].append(
                        Span(start=new_start, duration=a.duration, w=1, action=a)
                    )
                    placed = True
                j += 1
            if not placed:
                l = [Span(start=whdict[a.start], duration=a.duration, w=1, action=a)]
                start_hours.append(whdict[a.start])
                allocation_tab.append(l)
        # expand the allocations and empty spaces
        # insert the heading and trailing empty spaces
        prev_duration = None
        # print start_hours
        if len(allocation_tab) < 1:
            allocation_tab = [[Span(start=0, duration=len(whdict), w=1, action=None)]]
        else:
            to_set = None
            for i, l in enumerate(allocation_tab):
                if start_hours[i] > 0:
                    l.insert(
                        0, Span(start=0, duration=start_hours[i], w=1, action=None)
                    )
                last = l[-1]
                duration = len(whdict) - (last.start + last.duration)
                if duration > 0:
                    if prev_duration == duration:
                        # print to_set, l
                        s = allocation_tab[to_set][-1]
                        allocation_tab[to_set][-1] = Span(
                            start=s.start, duration=s.duration, w=s.w + 1, action=None
                        )
                    else:
                        s = Span(
                            start=last.start + last.duration,
                            duration=duration,
                            w=1,
                            action=None,
                        )
                        l.append(s)
                        to_set = i
                prev_duration = duration
        # insert allocations from allocation_tab into allocations_by_hour
        for l in allocation_tab:
            for j in l:
                allocations_by_hour[WORKHOURS[j.start][0]][day].append(
                    (j.w, j.duration, j.action)
                )
        space_taken_list.append(allocation_tab)
        max_overlaps_day.append(len(allocation_tab))
    daynames = {
        "MON": "Ponedeljek",
        "TUE": "Torek",
        "WED": "Sreda",
        "THU": "Četrtek",
        "FRI": "Petek",
    }
    day_header = []
    for day in range(len(WEEKDAYS)):
        day_header.append((daynames[WEEKDAYS[day][0]], max_overlaps_day[day]))
    return render(
        request,
        "timetable/allocations.html",
        {
            "timetable": timetable,
            "teacher": teacher,
            "classroom": classroom,
            "activity": activity,
            "group": group,
            "day_header": day_header,
            "allocations_by_hour": allocations_by_hour.iteritems(),
        },
    )


@login_required
def activity_requirements(request):
    try:
        teacher = request.user.teacher
    except ObjectDoesNotExist:
        teacher = None
    if request.method == "POST":
        complete_formset = ActivityRequirementsFormset(
            request.POST, request.FILES, prefix="cmplt-"
        )
        if complete_formset.is_valid():
            complete_formset.save()
        user_formset = ActivityRequirementsFormset(
            request.POST, request.FILES, prefix="usr-"
        )
        if user_formset.is_valid():
            user_formset.save()
    complete_formset = ActivityRequirementsFormset(
        prefix="cmplt-", queryset=Activity.objects.only("id", "requirements")
    )
    if teacher is not None:
        l = []
        activities = teacher.activities.all()
        for a in activities:
            l += a.groups.values_list("id", flat=True)
        qs = Group.objects.filter(id__in=l)

        class AFForm(forms.ModelForm):
            groups = forms.ModelMultipleChoiceField(queryset=qs)

            class Meta:
                model = Activity

        AFS = forms.models.modelformset_factory(
            Activity, form=ActivityRequirementForm, extra=0, max_num=5, can_delete=False
        )
        user_formset = AFS(
            queryset=teacher.activities.only("id", "requirements"),
            initial=[{}] * len(activities) + [{"teachers": [teacher]}],
            prefix="usr-",
        )
    else:
        user_formset = ActivityRequirementsFormset(prefix="usr-")
    return render(
        request,
        "timetable/activity_requirements.html",
        {
            "user_formset": user_formset,
            "complete_formset": complete_formset,
            "teacher": teacher,
        },
        context_instance=RequestContext(request),
    )


@login_required
def teacher_single_preferences_DEPRECATED(request, timetable_id=None):
    # DEPRECATED: This view is no longer used. Democratic preferences are used via friprosveta app.
    # Keeping this function to avoid breaking any old references, but it should not be called.
    try:
        teacher = request.user.teacher
        timetable = Timetable.objects.get(id=int(timetable_id))
    except:
        raise Http404
    activities = teacher.activities.all()
    pset = timetable.preferences
    problems = False
    if request.method == "POST":
        preference_form = TeacherPreferenceForm(request.POST, prefix="pref-")
        actreq_formset = ActivityRequirementsFormset(
            request.POST, request.FILES, prefix="actreq-"
        )
        preference_form.full_clean()
        actreq_formset.full_clean()
        if preference_form.is_valid():
            preference_form.save()
            logger.debug("is actreq valid?")
            if actreq_formset.is_valid():
                logger.debug("    YES!")
                try:
                    actreq_formset.save()
                except ValueError as e:
                    logger.warn("  Problem saving activity requirements" + str(e))
                    # print str(actreq_formset)
                    problems = True
                    activities = teacher.activities.all()
            else:
                logger.debug("    NO!")
                problems = True
    if not problems:
        actreq_formset = ActivityRequirementsFormset(
            queryset=activities,
            initial=[{}] * len(activities) + [{"teachers": [teacher]}],
            prefix="actreq-",
        )
        preference_form = TeacherPreferenceForm(
            teacher=teacher, preferenceset=pset, prefix="pref-"
        )
    return render(
        request,
        "timetable/teacher_single_preferences.html",
        {
            "form": preference_form,
            "activity_requirement_formset": actreq_formset,
        },
        context_instance=RequestContext(request),
    )


@login_required
def all_teacher_preferences(request):
    r = request.REQUEST
    teachers = Teacher.objects.filter()
    if "teacher" in r:
        teachers = teachers.filter(id=r["teacher"])
    preference_forms_by_period_teacher = {}
    #            preference_forms_by_period_teacher[p][t] = preference_forms_by_time(r, t, p)
    # restored_preferences = []
    if request.method == "POST":
        # formset = TeacherPreferenceFormSet(request.POST)
        management_form = formsets.ManagementForm(request.POST)
        # if formset.is_valid():
        #    formset.save()
        if management_form.is_valid():
            for i in range(management_form.cleaned_data["TOTAL_FORMS"]):
                tpform = TeacherPreferenceForm(
                    request.POST, prefix="ttpref-{0}".format(i)
                )
                teacher = tpform.teacher()
                period = tpform.period()
                if period not in preference_forms_by_period_teacher:
                    preference_forms_by_period_teacher[period] = {}
                preference_forms_by_period_teacher[period][teacher] = tpform
                tpform.save()
    else:
        nforms = 0
        preference_forms_by_period_teacher[p] = {}
        for t in teachers:
            preference_forms_by_period_teacher[p][t] = TeacherPreferenceForm(
                prefix="ttpref-{0}".format(nforms), teacher=t, period=p
            )
            nforms += 1
        #    formset = TeacherPreferenceFormSet(queryset=TeacherPreference.objects.all())
        management_form = formsets.ManagementForm(
            initial={
                "INITIAL_FORMS": nforms,
                "MAX_NUM_FORMS": nforms,
                "TOTAL_FORMS": nforms,
            }
        )
        # restored_preferences = TeacherPreference.objects.all()
    return render(
        request,
        "timetable/teacher_formset_preferences.html",
        {
            "teachers": teachers,
            "periods": periods,
            "WORKHOURS": WORKHOURS,
            "WEEKDAYS": WEEKDAYS,
            "management_form": management_form,
            "period_preference_forms": preference_forms_by_period_teacher.iteritems(),
        },
        context_instance=RequestContext(request),
    )


@login_required
def group_overview(request):
    return render(
        request,
        "friprosveta/group_overview.html",
        {"object_list": visible_timetables(request)},
        context_instance=RequestContext(request),
    )


def group_preference_list(request, timetable_id=None):
    if timetable_id is not None:
        t = Timetable.objects.get(id=timetable_id)
        if timetable_visible(request, t):
            q = t.groups
        else:
            q = Group.objects.none()
    else:
        q = Group.objects.all()
    return ListView(
        request,
        queryset=q,
        template_name="friprosveta/group_list.html",
    ).as_view()


@login_required
def group_single_preferences(request, group_id=None, timetable_id=None):
    try:
        group = Group.objects.get(id=int(group_id))
        timetable = Timetable.objects.get(id=int(timetable_id))
        if not timetable_visible(request, timetable):
            raise Http404
    except Exception as e:
        logger.warn(e)
        raise Http404
    pset = timetable.preferences
    problems = False
    got_post = False
    if request.method == "POST":
        preference_form = GroupPreferenceForm(request.POST, prefix="pref-")
        preference_form.full_clean()
        if preference_form.is_valid() and (
            not preference_form.preferenceset().locked or request.user.is_staff
        ):
            preference_form.save()
        else:
            problems = True
    if not problems:
        preference_form = GroupPreferenceForm(
            group=group, preferenceset=pset, prefix="pref-"
        )
    return render(
        request,
        "friprosveta/group_preferences.html",
        {
            "form": preference_form,
            "got_post": got_post,
        },
        context_instance=RequestContext(request),
    )


class ActivityDetailView(DetailView):
    model = Activity


class ActivityUpdateView(UpdateView):
    model = Activity


# Trade Request Views
@login_required
def trade_request_list(request, timetable_slug=None):
    """List all trade requests with optional filtering."""
    if not request.user.is_staff:
        messages.error(request, "You don't have permission to view all trade requests.")
        if timetable_slug:
            return redirect('my_trade_requests', timetable_slug=timetable_slug)
        return redirect('my_trade_requests')
    
    # Get timetable if slug provided
    timetable = None
    if timetable_slug:
        timetable = get_object_or_404(Timetable, slug=timetable_slug)
    
    # Check if trading is disabled
    if timetable and not timetable.trading_enabled:
        return render(request, 'timetable/trade_requests/trading_disabled.html', {
            'timetable': timetable,
            'timetable_slug': timetable_slug,
        })
    
    form = TradeRequestSearchForm(request.GET)
    trade_requests = TradeRequest.objects.select_related(
        'requesting_teacher__user',
        'offered_allocation__activityRealization__activity',
        'offered_allocation__classroom',
        'original_offered_classroom',
        'original_desired_allocation',
        'original_desired_classroom',
        'desired_allocation__activityRealization__activity',
        'desired_allocation__classroom',
        'matched_with'
    ).prefetch_related(
        'offered_allocation__activityRealization__teachers',
        'desired_allocation__activityRealization__teachers'
    )
    
    # Filter by timetable if provided
    if timetable:
        trade_requests = trade_requests.filter(
            offered_allocation__timetable=timetable
        )
    
    # Apply filters BEFORE slicing
    if form.is_valid():
        if form.cleaned_data['status']:
            trade_requests = trade_requests.filter(status=form.cleaned_data['status'])
        
        if form.cleaned_data['teacher']:
            trade_requests = trade_requests.filter(requesting_teacher=form.cleaned_data['teacher'])
        
        if form.cleaned_data['day']:
            trade_requests = trade_requests.filter(
                models.Q(offered_allocation__day=form.cleaned_data['day']) |
                models.Q(desired_allocation__day=form.cleaned_data['day']) |
                models.Q(desired_day=form.cleaned_data['day'])
            )
        
        if form.cleaned_data['search']:
            search_term = form.cleaned_data['search']
            trade_requests = trade_requests.filter(
                models.Q(offered_allocation__activityRealization__activity__name__icontains=search_term) |
                models.Q(desired_allocation__activityRealization__activity__name__icontains=search_term) |
                models.Q(reason__icontains=search_term)
            )
        
        if form.cleaned_data.get('relevant_to_me') and hasattr(request.user, 'teacher'):
            # Show requests where the desired allocation is taught by the current user
            teacher = request.user.teacher
            trade_requests = trade_requests.filter(
                models.Q(desired_allocation__activityRealization__teachers=teacher) |
                models.Q(desired_allocation__isnull=True)  # Include flexible requests
            ).exclude(requesting_teacher=teacher)  # Don't show my own requests
    
    # Limit to recent requests for performance (MUST be last)
    trade_requests = trade_requests.order_by('-created_at')[:100]
    
    return render(request, 'timetable/trade_requests/list.html', {
        'trade_requests': trade_requests,
        'form': form,
        'timetable_slug': timetable_slug,
    })


@login_required
def my_trade_requests(request, timetable_slug=None):
    """List the current user's trade requests and requests relevant to them."""
    try:
        teacher = request.user.teacher
    except AttributeError:
        # Debug: Check if user exists but doesn't have teacher relationship
        return render(request, 'timetable/trade_requests/no_teacher.html', {
            'debug_info': {
                'user': request.user,
                'user_id': request.user.id,
                'is_authenticated': request.user.is_authenticated,
                'has_teacher': hasattr(request.user, 'teacher'),
            }
        })
    
    # Get timetable if slug provided
    timetable = None
    if timetable_slug:
        timetable = get_object_or_404(Timetable, slug=timetable_slug)
    
    # Check if trading is disabled
    if timetable and not timetable.trading_enabled:
        return render(request, 'timetable/trade_requests/trading_disabled.html', {
            'timetable': timetable,
            'timetable_slug': timetable_slug,
        })
    
    # My requests (requests I created)
    my_requests = TradeRequest.objects.filter(
        requesting_teacher=teacher
    ).select_related(
        'offered_allocation__activityRealization__activity',
        'offered_allocation__classroom',
        'desired_allocation__activityRealization__activity',
        'desired_allocation__classroom',
        'matched_with'
    ).order_by('-created_at')
    
    # Requests relevant to me (where I teach what they want)
    relevant_requests = TradeRequest.objects.filter(
        models.Q(desired_allocation__activityRealization__teachers=teacher) |  # They want a specific slot I teach
        models.Q(desired_allocation__isnull=True)  # Include flexible requests
    ).exclude(
        requesting_teacher=teacher  # Exclude my own requests
    ).filter(
        status='OPEN'  # Only show open requests (not matched/accepted yet)
    ).select_related(
        'offered_allocation__activityRealization__activity',
        'offered_allocation__classroom',
        'desired_allocation__activityRealization__activity',
        'desired_allocation__classroom',
        'requesting_teacher__user',
        'matched_with'
    ).order_by('-created_at')
    
    # Requests directed at me (where I teach what they're offering)
    directed_at_me = TradeRequest.objects.filter(
        offered_allocation__activityRealization__teachers=teacher,
        status='OPEN'
    ).exclude(
        requesting_teacher=teacher  # Exclude my own requests
    ).select_related(
        'offered_allocation__activityRealization__activity',
        'offered_allocation__classroom',
        'desired_allocation__activityRealization__activity',
        'desired_allocation__classroom',
        'requesting_teacher__user',
        'matched_with'
    ).order_by('-created_at')
    
    # Filter by timetable if provided
    if timetable:
        my_requests = my_requests.filter(offered_allocation__timetable=timetable)
        relevant_requests = relevant_requests.filter(offered_allocation__timetable=timetable)
        directed_at_me = directed_at_me.filter(offered_allocation__timetable=timetable)
    
    # For each relevant flexible request, add a list of all overlapping allocations for this teacher
    from datetime import datetime, timedelta, date
    relevant_requests = list(relevant_requests)
    for req in relevant_requests:
        req.overlapping_allocations = []
        if req.desired_allocation is None:
            # Only show overlaps if flexible request has criteria
            from timetable.models import Allocation
            teacher_allocs = Allocation.objects.filter(activityRealization__teachers=teacher)
            if req.desired_day and req.desired_start_time and req.desired_duration:
                # Calculate request's time range as datetime objects
                from datetime import datetime, timedelta
                req_start_dt = datetime.combine(datetime.today(), datetime.strptime(req.desired_start_time, "%H:%M").time())
                req_end_dt = req_start_dt + timedelta(hours=req.desired_duration)
                for alloc in teacher_allocs:
                    alloc_start_dt = datetime.combine(datetime.today(), datetime.strptime(alloc.start, "%H:%M").time())
                    # Use Allocation's end property for correct end time
                    if hasattr(alloc, 'end'):
                        alloc_end_str = alloc.end
                        alloc_end_dt = datetime.combine(datetime.today(), datetime.strptime(alloc_end_str, "%H:%M").time())
                    else:
                        alloc_end_dt = alloc_start_dt + timedelta(hours=alloc.duration)
                    if alloc.day == req.desired_day and (req_start_dt < alloc_end_dt and req_end_dt > alloc_start_dt):
                        req.overlapping_allocations.append(alloc)
            # If no criteria, do not show any overlaps
    return render(request, 'timetable/trade_requests/my_requests.html', {
        'my_requests': my_requests,
        'relevant_requests': relevant_requests,
        'directed_at_me': directed_at_me,
        'teacher': teacher,
        'timetable': timetable if timetable_slug else None,
        'timetable_slug': timetable_slug,
    })


@login_required
def create_trade_request(request, timetable_slug=None):
    """Create a new trade request."""
    try:
        teacher = request.user.teacher
    except AttributeError:
        messages.error(request, "You need to be registered as a teacher to create trade requests.")
        return render(request, 'timetable/trade_requests/no_teacher.html', {
            'timetable_slug': timetable_slug,
        })
    
    # Get timetable if slug provided
    timetable = None
    if timetable_slug:
        timetable = get_object_or_404(Timetable, slug=timetable_slug)
    
    # Check for pre-selected values from URL parameters
    offered_allocation_id = request.GET.get('offered_allocation')
    desired_day = request.GET.get('desired_day')
    desired_start_time = request.GET.get('desired_start_time')
    initial_data = {}
    
    if offered_allocation_id:
        try:
            from timetable.models import Allocation
            offered_allocation = Allocation.objects.get(
                id=offered_allocation_id,
                activityRealization__teachers=teacher
            )
            initial_data['offered_allocation'] = offered_allocation
            messages.info(request, f'Pre-selected time slot to trade: {offered_allocation.get_day_display()} {offered_allocation.start}')
        except (Allocation.DoesNotExist, ValueError):
            messages.warning(request, 'The selected time slot is not valid or you do not teach it.')
    
    if desired_day:
        initial_data['desired_day'] = desired_day
        
    if desired_start_time:
        initial_data['desired_start_time'] = desired_start_time
        
    if desired_day or desired_start_time:
        day_str = dict(WEEKDAYS).get(desired_day, desired_day) if desired_day else "any day"
        time_str = desired_start_time if desired_start_time else "any time"
        messages.info(request, f'Target time slot preference: {day_str} at {time_str}')
    
    if request.method == 'POST':
        form = TradeRequestForm(request.POST, teacher=teacher, timetable=timetable, initial=initial_data)
        if form.is_valid():
            # Additional check for duplicate active requests (belt and suspenders approach)
            offered_alloc = form.cleaned_data.get('offered_allocation')
            if offered_alloc:
                # Only OPEN and PENDING_APPROVAL are considered blocking statuses
                active_statuses = ['OPEN', 'PENDING_APPROVAL']
                existing_requests = TradeRequest.objects.filter(
                    requesting_teacher=teacher,
                    offered_allocation=offered_alloc,
                    status__in=active_statuses
                )
                
                if existing_requests.exists():
                    existing = existing_requests.first()
                    messages.error(
                        request, 
                        f'You already have an active trade request ({existing.get_status_display()}) '
                        f'for this time slot. Please cancel or complete it before creating a new one.'
                    )
                    return render(request, 'timetable/trade_requests/create.html', {
                        'form': form,
                        'timetable_slug': timetable_slug,
                        'teacher_allocations_json': teacher_allocs_json,
                        'other_allocations_json': other_allocs_json,
                    })
            
            trade_request = form.save(commit=False)
            trade_request.requesting_teacher = teacher
            
            # Check if the desired time slot is free (info added by form validation)
            if form.cleaned_data.get('_slot_is_free'):
                # Automatically move to pending approval since no swap is needed
                trade_request.status = 'PENDING_APPROVAL'
                slot_desc = form.cleaned_data.get('_free_slot_description', 'your desired time')
                trade_request.save()
                messages.success(
                    request, 
                    f'✅ Trade request created and sent for admin approval! Good news: {slot_desc} appears to be free - '
                    f'your class can be moved there without requiring a swap. Waiting for administrator approval.'
                )
            else:
                # Keep as OPEN status - needs matching with another teacher
                trade_request.save()
                # Automatic matching disabled for performance - use admin actions instead
                messages.success(request, 'Trade request created successfully! Use the admin interface to find and approve matches.')
            
            if timetable_slug:
                return redirect('my_trade_requests', timetable_slug=timetable_slug)
            else:
                return redirect('my_trade_requests')
    else:
        form = TradeRequestForm(teacher=teacher, timetable=timetable, initial=initial_data)
    
    # Prepare allocations data for visual selector
    from timetable.models import Allocation
    import json
    
    # Get teacher's allocations
    teacher_allocations = Allocation.objects.filter(
        activityRealization__teachers=teacher
    ).select_related(
        'activityRealization__activity',
        'classroom',
        'timetable'
    )
    if timetable:
        teacher_allocations = teacher_allocations.filter(timetable=timetable)
    
    # Get all other allocations (potential trades)
    other_allocations = Allocation.objects.exclude(
        activityRealization__teachers=teacher
    ).select_related(
        'activityRealization__activity',
        'classroom',
        'timetable'
    )
    if timetable:
        other_allocations = other_allocations.filter(timetable=timetable)
    
    # Convert to JSON-serializable format
    preferred_rooms_cache = {}
    def allocation_to_dict(alloc):
        cache_key = (alloc.activityRealization_id, alloc.timetable_id)
        if cache_key in preferred_rooms_cache:
            preferred_classroom_ids = preferred_rooms_cache[cache_key]
        else:
            preferred_rooms = alloc.activityRealization.preferred_rooms(
                timetable=alloc.timetable
            )
            preferred_classroom_ids = list(
                preferred_rooms.values_list('id', flat=True)
            )
            preferred_rooms_cache[cache_key] = preferred_classroom_ids

        size = alloc.activityRealization.size
        min_capacity = max(size - 15, 0) if size is not None else 0

        # Get teacher names with full first and last name
        teacher_names = []
        for t in alloc.activityRealization.teachers.all():
            if t.user:
                full_name = f"{t.user.last_name}, {t.user.first_name}"
                teacher_names.append(full_name)
            else:
                teacher_names.append(str(t))
        
        return {
            'id': alloc.id,
            'day': alloc.day,
            'start': alloc.start,
            'duration': alloc.duration,
            'activity': alloc.activityRealization.activity.name,
            'classroom': str(alloc.classroom),
            'teachers': ' | '.join(teacher_names),  # Use | as separator instead of comma
            'timetable_id': alloc.timetable_id,
            'timetable_slug': alloc.timetable.slug,
            'preferred_classroom_ids': preferred_classroom_ids,
            'min_capacity': min_capacity,
        }
    
    teacher_allocs_json = json.dumps([allocation_to_dict(a) for a in teacher_allocations])
    other_allocs_json = json.dumps([allocation_to_dict(a) for a in other_allocations])
    
    # Get unique teachers from other allocations with their allocation counts
    teachers_dict = {}
    for alloc in other_allocations:
        for t in alloc.activityRealization.teachers.all():
            if t.user:
                full_name = f"{t.user.last_name}, {t.user.first_name}"
            else:
                full_name = str(t)
            
            if full_name not in teachers_dict:
                teachers_dict[full_name] = 0
            teachers_dict[full_name] += 1
    
    # Sort teachers alphabetically
    teachers_list = [{'name': name, 'count': count} for name, count in sorted(teachers_dict.items())]
    teachers_json = json.dumps(teachers_list)

    # Build free (empty) slots for the teacher's timetables
    from timetable.models.constants import WEEKDAYS, WORKHOURS

    def build_free_slots_for_timetable(target_timetable, durations):
        workhour_values = [hour[0] for hour in WORKHOURS]
        allocations = Allocation.objects.filter(
            timetable=target_timetable
        ).select_related('classroom')

        occupied = {}
        for alloc in allocations:
            if not alloc.classroom_id:
                continue
            key = (alloc.classroom_id, alloc.day)
            if key not in occupied:
                occupied[key] = set()
            occupied[key].update(alloc.hours)

        free_slots = []
        from timetable.models import Classroom
        classroom_ids = set(allocations.values_list('classroom_id', flat=True).distinct())
        classroom_ids.discard(None)
        if hasattr(target_timetable, 'classroomset') and target_timetable.classroomset_id:
            classroom_ids.update(target_timetable.classroomset.classrooms.values_list('id', flat=True))
        classrooms = Classroom.objects.filter(id__in=classroom_ids).order_by('name')

        for classroom in classrooms:
            for day_code, _day_label in WEEKDAYS:
                occupied_hours = occupied.get((classroom.id, day_code), set())
                for duration in durations:
                    if not duration:
                        continue
                    max_start_index = len(workhour_values) - duration
                    for i in range(0, max_start_index + 1):
                        slot_hours = workhour_values[i : i + duration]
                        if occupied_hours.intersection(slot_hours):
                            continue
                        free_slots.append(
                            {
                                'day': day_code,
                                'start': workhour_values[i],
                                'duration': duration,
                                'classroom_id': classroom.id,
                                'classroom': str(classroom),
                                'classroom_capacity': classroom.capacity,
                                'timetable_id': target_timetable.id,
                                'timetable_slug': target_timetable.slug,
                                'timetable_name': target_timetable.name,
                            }
                        )

        return free_slots

    timetables = [timetable] if timetable else list({alloc.timetable for alloc in teacher_allocations})
    duration_set = sorted({alloc.duration for alloc in teacher_allocations if alloc.duration})
    active_statuses = ['OPEN', 'PENDING_APPROVAL']
    requested_free_slots = TradeRequest.objects.filter(
        status__in=active_statuses,
        desired_allocation__isnull=True,
        desired_day__isnull=False,
        desired_start_time__isnull=False,
        desired_duration__isnull=False,
        desired_classroom__isnull=False,
        offered_allocation__timetable__in=timetables,
    ).select_related('desired_classroom', 'offered_allocation__timetable')

    requested_slot_keys = {
        (
            req.desired_day,
            req.desired_start_time,
            req.desired_duration,
            req.desired_classroom_id,
            req.offered_allocation.timetable_id,
        )
        for req in requested_free_slots
    }

    free_slots = []
    for tt in timetables:
        free_slots.extend(build_free_slots_for_timetable(tt, duration_set))

    for slot in free_slots:
        slot_key = (
            slot['day'],
            slot['start'],
            slot['duration'],
            slot['classroom_id'],
            slot['timetable_id'],
        )
        slot['is_requested'] = slot_key in requested_slot_keys
    free_slots_json = json.dumps(free_slots)
    
    return render(request, 'timetable/trade_requests/create.html', {
        'form': form,
        'teacher': teacher,
        'timetable_slug': timetable_slug,
        'teacher_allocations_json': teacher_allocs_json,
        'other_allocations_json': other_allocs_json,
        'teachers_json': teachers_json,
        'free_slots_json': free_slots_json,
    })


@login_required
def trade_request_allocation_stats(request, timetable_slug=None):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    allocation_ids = payload.get('allocation_ids', [])
    if not isinstance(allocation_ids, list):
        return JsonResponse({'error': 'Invalid allocation_ids'}, status=400)

    ids = []
    for allocation_id in allocation_ids:
        try:
            ids.append(int(allocation_id))
        except (TypeError, ValueError):
            continue

    if not ids:
        return JsonResponse({'stats': {}})

    allocations = Allocation.objects.filter(id__in=ids).select_related(
        'activityRealization',
        'timetable'
    )

    from friprosveta import models as friprosveta_models

    stats = {}
    busy_cache = {}
    for allocation in allocations:
        realization = allocation.activityRealization
        n_students = realization.size or 0

        students = friprosveta_models.Student.objects.filter(
            groups__realizations=realization
        ).distinct()

        overlap_count = 0
        for student in students:
            cache_key = (student.id, allocation.timetable_id)
            busy_hours = busy_cache.get(cache_key)
            if busy_hours is None:
                busy_hours = student.busy_hours(allocation.timetable)
                busy_cache[cache_key] = busy_hours

            overlaps = student.overlaps(allocation.timetable, busy_hours)
            has_overlap = any(
                day == allocation.day
                and hour in allocation.hours
                and any(slot_alloc.id == allocation.id for slot_alloc in slot_allocs)
                for day, hour, slot_allocs in overlaps
            )

            if has_overlap:
                overlap_count += 1

        stats[str(allocation.id)] = {
            'n_students': n_students,
            'total_overlaps': overlap_count,
        }

    return JsonResponse({'stats': stats})


@login_required
def trade_request_free_slot_stats(request, timetable_slug=None):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    offered_allocation_id = payload.get('offered_allocation_id')
    slot = payload.get('slot')
    if not offered_allocation_id or not isinstance(slot, dict):
        return JsonResponse({'error': 'Invalid payload'}, status=400)

    try:
        offered_allocation_id = int(offered_allocation_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid offered_allocation_id'}, status=400)

    day = slot.get('day')
    start = slot.get('start')
    duration = slot.get('duration')
    if not day or not start or not duration:
        return JsonResponse({'error': 'Invalid slot'}, status=400)

    try:
        duration = int(duration)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid slot duration'}, status=400)

    offered_allocation = Allocation.objects.select_related(
        'activityRealization',
        'timetable'
    ).filter(id=offered_allocation_id).first()

    if not offered_allocation:
        return JsonResponse({'error': 'Allocation not found'}, status=404)

    if timetable_slug and offered_allocation.timetable.slug != timetable_slug:
        return JsonResponse({'error': 'Allocation not in timetable'}, status=400)

    from timetable.models.constants import WORKHOURS
    workhour_values = [hour[0] for hour in WORKHOURS]
    if start not in workhour_values:
        return JsonResponse({'error': 'Invalid slot start'}, status=400)

    start_index = workhour_values.index(start)
    slot_hours = workhour_values[start_index : start_index + duration]
    if len(slot_hours) != duration:
        return JsonResponse({'error': 'Invalid slot range'}, status=400)

    from friprosveta import models as friprosveta_models

    realization = offered_allocation.activityRealization
    n_students = realization.size or 0

    students = friprosveta_models.Student.objects.filter(
        groups__realizations=realization
    ).distinct()

    busy_cache = {}
    overlap_count = 0
    for student in students:
        cache_key = (student.id, offered_allocation.timetable_id)
        busy_hours = busy_cache.get(cache_key)
        if busy_hours is None:
            busy_hours = student.busy_hours(offered_allocation.timetable)
            busy_cache[cache_key] = busy_hours

        has_overlap = False
        for hour in slot_hours:
            allocations_in_slot = busy_hours.get((day, hour), [])
            if any(slot_alloc.id != offered_allocation.id for slot_alloc in allocations_in_slot):
                has_overlap = True
                break

        if has_overlap:
            overlap_count += 1

    return JsonResponse({
        'stats': {
            'n_students': n_students,
            'total_overlaps': overlap_count,
        }
    })


@login_required
def trade_request_detail(request, pk, timetable_slug=None):
    """View details of a specific trade request."""

    trade_request = get_object_or_404(
        TradeRequest.objects.select_related(
            'requesting_teacher__user',
            'offered_allocation__activityRealization__activity',
            'offered_allocation__classroom',
            'original_offered_classroom',
            'original_desired_allocation',
            'original_desired_classroom',
            'desired_allocation__activityRealization__activity',
            'desired_allocation__classroom',
            'matched_with',
            'approved_by__user'
        ),
        pk=pk
    )
    
    # Check if user can view this request
    can_view = (
        request.user.is_staff or 
        (hasattr(request.user, 'teacher') and request.user.teacher == trade_request.requesting_teacher)
    )
    
    if not can_view:
        messages.error(request, "You don't have permission to view this trade request.")
        timetable_slug = trade_request.offered_allocation.timetable.slug
        return redirect('trade_request_list', timetable_slug=timetable_slug)
    
    # Find potential matches if the request is open
    potential_matches = []
    if trade_request.status == 'OPEN':
        potential_matches = trade_request.find_potential_matches()
    
    return render(request, 'timetable/trade_requests/detail.html', {
        'trade_request': trade_request,
        'potential_matches': potential_matches,
        'timetable_slug': timetable_slug,
    })


@login_required
def cancel_trade_request(request, pk, timetable_slug=None):
    """Cancel a trade request."""
    
    trade_request = get_object_or_404(TradeRequest, pk=pk)
    
    # Check if user can cancel this request
    if not (hasattr(request.user, 'teacher') and request.user.teacher == trade_request.requesting_teacher):
        messages.error(request, "You can only cancel your own trade requests.")
        fallback_slug = trade_request.offered_allocation.timetable.slug
        return redirect('trade_request_list', timetable_slug=timetable_slug or fallback_slug)
    
    if trade_request.status not in ['OPEN', 'MATCHED', 'PENDING_APPROVAL']:
        messages.error(request, "You can only cancel open, matched, or pending approval trade requests.")
        if timetable_slug:
            return redirect('my_trade_requests', timetable_slug=timetable_slug)
        else:
            return redirect('my_trade_requests')
    
    # Cancel the trade request directly without confirmation page
    trade_request.status = 'CANCELLED'
    trade_request.save()
    
    # If it was matched, also reset the matched request
    if trade_request.matched_with:
        matched_request = trade_request.matched_with
        matched_request.status = 'OPEN'
        matched_request.matched_with = None
        matched_request.save()
        messages.success(request, 'Trade request cancelled successfully. The matched request has been reopened.')
    else:
        messages.success(request, 'Trade request cancelled successfully.')
    
    # Redirect back to the referring page or default to my_trade_requests
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    elif timetable_slug:
        return redirect('my_trade_requests', timetable_slug=timetable_slug)
    else:
        return redirect('my_trade_requests')


@login_required
@transaction.atomic
def respond_to_trade_request(request, pk, timetable_slug=None):
    """Create a counter trade request to respond to an existing request."""
    try:
        teacher = request.user.teacher
    except AttributeError:
        messages.error(request, "You need to be registered as a teacher to respond to trade requests.")
        if timetable_slug:
            return redirect('my_trade_requests', timetable_slug=timetable_slug)
        # Get timetable from URL or default
        default_tt = Timetable.objects.first()
        fallback_slug = default_tt.slug if default_tt else 'default'
        return redirect('trade_request_list', timetable_slug=fallback_slug)
    
    original_request = get_object_or_404(TradeRequest, pk=pk)
    
    # Check if the teacher can fulfill this request
    can_fulfill = False
    if original_request.desired_allocation:
        # Check if teacher teaches the desired allocation
        can_fulfill = teacher in original_request.desired_allocation.activityRealization.teachers.all()
    else:
        # Flexible request - teacher can respond with any of their allocations
        can_fulfill = True
    
    if not can_fulfill:
        messages.error(request, "You cannot respond to this request as you don't teach the desired time slot.")
        return redirect('trade_request_detail', timetable_slug=timetable_slug, pk=pk)
    
    # Create a counter request
    counter_request = TradeRequest(
        requesting_teacher=teacher,
        offered_allocation=original_request.desired_allocation,  # What they want becomes what I offer
        desired_allocation=original_request.offered_allocation,  # What they offer becomes what I want
        reason=f"Response to trade request #{original_request.pk}"
    )
    counter_request.save()
    
    # Create a match between the two requests
    try:
        original_request.create_match(counter_request)
        messages.success(
            request, 
            f"Your response has been submitted! A trade match has been created and is now pending approval."
        )
    except ValueError as e:
        counter_request.delete()
        messages.error(request, f"Could not create trade match: {str(e)}")
    
    if timetable_slug:
        return redirect('my_trade_requests', timetable_slug=timetable_slug)
    return redirect('my_trade_requests', original_request.offered_allocation.timetable.slug)


@login_required
@transaction.atomic
def reject_trade_request(request, pk, timetable_slug=None):
    """Reject a trade request as a teacher (before it reaches admin approval)."""
    try:
        teacher = request.user.teacher
    except AttributeError:
        messages.error(request, "You need to be registered as a teacher to reject trade requests.")
        if timetable_slug:
            return redirect('my_trade_requests', timetable_slug=timetable_slug)
        default_tt = Timetable.objects.first()
        fallback_slug = default_tt.slug if default_tt else 'default'
        return redirect('trade_request_list', timetable_slug=fallback_slug)
    
    trade_request = get_object_or_404(TradeRequest, pk=pk)
    
    # Check if the teacher can reject this request
    # Teachers can reject requests that are offered to them (desired_allocation is theirs)
    can_reject = False
    if trade_request.desired_allocation:
        can_reject = teacher in trade_request.desired_allocation.activityRealization.teachers.all()
    
    if not can_reject:
        messages.error(request, "You cannot reject this trade request.")
        if timetable_slug:
            return redirect('my_trade_requests', timetable_slug=timetable_slug)
        return redirect('my_trade_requests', trade_request.offered_allocation.timetable.slug)
    
    if trade_request.status != 'OPEN':
        messages.error(request, "This trade request can no longer be rejected.")
        if timetable_slug:
            return redirect('my_trade_requests', timetable_slug=timetable_slug)
        return redirect('my_trade_requests', trade_request.offered_allocation.timetable.slug)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        try:
            trade_request.reject_by_teacher(teacher, reason)
            messages.success(request, "You have rejected this trade request.")
        except ValueError as e:
            messages.error(request, f"Could not reject trade request: {str(e)}")
        
        if timetable_slug:
            return redirect('my_trade_requests', timetable_slug=timetable_slug)
        return redirect('my_trade_requests', trade_request.offered_allocation.timetable.slug)
    
    # Show confirmation page
    # Ensure timetable_slug is set for template URLs
    if not timetable_slug:
        timetable_slug = trade_request.offered_allocation.timetable.slug
    
    return render(request, 'timetable/trade_requests/reject_confirm.html', {
        'trade_request': trade_request,
        'timetable_slug': timetable_slug,
    })


@login_required
@transaction.atomic
def trade_match_queue(request, timetable_slug=None):
    """View the trade match approval queue (for staff)."""
    if not request.user.is_staff:
        messages.error(request, "You don't have permission to access the approval queue.")
        # Get a default timetable if none provided
        if not timetable_slug:
            default_tt = Timetable.objects.first()
            if default_tt:
                timetable_slug = default_tt.slug
        if timetable_slug:
            return redirect('trade_request_list', timetable_slug=timetable_slug)
        return redirect('/')
    
    # Get timetable if slug provided
    timetable = None
    if timetable_slug:
        timetable = get_object_or_404(Timetable, slug=timetable_slug)
    
    # Handle POST requests (approve/reject)
    if request.method == 'POST':
        match_id = request.POST.get('match_id')
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        rejection_reason = request.POST.get('rejection_reason', '')
        
        # Handle individual trade request (free slot move)
        if request_id and action:
            try:
                trade_request = TradeRequest.objects.get(pk=request_id)
                reviewer = request.user.teacher if hasattr(request.user, 'teacher') else None
                
                if action == 'approve':
                    with transaction.atomic():
                        # Execute the move - change the allocation's day/time
                        allocation = trade_request.offered_allocation
                        original_classroom = allocation.classroom
                        new_day = allocation.day
                        new_start = allocation.start
                        new_classroom = allocation.classroom
                        
                        # If they specified a desired allocation, use its day/time/classroom
                        if trade_request.desired_allocation:
                            new_day = trade_request.desired_allocation.day
                            new_start = trade_request.desired_allocation.start
                            new_classroom = trade_request.desired_allocation.classroom
                        # Otherwise use the specified preferences
                        elif trade_request.desired_day or trade_request.desired_start_time:
                            if trade_request.desired_day:
                                new_day = trade_request.desired_day
                            if trade_request.desired_start_time:
                                new_start = trade_request.desired_start_time
                            
                            # Use desired classroom if specified
                            if trade_request.desired_classroom:
                                new_classroom = trade_request.desired_classroom
                            else:
                                conflicting_in_original = Allocation.objects.filter(
                                    timetable=allocation.timetable,
                                    classroom=original_classroom,
                                    day=new_day,
                                    start=new_start
                                ).exclude(id=allocation.id).exists()

                                if conflicting_in_original:
                                    messages.error(
                                        request,
                                        f"❌ Cannot approve: {original_classroom} is occupied at {dict(WEEKDAYS).get(new_day)} {new_start}. "
                                        f"Please pick a different time or classroom."
                                    )
                                    raise Exception("Original classroom occupied")
                        
                        # Check one more time for any conflicts (teacher, classroom, etc.)
                        conflicts = Allocation.objects.filter(
                            timetable=allocation.timetable,
                            day=new_day,
                            start=new_start
                        ).filter(
                            models.Q(classroom=new_classroom) |
                            models.Q(activityRealization__teachers__in=allocation.activityRealization.teachers.all())
                        ).exclude(id=allocation.id)
                        
                        if conflicts.exists():
                            conflict = conflicts.first()
                            conflict_reason = "classroom" if conflict.classroom == new_classroom else "teacher"
                            messages.error(
                                request,
                                f"❌ Cannot approve: {conflict_reason.capitalize()} conflict detected at {dict(WEEKDAYS).get(new_day)} {new_start}. "
                                f"Please resolve conflicts before approving."
                            )
                            raise Exception(f"{conflict_reason.capitalize()} conflict")
                        
                        # All checks passed - execute the move
                        allocation.day = new_day
                        allocation.start = new_start
                        allocation.classroom = new_classroom
                        allocation.save()
                        
                        # Update the trade request status
                        trade_request.status = 'APPROVED'
                        trade_request.approved_by = reviewer
                        trade_request.approval_date = timezone.now()
                        
                        classroom_note = f" (classroom changed to {new_classroom})" if new_classroom != original_classroom else ""
                        trade_request.approval_notes = f"Approved and executed via web interface - free slot move{classroom_note}"
                        trade_request.save()
                    
                    classroom_msg = f" in {new_classroom}" if new_classroom != original_classroom else ""
                    messages.success(
                        request, 
                        f"✅ Move approved and executed! {trade_request.requesting_teacher}'s class has been moved to "
                        f"{dict(WEEKDAYS).get(new_day)} at {new_start}{classroom_msg}."
                    )
                elif action == 'reject':
                    trade_request.status = 'REJECTED'
                    trade_request.approved_by = reviewer
                    trade_request.approval_date = timezone.now()
                    trade_request.approval_notes = f"Rejected: {rejection_reason}" if rejection_reason else "Rejected by administrator"
                    trade_request.save()
                    
                    messages.warning(
                        request, 
                        f"Move request rejected. {trade_request.requesting_teacher} will be notified."
                    )
            except TradeRequest.DoesNotExist:
                messages.error(request, "Trade request not found.")
            except Exception as e:
                messages.error(request, f"Error processing request: {str(e)}")
            
            # Get timetable_slug from request if not provided
            if not timetable_slug and request_id:
                try:
                    trade_request = TradeRequest.objects.get(pk=request_id)
                    timetable_slug = trade_request.offered_allocation.timetable.slug
                except:
                    pass
        
        # Handle trade match (swap)
        elif match_id and action:
            try:
                trade_match = TradeMatch.objects.get(pk=match_id)
                reviewer = request.user.teacher if hasattr(request.user, 'teacher') else None
                
                if action == 'approve':
                    trade_match.approve(reviewer, notes="Approved via web interface")
                    messages.success(
                        request, 
                        f"Trade approved! {trade_match.request_1.requesting_teacher} and "
                        f"{trade_match.request_2.requesting_teacher} have been notified."
                    )
                elif action == 'reject':
                    notes = f"Rejected: {rejection_reason}" if rejection_reason else "Rejected by administrator"
                    trade_match.reject(reviewer, notes=notes)
                    
                    messages.warning(
                        request, 
                        f"Trade rejected. {trade_match.request_1.requesting_teacher} and "
                        f"{trade_match.request_2.requesting_teacher} will see this as REJECTED with your reason."
                    )
            except TradeMatch.DoesNotExist:
                messages.error(request, "Trade match not found.")
            except Exception as e:
                messages.error(request, f"Error processing trade: {str(e)}")
        
            # Redirect back to queue - if no timetable_slug, get one from the trade match
            if not timetable_slug and match_id:
                try:
                    trade_match = TradeMatch.objects.get(pk=match_id)
                    timetable_slug = trade_match.request_1.offered_allocation.timetable.slug
                except:
                    pass
        
        if timetable_slug:
            return redirect('trade_match_queue', timetable_slug=timetable_slug)
        return redirect('/')
    
    # Get pending trade matches (two-way swaps)
    pending_matches = TradeMatch.objects.filter(
        status='PENDING_APPROVAL'
    ).select_related(
        'request_1__requesting_teacher__user',
        'request_1__offered_allocation__activityRealization__activity',
        'request_1__offered_allocation__classroom',
        'request_2__requesting_teacher__user',
        'request_2__offered_allocation__activityRealization__activity',
        'request_2__offered_allocation__classroom'
    )
    
    # Filter by timetable if provided
    if timetable:
        pending_matches = pending_matches.filter(
            request_1__offered_allocation__timetable=timetable
        )
    
    pending_matches = pending_matches.order_by('created_at')
    
    # Get pending individual trade requests (free slot moves)
    pending_requests = TradeRequest.objects.filter(
        status='PENDING_APPROVAL',
        matched_with__isnull=True  # Not part of a TradeMatch
    ).select_related(
        'requesting_teacher__user',
        'offered_allocation__activityRealization__activity',
        'offered_allocation__classroom',
        'desired_allocation__activityRealization__activity',
        'desired_allocation__classroom'
    )
    
    # Filter by timetable if provided
    if timetable:
        pending_requests = pending_requests.filter(
            offered_allocation__timetable=timetable
        )
    
    pending_requests = pending_requests.order_by('created_at')

    allocation_stats = {}

    def _build_student_stats(allocation):
        if not allocation:
            return None

        cached = allocation_stats.get(allocation.id)
        if cached is not None:
            return cached

        from friprosveta import models as friprosveta_models

        realization = allocation.activityRealization
        n_students = realization.size

        students = friprosveta_models.Student.objects.filter(
            groups__realizations=realization
        ).distinct()

        busy_cache = {}
        overlap_count = 0
        for student in students:
            cache_key = (student.id, allocation.timetable_id)
            busy_hours = busy_cache.get(cache_key)
            if busy_hours is None:
                busy_hours = student.busy_hours(allocation.timetable)
                busy_cache[cache_key] = busy_hours

            overlaps = student.overlaps(allocation.timetable, busy_hours)
            has_overlap = any(
                day == allocation.day
                and hour in allocation.hours
                and any(slot_alloc.id == allocation.id for slot_alloc in slot_allocs)
                for day, hour, slot_allocs in overlaps
            )

            if has_overlap:
                overlap_count += 1

        stats = {
            "n_students": n_students,
            "total_overlaps": overlap_count,
        }
        allocation_stats[allocation.id] = stats
        return stats

    def _build_slot_stats(allocation, day, start, duration):
        if not allocation or not day or not start or not duration:
            return None

        workhour_values = [hour[0] for hour in WORKHOURS]
        if start not in workhour_values:
            return None

        start_index = workhour_values.index(start)
        slot_hours = workhour_values[start_index : start_index + duration]
        if len(slot_hours) != duration:
            return None

        from friprosveta import models as friprosveta_models

        realization = allocation.activityRealization
        n_students = realization.size

        students = friprosveta_models.Student.objects.filter(
            groups__realizations=realization
        ).distinct()

        busy_cache = {}
        overlap_count = 0
        for student in students:
            cache_key = (student.id, allocation.timetable_id)
            busy_hours = busy_cache.get(cache_key)
            if busy_hours is None:
                busy_hours = student.busy_hours(allocation.timetable)
                busy_cache[cache_key] = busy_hours

            has_overlap = False
            for hour in slot_hours:
                allocations_in_slot = busy_hours.get((day, hour), [])
                if any(slot_alloc.id != allocation.id for slot_alloc in allocations_in_slot):
                    has_overlap = True
                    break

            if has_overlap:
                overlap_count += 1

        return {
            "n_students": n_students,
            "total_overlaps": overlap_count,
        }

    for match in pending_matches:
        match.request_1.offered_student_stats = _build_student_stats(
            match.request_1.offered_allocation
        )
        match.request_2.offered_student_stats = _build_student_stats(
            match.request_2.offered_allocation
        )

    for req in pending_requests:
        req.offered_student_stats = _build_student_stats(req.offered_allocation)
        req.desired_student_stats = _build_student_stats(req.desired_allocation)
        if not req.desired_allocation and req.desired_day and req.desired_start_time:
            effective_duration = req.desired_duration or req.offered_allocation.duration
            req.desired_slot_stats = _build_slot_stats(
                req.offered_allocation,
                req.desired_day,
                req.desired_start_time,
                effective_duration,
            )
    
    return render(request, 'timetable/trade_requests/approval_queue.html', {
        'pending_matches': pending_matches,
        'pending_requests': pending_requests,
        'timetable_slug': timetable_slug,
    })
