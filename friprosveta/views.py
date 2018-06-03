from bisect import bisect_left
import colorsys
import datetime
import itertools
import logging
from bisect import bisect_left
from collections import OrderedDict, defaultdict
from collections import namedtuple

import django.forms
import icalendar
import palettable
import pytz
# from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.decorators import login_required
from django.core import serializers
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render_to_response, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.utils.translation import ugettext as _
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.list import ListView

import frinajave
import friprosveta.forms
import friprosveta.models
import timetable.forms
import timetable.views
from friprosveta.forms import AssignmentForm, NajavePercentageForm
from timetable.models import Timetable, Group, ActivityRealization, \
    Allocation, Activity, WORKHOURS, WEEKDAYS, \
    Tag, default_timetable

logger = logging.getLogger(__name__)


class TimetableList(ListView):
    model = Timetable
    context_object_name = 'choosable_timetable_sets'

    def get_queryset(self):
        timetables = Timetable.objects.all()
        if self.request.user.is_staff:
            timetables = Timetable.objects.all()
        else:
            timetables = Timetable.objects.filter(public=True)
        return timetables


def index(request):
    return render(request, 'friprosveta/index.html', {})


def problems(request, *args, **kwargs):
    return render(request, 'friprosveta/problems.html', {})


def __visible_timetables(request):
    logger.info("Entering __visible_timetables")
    try:
        u = request.user
        assert u.is_staff
        timetables = friprosveta.models.Timetable.objects.all()
    except:
        timetables = friprosveta.models.Timetable.objects.filter(public=True)
    return timetables


def __visible_timetable_ids(request):
    return __visible_timetables(request).values_list('id', flat=True)


def __timetable_visible(request, t):
    try:
        u = request.user
        return t.public or u.is_staff
    except:
        pass
    return False


def __default_timetable_id():
    return friprosveta.models.Timetable.objects.filter(
        public=True,
        start__lte=datetime.datetime.now(),
        end__gte=datetime.datetime.now()
    ).order_by(
        'start'
    ).values_list('id', flatten=True)[0]


def __default_timetable(request):
    default_id = request.session.get('timetable_id', __default_timetable_id())
    return friprosveta.models.Timetable.objects.get(id=default_id)


def __is_teacher_or_staff(user):
    authenticated = False
    try:
        if user.teacher is not None:
            authenticated = True
    except:
        pass
    authenticated = authenticated | user.is_staff
    return authenticated


class PreferenceSetTimetableView(ListView):
    def get_queryset(self):
        self.timetable_set = get_object_or_404(timetable.models.TimetableSet,
                                               slug=self.kwargs['timetable_set_slug'])
        return timetable.models.PreferenceSet.objects.filter(
            timetable__timetable_sets=self.timetable_set).distinct()

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(PreferenceSetTimetableView, self).get_context_data(**kwargs)
        context['timetable_set_slug'] = self.timetable_set.slug
        return context


class GroupListView(ListView):
    template_name = "friprosveta/group_list.html"

    def get_queryset(self):
        self.timetable_slug = self.kwargs['timetable_slug']
        return timetable.models.Group.objects.filter(
            groupset__timetables__slug=self.timetable_slug).distinct()

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(GroupListView, self).get_context_data(**kwargs)
        context['timetable_slug'] = self.timetable_slug
        return context


class TagListView(ListView):
    template_name = "friprosveta/tag_preference_list.html"
    model = timetable.models.Tag

    def get_queryset(self):
        self.timetable_slug = self.kwargs['timetable_slug']
        return self.model.objects.all()

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(TagListView, self).get_context_data(**kwargs)
        context['timetable_slug'] = self.timetable_slug
        return context


def default_timetable_redirect(request):
    slug = default_timetable().slug
    return redirect("/timetable/{}/".format(slug), permanent=False)


# @cache_page(60 * 15)
def results(request, timetable_slug):
    class StudentForm(django.forms.Form):
        student = django.forms.CharField(label='vpisna', max_length=8)

    selected_timetable = get_object_or_404(timetable.models.Timetable,
                                           slug=timetable_slug)
    try:
        groups = selected_timetable.groupset.groups.filter(parent=None)
    except:
        groups = timetable.models.Group.objects.none()
    teachers = friprosveta.models.Teacher.objects.filter(
        activities__activityset=selected_timetable.activityset).distinct()
    subjects = friprosveta.models.Subject.objects.filter(
        activities__activityset=selected_timetable.activityset).distinct()
    if __is_teacher_or_staff(request.user):
        allocations_view = reverse('authenticated_allocations',
                                   kwargs={'timetable_slug': timetable_slug})
    else:
        allocations_view = reverse('allocations',
                                   kwargs={'timetable_slug': timetable_slug})

    if request.user.is_authenticated():
        try:
            accessing_student = friprosveta.models.Student.from_user(request.user)
        except friprosveta.models.Student.DoesNotExist:
            accessing_student = None
        accessing_teacher = request.user.teacher if hasattr(request.user, "teacher") else None
    else:
        accessing_student = None
        accessing_teacher = None

    params = {
        'allocations_view': allocations_view,
        'student_form': StudentForm,
        'timetable_slug': timetable_slug,
        'teachers': teachers.order_by('user__last_name', 'user__first_name'),
        'classrooms': selected_timetable.classroomset.classrooms.order_by(
            "name"),
        'studyGroups': groups,
        'subjects': subjects.order_by("name"),
        'accessing_student': accessing_student,
        'accessing_teacher': accessing_teacher
    }
    return render(request, 'friprosveta/results.html', params)


ParamTuple = namedtuple(
    'ParamTuple',
    [
        'exclusive', 'name', 'modelType',
        'filterProperty', 'allocationProperty'
    ]
)


def _allocation_context_links(request):
    contextlinks = dict()
    param_ids = dict()
    r = request.GET
    allparams = set(['teacher', 'classroom', 'group', 'activity',
                     'type', 'student', 'realization', 'subject'])
    exclusiveparams = set(['teacher', 'classroom', 'group', 'activity',
                           'subject', 'student'])
    passparams = allparams - exclusiveparams
    for i in allparams:
        contextlinks[i] = ""
    if 'timetable' in r:
        l = r.getlist('timetable')
        param_ids['timetable'] = [int(e) for e in l]
        for i in allparams - set(['timetable']):
            contextlinks[i] += "&timetable=" + "&timetable=".join(l)
    for param in ['teacher', 'classroom', 'group']:
        if param in r:
            l = r.getlist(param)
            param_ids[param] = [int(e) for e in l]
            for i in passparams:
                s = '&{0}='.format(param)
                contextlinks[i] += s + s.join(l)
    if 'subject' in r:
        l = r.getlist('subject')
        param_ids['subject'] = l
        for i in passparams:
            s = '&subject='
            contextlinks[i] += s + s.join(l)
    if 'type' in r:
        l = r.getlist('type')
        param_ids['type'] = l
        for i in allparams.copy() - set(['type']):
            contextlinks[i] += "&type=" + "&type=".join(l)
    if 'student' in r:
        l = r.getlist('student')
        param_ids['student'] = l
    if 'activity' in r:
        l = r.getlist('activity')
        param_ids['activity'] = l
        for i in passparams.copy() - set(['type']):
            contextlinks[i] += "&activity=" + "&activity=".join(l)
        try:
            activity_ids = map(int, l)
        except:
            activity_ids = []
        activities = friprosveta.models.Activity.objects.filter(
            id__in=activity_ids).all()
        subjects = set()
        for i in activities:
            subjects.add(str(i.activity.subject.code))
        contextlinks['type'] += "&subject=" + "&subject=".join(subjects)
        # contextlink += "&activity=" + "&activity=".join(l)
        # contextlink += "&group=" + "&group=".join(l)
    return contextlinks, param_ids


def _activity_set(param_ids, filtered_activities):
    allparams = set(['teacher', 'classroom', 'group', 'activity',
                     'type', 'student', 'realization', 'subject',
                     'timetable', 'timetable_slug'])
    # Do not allow unfiltered queries
    not_filtered = all([param not in param_ids for param in allparams])
    if not_filtered:
        return Activity.objects.none()
    if 'timetable' in param_ids:
        filtered_activities = filtered_activities.filter(
            activityset__timetable__id__in=param_ids['timetable'])
    if 'timetable_slug' in param_ids:
        filtered_activities = filtered_activities.filter(
            activityset__timetable__slug__in=param_ids['timetable_slug'])
    # exclusiveparams = set(['teacher', 'classroom', 'group', 'activity', 'subject', 'student'])
    if 'teacher' in param_ids:
        filtered_activities = filtered_activities.filter(teachers__id__in=param_ids['teacher'])
    # if 'classroom' in param_ids:
    #     filteredAllocations = filteredAllocations.filter(classroom__id__in=param_ids['classroom'])
    if 'activity' in param_ids:
        # contextlink += "&activity=" + "&activity=".join(l)
        filtered_activities = filtered_activities.filter(id__in=param_ids['activity'])
    if 'subject' in param_ids:
        filtered_activities = filtered_activities.filter(activity__subject__code__in=param_ids['subject'])
    if 'type' in param_ids:
        filtered_activities = filtered_activities.filter(type__in=param_ids['type'])
    # done filtering the allocations.
    if 'group' in param_ids:
        # contextlink += "&group=" + "&group=".join(l)
        groups_listed_ids = []
        for g in Group.objects.filter(id__in=param_ids['group']).all():
            groups_listed_ids += [i.id for i in g.family()]
        filtered_activities = filtered_activities.filter(
            groups__id__in=groups_listed_ids)
    realizations = set()
    if 'realization' in param_ids:
        realizations += set(param_ids['realization'])
    if 'student' in param_ids:
        logger.debug("Student in param_ids")
        sl = friprosveta.models.Student.objects.filter(studentId__in=param_ids['student'])
        logger.debug("Students: {}".format(sl))
        if len(sl) < 1:
            filtered_activities = Activity.objects.none()
        for s in sl:
            if len(s.follows.all()):
                logger.debug("Follows")
                realizations.add([ar.id for ar in s.follows.all()])
            else:
                logger.debug("Processing student groups")
                for g in s.groups.all():
                    logger.debug("Processing {}".format(g))
                    for r in g.realizations.all():
                        logger.debug("Processing realization {}".format(r))
                        realizations.add(r.id)
                logger.debug("Realizations: {}".format(realizations))
    if len(realizations):
        filtered_activities = filtered_activities.filter(realizations__id__in=realizations)
    return filtered_activities


def _realization_set(param_ids, filtered_realizations, allow_unfiltered=False):
    allparams = set(['teacher', 'group', 'activity',
                     'type', 'student', 'realization', 'subject'])
    if 'timetable_slug' in param_ids:
        if param_ids.get('unallocated', [False])[0]:
            filtered_realizations = filtered_realizations.filter(
                activity__activityset__timetable__slug__in=param_ids['timetable_slug'],
                allocations=None)
        else:
            filtered_realizations = filtered_realizations.filter(
                activity__activityset__timetable__slug__in=param_ids['timetable_slug'])
    if 'timetable' in param_ids:
        if param_ids.get('unallocated', [False])[0]:
            filtered_realizations = filtered_realizations.filter(
                activity__activityset__timetable__id__in=param_ids['timetable'],
                allocations=None)
        else:
            filtered_realizations = filtered_realizations.filter(
                activity__activityset__timetable__id__in=param_ids['timetable'])
    # Do not allow unfiltered queries
    not_filtered = all([param not in param_ids for param in allparams])
    if not_filtered and not allow_unfiltered:
        return ActivityRealization.objects.none()
    if 'teacher' in param_ids:
        filtered_realizations = filtered_realizations.filter(
            teachers__id__in=param_ids['teacher'])
    if 'activity' in param_ids:
        # contextlink += "&activity=" + "&activity=".join(l)
        filtered_realizations = filtered_realizations.filter(
            activity__id__in=param_ids['activity'])
    if 'subject' in param_ids:
        filtered_realizations = filtered_realizations.filter(
            activity__activity__subject__code__in=param_ids['subject'])
    if 'type' in param_ids:
        filtered_realizations = filtered_realizations.filter(
            activity__type__in=param_ids['type'])
    realization_ids = set()
    if 'realization' in param_ids:
        realization_ids += set(param_ids['realization'])
    if 'student' in param_ids:
        sl = friprosveta.models.Student.objects.filter(
            studentId__in=param_ids['student'])
        if len(sl) < 1:
            filtered_realizations = ActivityRealization.objects.none()
        for s in sl:
            if len(s.follows.all()):
                realization_ids.add([ar.id for ar in s.follows.all()])
            else:
                for g in s.groups.all():
                    for r in g.realizations.all():
                        realization_ids.add(r.id)
    if len(realization_ids):
        filtered_realizations = filtered_realizations.filter(
            id__in=realization_ids)
    if 'group' in param_ids:
        # contextlink += "&group=" + "&group=".join(l)
        groups_listed_ids = []
        for g in Group.objects.filter(id__in=param_ids['group']).all():
            groups_listed_ids += [i.id for i in g.family()]
        filtered_realizations = filtered_realizations.filter(
            groups__id__in=groups_listed_ids)
    return filtered_realizations


def _allocation_set(param_ids, filtered_allocations, is_staff=False):
    allparams = set(['teacher', 'classroom', 'group', 'activity',
                     'type', 'student', 'realization', 'subject'])

    # Do not allow unfiltered queries
    not_filtered = all([param not in param_ids for param in allparams])
    if not_filtered:
        return Allocation.objects.none()
    if 'timetable_slug' in param_ids:
        filtered_allocations = filtered_allocations.filter(
            Q(timetable__slug__in=param_ids['timetable_slug']) |
            Q(timetable__respects__slug__in=param_ids['timetable_slug']))
    if 'timetable' in param_ids:
        filtered_allocations = filtered_allocations.filter(
            Q(timetable__id__in=param_ids['timetable']) |
            Q(timetable__respects__id__in=param_ids['timetable']))
    if not is_staff:
        filtered_allocations = filtered_allocations.filter(timetable__public=True)
    if 'day' in param_ids:
        filtered_allocations = filtered_allocations.filter(day__in=param_ids['day'])
    if 'classroom' in param_ids:
        filtered_allocations = filtered_allocations.filter(classroom_id__in=param_ids['classroom'])
    realizations = _realization_set(
        param_ids, ActivityRealization.objects.all(), allow_unfiltered=True)
    filtered_allocations = filtered_allocations.filter(
        activityRealization__in=realizations)
    return filtered_allocations


def _titles(param_ids):
    if 'timetable' in param_ids or 'timetable_slug' in param_ids:
        tts = Timetable.objects.all()
    else:
        tts = Timetable.objects.none()
    if 'timetable' in param_ids:
        tts = tts.filter(id__in=param_ids['timetable'])
    if 'timetable_slug' in param_ids:
        tts = tts.filter(slug__in=param_ids['timetable_slug'])
    title = "; ".join([i.name for i in tts])
    subtitle_map = {
        'student': (friprosveta.models.Student,
                    lambda x: x.studentId,
                    lambda l: Q(studentId__in=l)),
        'teacher': (timetable.models.Teacher,
                    lambda x: str(x),
                    lambda l: Q(id__in=l)),
        'group': (timetable.models.Group,
                  lambda x: x.name,
                  lambda l: Q(id__in=l)),
        'subject': (friprosveta.models.Subject,
                    lambda x: x.name,
                    lambda l: Q(code__in=l)),
        'activity': (friprosveta.models.Activity,
                     lambda x: x.name,
                     lambda l: Q(id__in=l)),
        'classroom': (timetable.models.Classroom,
                      lambda x: x.name,
                      lambda l: Q(id__in=l)),
    }
    subtitles = []
    for k, v in param_ids.items():
        if k in subtitle_map:
            c, disp_fn, filter_fn = subtitle_map[k]
            l = c.objects.filter(filter_fn(v))
            subtitles.append("; ".join([disp_fn(i) for i in l]))
    return title, subtitles


def allocations_json(request, timetable_slug=None):
    # logger.info("Entering allocations_json")
    tt = get_object_or_404(timetable.models.Timetable, slug=timetable_slug)
    param_ids = _allocation_context_links(request)[1]
    # param_ids['timetable_slug'] = [timetable_slug]
    # This fetches all the allocations before filtering.
    # Why would you increase the server load on each request
    # just in case you need to debug something?
    # logger.debug("Got filtered allocations")
    # logger.debug("{}".format(filtered_allocations))
    filtered_allocations = _allocation_set(param_ids,
                                           tt.allocations,
                                           request.user.is_staff)
    # logger.debug("Filtered allocations after _allocation_set")
    # logger.debug("{}".format(filtered_allocations))
    json_data = serializers.serialize("json", filtered_allocations)
    # logger.debug("Returning json data")
    # logger.debug("{}".format(json_data))
    # logger.info("Exiting allocations_json")
    return HttpResponse(json_data)


def authenticated_allocations(request, timetable_slug=None):
    return _allocations(request, timetable_slug,
                        is_teacher=__is_teacher_or_staff(request.user))


def problematic_allocations(request, timetable_slug=None):
    object_list = []
    is_teacher = __is_teacher_or_staff(request.user)
    allocations = Allocation.objects.filter(timetable__slug=timetable_slug)
    for a in allocations:
        realization = a.activityRealization
        if realization.size > 0:
            classroom_utilization = 1.0 * realization.size / a.classroom.capacity
        else:
            classroom_utilization = 0
        if classroom_utilization < 0.5 or classroom_utilization > 1.0:
            css_class = "cycles_todo"
        else:
            css_class = "cycles_ok"
        # this is sloooow
        students = friprosveta.models.Student.objects.filter(groups__realizations=realization).distinct()
        group_overlaps = 0
        for g in a.groups.all():
            for tp in g.time_preferences.filter(day=a.day, level='CANT'):
                if len(set(a.hours).intersection(tp.hours())) > 0:
                    group_overlaps += g.size
                    students = students.exclude(groups=g)
        individual_overlaps = 0
        for s in students:
            busy = False
            possible_conflicts = timetable.models.Allocation.objects.filter(
                timetable=a.timetable,
                day=a.day,
                activityRealization__groups__students=s).exclude(id=a.id).distinct()
            for i in possible_conflicts:
                if len(set(a.hours).intersection(i.hours)) > 0:
                    busy = True
                    break
            if busy:
                individual_overlaps += 1
        object_list.append({"allocation": a,
                            "n_students": realization.size,
                            "total_overlaps": group_overlaps + individual_overlaps,
                            "group_overlaps": group_overlaps,
                            "individual_overlaps": individual_overlaps,
                            "classroom_utilization": classroom_utilization,
                            "css_class": css_class})
    return render_to_response('friprosveta/problematic_allocations.html', locals())


def allocations(request, timetable_slug=None):
    return _allocations(request, timetable_slug, is_teacher=False)


def _allocations(request, timetable_slug=None, is_teacher=False):
    context_links, param_ids = _allocation_context_links(request)
    tt = get_object_or_404(timetable.models.Timetable, slug=timetable_slug)
    param_ids = _allocation_context_links(request)[1]
    filtered_allocations = _allocation_set(param_ids,
                                           tt.allocations,
                                           request.user.is_staff)

    groups_listed = sorted(set(g for a in filtered_allocations for g in a.activityRealization.groups.all()),
                           key=lambda g: g.short_name)
    param_ids['timetable_slug'] = [timetable_slug]
    title, subtitles = _titles(param_ids)
    is_internet_explorer = "trident" in request.META["HTTP_USER_AGENT"].lower()
    get_args = "?" + "&".join("{}={}".format(escape(k), escape(v)) for k, v in request.GET.items()) if request.GET else ""

    # not necessarily needed, but this helps make labs of the same subject be closer when looking at a huge timetable
    filtered_allocations = filtered_allocations.order_by('activityRealization__activity')
    allocation_subjects = dict()
    for a in filtered_allocations:
        try:
            subject = friprosveta.models.Activity.from_timetable_activity(a.activityRealization.activity).subject
        except:
            subject = None
        allocation_subjects[a] = subject

    # generate nice colors for each subject, then allocation
    # colors repeat if there are too many subjects
    color_palette = palettable.colorbrewer.get_map("Set3", "qualitative", 12)
    ColorVM = namedtuple('ColorVM', ['h', 's', 'l'])
    allocation_colors = dict()
    subject_colors = dict()
    activity_colors = dict()
    colors_used = 0
    for a in filtered_allocations:
        activity_id = a.activityRealization.activity.id
        color = activity_colors.get(activity_id, None)
        if color is None:
            subject = allocation_subjects[a]
            if subject is not None:
                color = subject_colors.get(subject.id, None)
        if color is None:
            color = color_palette.colors[colors_used % color_palette.number]
            activity_colors[activity_id] = color
            if subject is not None:
                subject_colors[subject.id] = color
            colors_used += 1
        # colors are in HSL for easier manipulation
        hls_color = colorsys.rgb_to_hls(*(c / 256.0 for c in color))
        final_color = ColorVM(h=hls_color[0] * 360,
                              l="{:.2f}%".format(100 * hls_color[1]),
                              # emphasise lectures and slightly de-emphasise labs for more clarity
                              s="{:.2f}%".format(
                                  100 * hls_color[2] * (0.8 if a.activityRealization.activity.type != "P" else 1.4)))
        allocation_colors[a] = final_color
    AllocationVM = namedtuple('AllocationVM', ['object', 'subject', 'day_index', 'hour_index', 'duration', 'color'])
    weekday_mapping = {wd[0]: i for i, wd in enumerate(WEEKDAYS)}
    hour_mapping = {wh[0]: i for i, wh in enumerate(WORKHOURS)}
    allocation_vms = [AllocationVM(
        object=a,
        subject=allocation_subjects[a],
        day_index=weekday_mapping[a.day],
        hour_index=hour_mapping[a.start],
        duration=a.duration,
        color=allocation_colors[a],
    ) for a in filtered_allocations]
    # sorting required for groupby
    allocation_vms = sorted(allocation_vms, key=lambda avm: avm.day_index)
    allocations_by_day = [(d, list(avm_grouper))
                          for d, avm_grouper in itertools.groupby(allocation_vms, lambda avm: avm.object.day)]
    # add missing days so we have all columns present
    allocations_by_day += [(d[0], []) for d in WEEKDAYS if
                           d[0] not in [existing_day for existing_day, _ in allocations_by_day]]

    response = render(request, 'friprosveta/allocations.html', {
        'is_teacher': is_teacher,
        'context_links': context_links,
        'get_args': get_args,
        'title': title,
        'subtitles': subtitles,
        'groups': groups_listed,
        'timetable': timetable,
        'timetable_slug': timetable_slug,
        'day_keys': [wd[0] for wd in WEEKDAYS],
        'day_strings': [wd[1] for wd in WEEKDAYS],
        'hour_strings': [wh[1] for wh in WORKHOURS],
        'allocations_by_day': allocations_by_day,
        'is_internet_explorer': is_internet_explorer
    })

    return response


def allocations_ical(request, timetable_slug):
    tt = get_object_or_404(timetable.models.Timetable, slug=timetable_slug)
    param_ids = _allocation_context_links(request)[1]
    filtered_allocations = _allocation_set(param_ids, tt.allocations, request.user.is_staff)

    calendar = icalendar.Calendar()
    calendar.add("prodid", "-//Urnik FRI//urnik.fri.uni-lj.si//")
    calendar.add("version", "2.0")

    for a in filtered_allocations:
        try:
            subject = friprosveta.models.Activity.from_timetable_activity(a.activityRealization.activity).subject
        except:
            subject = None

        # the first event starts on the first occurrence of the day-hour after the timetable start
        timetable_start_day = tt.start.weekday()
        allocation_day = next(i for i, d in enumerate(WEEKDAYS) if d[0] == a.day)
        days_in_the_future = (allocation_day - timetable_start_day) % 7
        first_event_day = tt.start + datetime.timedelta(days=days_in_the_future)

        start_hour = int(a.start[0:2])
        first_event_start = datetime.datetime.combine(first_event_day, datetime.time(hour=start_hour, minute=0))
        first_event_start = first_event_start.astimezone(tz=pytz.timezone("Europe/Ljubljana"))
        first_event_end = first_event_start + datetime.timedelta(hours=a.duration)

        event = icalendar.Event()
        calendar.add_component(event)
        event.add("summary", "{} - {}".format(
            subject.short_name if subject else "unknown subject", a.activityRealization.activity.type
        ))
        event.add("description", "{} {} @ {}\n{}".format(
            subject.name if subject else "unknown subject",
            a.activityRealization.activity.type,
            a.classroom.name,
            ", ".join("{} {}".format(t.user.first_name, t.user.last_name) for t in a.activityRealization.teachers.all())
        ))
        event.add("location", a.classroom.name)
        event.add("uid", "urnikfri-{}".format(a.id))
        event.add("dtstart", first_event_start)
        event.add("dtend", first_event_end)
        event.add("dtstamp", datetime.datetime.utcnow())

        rep = icalendar.vRecur()
        event.add("rrule", rep)
        rep.update({
            "freq": "weekly",
            "byday": a.day[:2],
            "until": datetime.datetime.combine(tt.end, datetime.time.max)
        })

    result_text = calendar.to_ical().decode("UTF-8").replace("\\r\\n", "\n")
    response = HttpResponse(result_text, content_type="text/calendar")
    response["Content-Disposition"] = "attachment; filename=urnik.ical"
    return response


@login_required
def realizations_json(request, timetable_slug=None):
    contextlinks, param_ids = _allocation_context_links(request)
    realizations = _realization_set(
        param_ids, ActivityRealization.objects.all())
    json_data = serializers.serialize("json", realizations)
    # logger.debug("Returning json data")
    # logger.debug("{}".format(json_data))
    # logger.info("Exiting allocations_json")
    return HttpResponse(json_data)


@login_required
def allocations_edit(request, timetable_slug=None):
    # done filtering the groups
    contextlinks, param_ids = _allocation_context_links(request)
    param_ids['timetable_slug'] = [timetable_slug]
    title, subtitles = _titles(param_ids)
    filtered_allocations = _allocation_set(param_ids,
                                           Allocation.objects.all(),
                                           request.user.is_staff)
    activities = _activity_set(param_ids, Activity.objects.all())
    realizations = _realization_set(
        param_ids, ActivityRealization.objects.all())
    unplaced_realizations = realizations.exclude(
        id__in=filtered_allocations.values_list(
            'activityRealization_id', flat=True)
    )
    allocation_tabs = {}
    allocations_by_hour_day = defaultdict(lambda: defaultdict(list))
    for day, dayname in WEEKDAYS:
        allocation_tabs[day] = []
        for a in filtered_allocations.filter(
                day=day
        ).order_by(
            'start',
            '-activityRealization__activity__duration',
            'activityRealization__activity__name'
        ):
            placed = False
            for i, t in enumerate(allocation_tabs[day]):
                if t[-1].end <= a.start:
                    placed = True
                    a.offset = i
                    t.append(a)
                    break
            if not placed:
                a.offset = len(allocation_tabs[day])
                allocation_tabs[day].append([a])
            allocations_by_hour_day[a.start][day].append(a)
    allocations = []
    for hour, hourname in WORKHOURS:
        hour_allocations = []
        for day, dayname in WEEKDAYS:
            day_allocations = []
            for a in allocations_by_hour_day[hour][day]:
                n_divisions = len(allocation_tabs[day])
                if n_divisions > 0:
                    a.width = int(100.0 / n_divisions)
                    a.offset = a.width * a.offset
                else:
                    a.width = 100
                day_allocations.append(a)
            hour_allocations.append((dayname, day_allocations))
        allocations.append((hourname, hour_allocations))
    response = render(request, 'friprosveta/allocations_edit.html', {
        # 'spaceTakenList': spaceTakenList,
        'contextlinks': contextlinks,
        'title': title,
        'subtitles': subtitles,
        'day_header': WEEKDAYS,
        'timetable_slug': timetable_slug,
        'activities': activities[:32],
        'unplaced_realizations': unplaced_realizations,
        'realizations': realizations,
        'allocations': allocations})

    # if len(realizations) > 0:
    #     response.set_cookie("realizations", "&".join(map(str, realizations)),
    #                          expires=last_timetable_end)
    return response


def students_list(request, timetable_slug, realization_id):
    user = request.user
    students = []
    if __is_teacher_or_staff(user):
        realization = get_object_or_404(
            friprosveta.models.ActivityRealization,
            id=realization_id)
        allocations = Allocation.objects.filter(
            timetable__slug=timetable_slug,
            activityRealization=realization)
        if user.is_staff or user.teacher in realization.activity.teachers.all():
            students = realization.students.order_by('surname')
    data = {'students': students,
            'realization': realization,
            'allocations': allocations}
    return render(request, 'friprosveta/students_list.html', data)


@login_required
def busy_students_admin(request, timetable_slug, realization_id):
    tt = get_object_or_404(Timetable, slug=timetable_slug)
    realization = get_object_or_404(ActivityRealization, id=realization_id)
    days = [_(i[1]) for i in WEEKDAYS]
    hours = [i[0] for i in WORKHOURS]
    if request.GET.get('all_rooms', False):
        rooms = tt.classrooms.all()
    else:
        rooms = realization.preferred_rooms(tt)
    allow_bad_place = request.GET.get('allow_bad_place', False)
    busy_group_dict = defaultdict(lambda: defaultdict(int))
    busy_activity_dict = defaultdict(lambda: defaultdict(int))
    busy_group_preference_dict = defaultdict(set)
    for g in realization.groups.all():
        for s in g.students.all():
            allocations = tt.allocations.filter(
                activityRealization__groups__students=s
            ).exclude(
                activityRealization_id=realization_id).distinct()
            for a in allocations:
                for h in a.hours:
                    busy_activity_dict[(a.day, h)][a] += 1
                    busy_group_dict[(a.day, h)][g] += 1
        for tp in g.time_preferences.filter(level='CANT').distinct():
            for h in tp.hours():
                busy_group_preference_dict[(tp.day, h)].add(g)
    busy_teachers_dict = defaultdict(lambda: defaultdict(list))
    teachers_preference_dict = defaultdict(lambda: defaultdict(set))
    for t in realization.teachers.all():
        allocations = tt.allocations.filter(
            activityRealization__teachers=t
        ).exclude(
            activityRealization_id=realization_id).distinct()
        for a in allocations:
            for h in a.hours:
                busy_teachers_dict[(a.day, h)][t].append(a)
        for tp in timetable.models.TeacherTimePreference.objects.filter(
                teacher=t, preferenceset=tt.preferenceset).distinct():
            for h in tp.hours():
                teachers_preference_dict[(tp.day, h)][tp.level].add(t)
    classrooms_busy = defaultdict(lambda: defaultdict(list))
    for c in rooms:
        allocations = tt.allocations.filter(classroom=c).exclude(
            activityRealization_id=realization_id)
        for a in allocations:
            for h in a.hours:
                classrooms_busy[(a.day, h)][a.classroom].append(a)
    busy = list()
    for h_n, h in enumerate(hours):
        l = []
        for d in [i[0] for i in WEEKDAYS]:
            c_dict = dict(classrooms_busy[(d, h)])
            c_free = set([c for c in rooms if c not in c_dict])
            c_semifree = set()
            for h1 in hours[h_n + 1:h_n + realization.activity.duration]:
                for c_busy in dict(classrooms_busy[(d, h1)]):
                    if c_busy in c_free:
                        c_semifree.add(c_busy)
                    c_free.discard(c_busy)
            a_dict = dict(busy_activity_dict[(d, h)])
            g_dict = dict(busy_group_dict[(d, h)])
            total_overlap = 0
            bad_students_overlap = 0
            good_students_overlap = 0
            for k, v in g_dict.items():
                total_overlap += v
                try:
                    study = k.short_name.split('_')[1]
                except:
                    study = ''
                if study == 'PAD' or study == '8' or study == '4':
                    bad_students_overlap += v
                else:
                    good_students_overlap += v
            l.append((d, {
                'total_overlap': total_overlap,
                'good_students_overlap': good_students_overlap,
                'bad_students_overlap': bad_students_overlap,
                'classrooms_busy': c_dict,
                'classrooms_semifree': c_semifree,
                'classrooms_free': c_free,
                'groups': g_dict,
                'activities': a_dict,
                'group_preference_dict': busy_group_preference_dict[(d, h)],
                'busy_teachers': dict(busy_teachers_dict[(d, h)]),
                'teacher_preferences': dict(teachers_preference_dict[(d, h)])
            }))
        busy.append((h, l))
    return render(request, 'friprosveta/busy_students_admin.html', {
        'days': days, 'hours': hours, 'busy': busy,
        'rooms': rooms,
        'realization': realization,
        'allow_bad_place': allow_bad_place,
        'allocations': tt.allocations.filter(activityRealization=realization),
        'timetable_slug': timetable_slug})


class UnplacedRealizationsList(ListView):
    def get_queryset(self):
        return timetable.models.ActivityRealization.objects.filter(
            activity__activityset=self.timetable.activityset,
        ).exclude(
            allocations__timetable=self.timetable)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(UnplacedRealizationsList, self).get_context_data(**kwargs)
        context['timetable_slug'] = self.timetable.slug
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.timetable = get_object_or_404(Timetable, slug=kwargs['timetable_slug'])
        return super(UnplacedRealizationsList, self).dispatch(request, *args, **kwargs)


@login_required
def busy_students(request, timetable_slug, realization_id):
    days = [_(i[1]) for i in WEEKDAYS]
    hours = [i[0] for i in WORKHOURS]
    tt = get_object_or_404(timetable.models.Timetable, slug=timetable_slug)
    groupset = tt.groupset
    realization = get_object_or_404(timetable.models.ActivityRealization, id=realization_id)
    preferred_rooms = realization.preferred_rooms(tt)
    students = friprosveta.models.Student.objects.filter(groups__realizations=realization).distinct()
    busy_dict = dict()
    for s in students:
        allocations = tt.allocations.filter(
            activityRealization__groups__students=s
        ).exclude(
            activityRealization_id=realization.id
        ).distinct()
        # Some students might have overlapping allocations.
        # Count each time a student is busy exactly once.
        busy_set = set()
        for a in allocations:
            for h in a.hours:
                busy_set.add((a.day, h))
        for g in s.groups.filter(groupset=groupset):
            for tp in g.time_preferences.filter(level='CANT'):
                for h in tp.hours():
                    busy_set.add((tp.day, h))
        for (day, h) in busy_set:
            h_dict = busy_dict.get(h, dict())
            d = h_dict.get(day, 0)
            h_dict[day] = d + 1
            busy_dict[h] = h_dict
    classrooms_free = dict()
    for hour in WORKHOURS:
        classrooms_free[hour[0]] = dict()
        for day in WEEKDAYS:
            classrooms_free[hour[0]][day[0]] = set(preferred_rooms)
    for c in preferred_rooms:
        allocations = tt.allocations.filter(
            classroom=c)
        for a in allocations:
            for h in a.hours:
                try:
                    classrooms_free[h][a.day].remove(c)
                except KeyError:
                    pass  # survive double-booking which causes multiple removes.
    busy = list()
    for h in hours:
        l = []
        for d in WEEKDAYS:
            busy_s = busy_dict.get(h, dict()).get(d[0], 0)
            classrooms = classrooms_free[h][d[0]]
            l.append({'busy': busy_s, 'classrooms_free': classrooms})
        busy.append((h, l))
    return render(request, 'friprosveta/busy_students.html',
                  {'is_staff': request.user.is_staff,
                   'days': days, 'hours': hours, 'busy': busy,
                   'students': students,
                   'allocations': tt.allocations.filter(activityRealization=realization),
                   'preferred_rooms': preferred_rooms,
                   'realization': realization, 'timetable_slug': timetable_slug})


@login_required
def teacher_preference_login(request):
    return render(request, "friprosveta/timetable_teacherpreference_list.html",
                  {'object_list': __visible_timetables(request)})


@login_required
def teacher_preference_redirect(request, timetable_slug):
    return redirect('teacher_single_preferences',
                    timetable_slug=timetable_slug,
                    teacher_id=request.user.teacher.id)


@login_required
def activity_requirements(request):
    try:
        teacher = request.user.teacher
    except ObjectDoesNotExist:
        teacher = None
    if request.method == 'POST':
        complete_formset = timetable.forms.ActivityRequirementFormset(request.POST, request.FILES, prefix="cmplt-")
        if complete_formset.is_valid():
            complete_formset.save()
        user_formset = timetable.forms.ActivityRequirementFormset(request.POST, request.FILES, prefix="usr-")
        if user_formset.is_valid():
            user_formset.save()
    complete_formset = timetable.forms.ActivityRequirementFormset(
        prefix="cmplt-",
        queryset=friprosveta.models.Activity.objects.only('id', 'requirements'))
    if teacher is not None:
        l = []
        activities = teacher.activities.all()
        for a in activities:
            l += a.groups.values_list('id', flat=True)
        qs = Group.objects.filter(id__in=l)

        class AFForm(django.forms.ModelForm):
            groups = django.forms.ModelMultipleChoiceField(queryset=qs)

            class Meta:
                model = Activity

        AFS = django.forms.models.modelformset_factory(Activity, form=timetable.forms.ActivityRequirementForm, extra=0,
                                                       max_num=5, can_delete=False)
        user_formset = AFS(queryset=teacher.activities.only('id', 'requirements'),
                           initial=[{}] * len(activities) + [{'teachers': [teacher]}], prefix="usr-")
    else:
        user_formset = friprosveta.forms.ActivityRequirementFormset(prefix="usr-")
    return render(request, 'friprosveta/activity_requirements.html',
                  {'user_formset': user_formset, 'complete_formset': complete_formset,
                   'teacher': teacher})


@login_required
@transaction.atomic
def teacher_single_preferences(request, timetable_slug, teacher_id=None):
    try:
        if teacher_id is not None:
            teacher = friprosveta.models.Teacher.objects.get(id=int(teacher_id))
        else:
            teacher = request.user.teacher
        tt = Timetable.objects.get(slug=timetable_slug)
        pset = tt.preferenceset
    except Exception as e:
        logger.error(e)
        # raise Http404
    # if request.user.is_staff:
    if True:
        own_activities = teacher.activities.filter(activityset=tt.activityset)
        others_activities = friprosveta.models.Activity.objects.none()
    else:
        own_activities = teacher.subordinate_activities.filter(
            activityset=tt.activityset).distinct().order_by('-short_name')
        others_activities = teacher.others_activities.filter(
            activityset=tt.activityset).distinct().order_by('-short_name')
    problems = False
    problem_msg = "?"
    got_post_msg = ""
    if request.method == 'POST':
        preference_form = timetable.forms.TeacherPreferenceForm(request.POST, prefix='pref-')
        # own_act_formset = timetable.forms.ActivityRequirementsFormset(request.POST, request.FILES, prefix="ownact-")
        own_act_formset = timetable.forms.ActivityMinimalFormset(request.POST, request.FILES, prefix="ownact-")
        others_act_formset = timetable.forms.ActivityMinimalFormset(request.POST, request.FILES, prefix="act-")
        preference_form.full_clean()
        own_act_formset.full_clean()
        others_act_formset.full_clean()
        if preference_form.is_valid() and (
                not preference_form.preferenceset().locked \
                or request.user.is_staff) \
                and own_act_formset.is_valid() \
                and others_act_formset.is_valid():
            preference_form.save()
            try:
                own_act_formset.save()
                others_act_formset.save()
            except ValueError as e:
                problem_msg = "  Problem saving activity requirements" + str(e)
                problems = True
                if request.user.is_staff:
                    own_activities = teacher.activities.filter(
                        activityset=tt.activityset).distinct()
                    others_activities = friprosveta.models.Activity.objects.none()
                else:
                    own_activities = teacher.subordinate_activities.filter(
                        activityset=tt.activityset).distinct().order_by('-short_name')
                    others_activities = teacher.others_activities.filter(
                        activityset=tt.activityset).distinct().order_by('-short_name')
        else:
            problem_msg = "Problem v eni od form za aktivnosti"
            problem_msg += str(own_act_formset.errors) + str(others_act_formset.errors)
            problems = True
        if not problems:
            got_post_msg = "Zahteve uspešno vnešene"
        else:
            got_post_msg = problem_msg
    if not problems:
        # own_act_formset = timetable.forms.ActivityRequirementsFormset(queryset=own_activities, prefix="ownact-" )
        own_act_formset = timetable.forms.ActivityMinimalFormset(queryset=own_activities, prefix="ownact-")
        others_act_formset = timetable.forms.ActivityMinimalFormset(queryset=others_activities, prefix="act-")
        preference_form = timetable.forms.TeacherPreferenceForm(teacher=teacher, preferenceset=pset, prefix="pref-")
    return render(request, 'friprosveta/teacher_single_democratic_preferences.html',
                  {'preference_set': pset,
                   'timetable_slug': timetable_slug,
                   'deadline': None,
                   'preference_form': preference_form,
                   'own_activity_formset': own_act_formset,
                   'others_activity_formset': others_act_formset,
                   'got_post_msg': got_post_msg,
                   })


@login_required
def teacher_preference_list(request, timetable_slug):
    tt = get_object_or_404(Timetable, slug=timetable_slug)
    fargs = {'preferenceset__id': tt.preferenceset.id}

    class FTeacher(friprosveta.models.Teacher):
        class Meta:
            proxy = True

        def cant_time_preferences(self):
            return self.time_preferences.filter(level='CANT', **fargs)

        def hate_time_preferences(self):
            return self.time_preferences.filter(level='HATE', **fargs)

        def want_time_preferences(self):
            return self.time_preferences.filter(level='WANT', **fargs)

        def cant_hours(self):
            i = self.cant_time_preferences().aggregate(Sum('duration'))['duration__sum']
            if i is None:
                return 0
            return i

        def hate_hours(self):
            i = self.hate_time_preferences().aggregate(Sum('duration'))['duration__sum']
            if i is None:
                return 0
            return i

        def want_hours(self):
            i = self.want_time_preferences().aggregate(Sum('duration'))['duration__sum']
            if i is None:
                return 0
            return i

        def filtered_descriptive_preferences(self):
            return self.descriptive_preferences.filter(**fargs)

    q = FTeacher.objects.filter(
        activities__activityset=tt.activityset
    ).distinct().order_by('user__last_name', 'user__first_name')

    class FTeacherListView(ListView):
        template_name = "friprosveta/teacher_preference_list.html"

        def get_context_data(self, **kwargs):
            context = super(FTeacherListView, self).get_context_data(**kwargs)
            context['timetable_slug'] = timetable_slug
            return context

        # model = FTeacher
        queryset = q

    return FTeacherListView.as_view()(request)


@login_required
def group_single_preferences(request, timetable_slug, group_id=None):
    tt = get_object_or_404(Timetable, slug=timetable_slug)
    logger.info("Entering group_single_preferences")
    try:
        group = timetable.models.Group.objects.get(id=int(group_id))
    except Exception:
        logger.exception("Exception while getting data for group id {}".format(group_id))
        raise Http404
    logger.debug("Getting preference set")
    pset = tt.preferenceset
    problems = False
    got_post = False
    if request.method == 'POST':
        logger.debug("POST")
        preference_form = timetable.forms.GroupPreferenceForm(request.POST, prefix='pref-')
        preference_form.full_clean()
        if preference_form.is_valid() and (
                not preference_form.preferenceset().locked or request.user.is_staff):
            preference_form.save()
        else:
            problems = True
    logger.debug("Problems: {}".format(problems))
    if not problems:
        logger.debug("Preparing preference set form")
        preference_form = timetable.forms.GroupPreferenceForm(group=group, preferenceset=pset, prefix="pref-")
    return render(request, 'friprosveta/group_preferences.html',
                  {'form': preference_form,
                   'timetable_slug': timetable_slug,
                   'got_post': got_post,
                   })


@login_required
def tag_time_preferences(request, timetable_slug, tag_id):
    tt = get_object_or_404(Timetable, slug=timetable_slug)
    pset = tt.preferenceset
    try:
        tag = Tag.objects.get(id=int(tag_id))
    except Exception as e:
        logger.error(e)
        raise Http404
    problems = False
    got_post = False
    if request.method == 'POST':
        preference_form = timetable.forms.TagTimetablePreferenceForm(request.POST, prefix='pref-')
        preference_form.full_clean()
        if preference_form.is_valid() and (
                not preference_form.preferenceset().locked or request.user.is_staff):
            preference_form.save()
        else:
            problems = True
    if not problems:
        preference_form = timetable.forms.TagTimetablePreferenceForm(
            tag=tag, preferenceset=pset, prefix="pref-")
    return render(
        request,
        'friprosveta/tag_time_preferences.html', {
            'form': preference_form,
            'timetable_slug': timetable_slug,
            'got_post': got_post})


# NAJAVE

@login_required
@transaction.atomic
def assignments(request, timetable_slug, subject_code):
    tt = get_object_or_404(timetable.models.Timetable, slug=timetable_slug)
    try:
        timetable_set = tt.timetable_sets.all()[0]
    except:
        raise Http404
    user = request.user.teacher
    subject = friprosveta.models.Subject.objects.get(code=subject_code)

    if not request.user.is_staff \
            and user.id not in subject.managers.values_list('id', flat=True):
        raise Http404

    activities = subject.activities.filter(activityset=tt.activityset).order_by("type")

    AssignmentFormset = django.forms.models.modelformset_factory(Activity, extra=0, form=AssignmentForm)
    for a in activities:
        a.displayName = a.get_type_display()
    # razdeli forme v skupine glede na nacin izvajanja / kaste uciteljev
    if request.method == 'POST':
        assignment_formset = AssignmentFormset(request.POST,
                                               request.FILES,
                                               queryset=activities)
        assignment_formset.full_clean()
        teachers = set()
        if assignment_formset.is_valid():
            for form in assignment_formset.forms:
                activity = form.save(commit=False)
                activity.save()
                subject = activity.subject
                lecture_type = friprosveta.models.LectureType.objects.get(short_name=activity.type).id
                # for p in timetable.models.ActivityPercentage.objects.filter(activity=activity):
                #     percentages[p.teacher] = p
                # Delete old percentage sets
                # timetable.models.ActivityPercentage.objects.filter(activity=activity).delete()
                activity.teachers.clear()
                # Get old najave entries
                old_najave = frinajave.models.TeacherSubjectCycles.objects.filter(lecture_type=lecture_type,
                                                                                  timetable_set=timetable_set,
                                                                                  subject_code=subject_code)
                old_najave_ids = [entry.id for entry in old_najave.all()]

                for teacher in form.cleaned_data.get('teachers'):
                    teachers.add((teacher, activity.lecture_type.id))
                    activity.teachers.add(teacher)
                    # ap = percentages.get(teacher, ActivityPercentage(teacher=teacher, activity=activity))
                    # ap.save()

                    old_najave_teacher_period = old_najave.filter(
                        timetable_set=timetable_set, teacher_code=teacher.code)
                    # a teacher can have 2 
                    assert len(
                        old_najave_teacher_period) <= 1, "At most one entry per subject/techer/timetable_set/lecture_type combination: {0}, timetable_set {1}: {2}".format(
                        teacher, timetable_set, list(old_najave_teacher_period.all()))
                    cycles = 1
                    instruction_type = None
                    teacher_comment = ''
                    if old_najave_teacher_period.count() == 1:
                        old_najave_teacher_period = old_najave_teacher_period.get()
                        cycles = old_najave_teacher_period.cycles
                        instruction_type = old_najave_teacher_period.instruction_type
                        teacher_comment = old_najave_teacher_period.comment
                    subject_cycle = frinajave.models.TeacherSubjectCycles(
                        lecture_type=lecture_type, timetable_set=timetable_set,
                        subject_code=subject_code, teacher_code=teacher.code,
                        cycles=cycles, comment=teacher_comment,
                        instruction_type=instruction_type)
                    subject_cycle.save()
                # Remove all old najave entries
                for entry_id in old_najave_ids:
                    entry = frinajave.models.TeacherSubjectCycles.objects.get(pk=entry_id)
                    entry.delete()
    else:
        assignment_formset = AssignmentFormset(queryset=activities)
    media = assignment_formset.media
    return render(
        request,
        'friprosveta/assignments.html',
        {
            'timetable_slug': timetable_slug,
            'assignment_formset': assignment_formset,
            'subject': subject,
            'media': media,
        })


@login_required
def subject(request, timetable_slug, subject_code):
    tt = get_object_or_404(timetable.models.Timetable, slug=timetable_slug)
    user = request.user.teacher
    subject = friprosveta.models.Subject.objects.get(code=subject_code)
    # if not user.is_staff or not subject in user.managed_subjects:
    if not request.user.is_staff:  # \
        # and user not in subject.managers.all() \
        # and user not in subject.teachers(tt):
        raise PermissionDenied
    activities = subject.activities.filter(activityset=tt.activityset).distinct().order_by("type")
    studies = subject.studiesOnTimetables([tt])
    studies.sort()

    najave_percentage_formset = django.forms.models.modelformset_factory(
        frinajave.models.TeacherSubjectCycles, extra=0, form=NajavePercentageForm)

    for a in activities:
        a.displayName = a.get_type_display()

    # razdeli forme v skupine glede na nacin izvajanja / kaste uciteljev
    teacher_classes = {'P': "Nosilec",
                       'AV': "Asistenti",
                       'LV': "Asistenti",
                       'LAB': "Laboranti",
                       'lab.': "Laboranti"}
    problems = False
    problem_msg = "?"
    got_post_msg = ""
    najave_percentages = frinajave.models.TeacherSubjectCycles.objects.filter(
        subject_code=subject.code,
        timetable_set__timetables=tt).order_by("lecture_type")
    teachers_formset = najave_percentage_formset(queryset=najave_percentages, prefix="prc-")

    if request.method == 'POST':
        # if not (user.id in subject.managers.values_list('id', flat=True)):
        #     raise PermissionDenied
        if not request.user.is_staff:
            raise PermissionDenied
        teachers_formset = najave_percentage_formset(request.POST, request.FILES, queryset=najave_percentages,
                                                     prefix="prc-")
        realization_formsets = []
        for activity in activities:
            Formset = timetable.forms.realization_formset(activity, tt)
            formset = Formset(request.POST, request.FILES, instance=activity, prefix='act--{0}-'.format(activity.id))
            realization_formsets.append(formset)
        realization_formsets_valid = True
        realization_formsets_errors = ""
        for formset in realization_formsets:
            formset.full_clean()
            if not formset.is_valid():
                realization_formsets_errors += str(formset.errors)
                realization_formsets_valid = False
        if realization_formsets_valid:
            try:
                for i in realization_formsets:
                    i.save()
            except ValueError as e:
                problem_msg = "  Problem saving realizations" + str(e)
                problems = True
        else:
            if not realization_formsets_valid:
                problem_msg = "Problem v enem od obrazcev za cikle:" + str(realization_formsets_errors)
            problems = True
        if not problems:
            got_post_msg = "Zahteve uspešno vnešene"
        else:
            got_post_msg = problem_msg
    media = None

    id_hack = -1

    percentage_forms = OrderedDict()
    for f in teachers_formset.forms:
        i = f.instance
        if i is not None:
            lecture_type = friprosveta.models.LectureType.objects.get(pk=i.lecture_type)
            try:
                teacher = friprosveta.models.Teacher.objects.get(code=i.teacher_code)
                id_hack -= 1
            except Exception:
                # If no teacher is found, add unknown teacher (but do not save it to database
                user = timetable.models.User(first_name='Unknown', last_name=str(i.teacher_code), id=-id_hack)
                teacher = friprosveta.models.Teacher(user=user, code=i.teacher_code, id=-id_hack)
            i.lecture_type = lecture_type
            current_activities = activities.filter(lecture_type=lecture_type)
            realization_hours = 0
            for ar in timetable.models.ActivityRealization.objects.filter(activity__in=current_activities,
                                                                          teachers__exact=teacher).distinct():
                realization_hours += ar.duration
            realizations_number = 1.0 * realization_hours / lecture_type.duration

            t = teacher_classes.get(lecture_type.short_name, "Unknown")
            form_group = percentage_forms.get(t, OrderedDict())
            l = form_group.get(teacher, [])
            l.append((f, realizations_number))
            form_group[teacher] = l
            percentage_forms[t] = form_group
    realization_formsets = []
    for activity in activities:
        Formset = timetable.forms.realization_formset(activity, tt)
        formset = Formset(instance=activity, prefix='act--{0}-'.format(activity.id))
        if media is None:
            media = formset.media
        realization_formsets.append(formset)
    return render(request, 'friprosveta/subject.html', {
        'timetable_slug': timetable_slug,
        'teachers_formset': teachers_formset,
        'percentage_forms': percentage_forms,
        'subject': subject,
        'media': media,
        'realization_formsets': realization_formsets,
        'got_post_msg': got_post_msg,
        'studies': studies, })


@login_required
def subject_list(request, timetable_slug):
    def is_synced_with_najave(activity):
        """
        Check if realizations within given activity are in sync with najave.
        :param activity:
        :return: String. If realizations are not in sync with najave it is non-empty.
        """
        # Read najave
        najave = activity.najave()
        teachers_najave_cycles = defaultdict(int)
        for najava in najave:
            teachers_najave_cycles[najava.teacher_code] += najava.cycles

        teachers_realizations_number = defaultdict(int)
        for realization in activity.realizations.all():
            for teacher in realization.teachers.all():
                teachers_realizations_number[teacher.code] += 1

        # Same teachers
        najave_teachers = set(teachers_najave_cycles.keys())
        realizations_teachers = set(teachers_realizations_number.keys())
        if najave_teachers != realizations_teachers:
            return _("Teachers do not match with najave")

        for teacher_code in teachers_najave_cycles.keys():
            najave_cycles = teachers_najave_cycles[teacher_code]
            realizations_number = teachers_realizations_number[teacher_code]
            if najave_cycles != realizations_number:
                teacher = friprosveta.models.Teacher.objects.get(code=teacher_code)
                return _("Wrong number of cycles for {}".format(teacher))
        return ""

    tt = friprosveta.models.Timetable.objects.get(slug=timetable_slug)
    teacher = request.user.teacher
    user = request.user
    data = []
    if user.is_staff:
        subjects = tt.subjects.all().distinct().order_by("name")
    else:
        subjects = tt.subjects.filter(managers=teacher).distinct().order_by("name")
    l = []
    for frisubject in subjects:
        css_class = "cycles_ok"
        is_synced = True
        synced_message = ""
        for activity in tt.activities.filter(subject=frisubject):
            synced = is_synced_with_najave(activity)
            if len(synced) > 0:
                synced_message += "{}: {}\n".format(activity.short_name, synced)
                is_synced = False

        student_num = len(frisubject.get_enrolled_students(tt))
        unallocated_students = [
            frisubject.number_of_unallocated_students(tip, tt) for tip in ["LV", "AV", "P"]]
        if sum(unallocated_students) > 0:
            css_class = "cycles_todo"
        l.append([frisubject, student_num] + unallocated_students + [css_class] +
                 [is_synced, synced_message])
    # except:
    data.append((tt.name, l))
    #    pass
    return render(request, 'friprosveta/subject_list.html', {
        'data': data,
        'timetable_slug': timetable_slug})


@login_required
def teacher_hours(request, timetable_set_slug):
    user = request.user.teacher
    timetable_set = timetable.models.TimetableSet.objects.get(slug=timetable_set_slug)

    def cycles_by_timetable_type(teacher, ttables=None, types=None):
        cycles_sums_by_tt = dict()
        for tt in ttables:
            tt = friprosveta.models.Timetable.objects.get(id=tt.id)
            data = list()
            suma = dict()
            subjects = tt.subjects.filter(activities__teachers=teacher).distinct()
            for frisubject in subjects:
                for cycleType, long_cycleType in timetable.models.ACTIVITYTYPES:
                    suma_for_type = suma.get(cycleType, [0.0, 0.0])
                    cycles = frisubject.cyclesForTeacher(teacher, cycleType, tt)
                    cycles_najave = 0
                    percentage_najave = 0
                    if teacher.code != "":
                        try:
                            frilecture_type = friprosveta.models.LectureType.objects.get(short_name=cycleType)
                            najave_entry = frinajave.models.TeacherSubjectCycles.objects.filter(
                                teacher_code=teacher.code, subject_code=frisubject.code, timetable_set=timetable_set,
                                lecture_type=frilecture_type.id)
                            if len(najave_entry) == 1:
                                najave_entry = najave_entry[0]
                                cycles_najave = najave_entry.cycles
                                # percentage_najave = float(najave_entry.percentage)
                                percentage_najave = 1
                        except:
                            pass
                    suma_for_type[0] += cycles
                    suma_for_type[1] += float(cycles_najave * percentage_najave)
                    suma[cycleType] = suma_for_type
                    if cycles > 0 or cycles_najave > 0:
                        data.append((frisubject, cycleType, cycles, cycles_najave, percentage_najave))
            # convert sums from dict to list, only keeping non-zeroes
            cycles_sums_by_tt[tt] = (data, [[key] + vals for key, vals in suma.items() if max(vals) > 0])
        return cycles_sums_by_tt

    # this is completely wrong for now.
    ttables = timetable_set.timetables.distinct().order_by('start')
    q = Q()
    for tt in ttables:
        q = q | Q(activities__activity__subject__activities__teachers=user,
                  activities__activityset__timetable=tt)
    q = q | Q(activities__activity__subject__managers=user)
    others = friprosveta.models.Teacher.objects.filter(q).distinct().exclude(id=user.id)
    for o in others:
        o.timetables_hours = cycles_by_timetable_type(o, ttables)
    user.timetables_hours = cycles_by_timetable_type(user, ttables)
    sorted_others = sorted(others, key=lambda teacher: teacher.user.last_name)
    return render(request, 'friprosveta/teacher_hours.html', {
        'data': [user] + sorted_others,
        'timetable_set_slug': timetable_set_slug})


def binary_search(a, x, lo=0, hi=None):  # can't use a to specify default for hi
    hi = hi if hi is not None else len(a)  # hi defaults to len(a)
    pos = bisect_left(a, x, lo, hi)  # find insertion position
    return pos if pos != hi and a[pos] == x else -1  # don't walk off the end


@login_required
def teacher_hours_table(request, timetable_set_slug):
    user = request.user.teacher
    suma = dict()

    def cycles_by_timetable_type(ttables, shown_activity_types):
        cycles_by_tt = dict()
        translate_activity_type = {'lab.': 'LAB'}
        lecture_type_id_to_short_name = {lecture_type.id: lecture_type.short_name for lecture_type in
                                         friprosveta.models.LectureType.objects.all()}
        subject_codes = dict()
        tt_names = []
        for tt in ttables:
            tt = friprosveta.models.Timetable.objects.get(id=tt.id)
            tt_names.append(tt.name)
            subject_codes[tt.name] = sorted(tt.subjects.all().values_list('code', flat=True))
            cycles_by_tt[tt.name] = dict()
        for entry in frinajave.models.TeacherSubjectCycles.objects.filter(timetable_set=timetable_set):
            for tt in ttables:
                tt_name = tt.name
                if binary_search(subject_codes[tt_name], entry.subject_code) == -1: continue
                activity_type_short_name = lecture_type_id_to_short_name[entry.lecture_type]
                if activity_type_short_name in translate_activity_type:
                    activity_type_short_name = translate_activity_type[activity_type_short_name]
                if activity_type_short_name not in shown_activity_types: continue
                if entry.teacher_code not in cycles_by_tt[tt_name]:
                    cycles_by_tt[tt_name][entry.teacher_code] = dict()
                    for activity_type in shown_activity_types:
                        cycles_by_tt[tt_name][entry.teacher_code][activity_type] = [0.0, 0.0]
                # Real cycles hits the database preety bad
                real_cycles = tt.realizations.filter(activity__type=activity_type_short_name,
                                                     activity__activity__subject__code=entry.subject_code,
                                                     teachers__code=entry.teacher_code).count()
                cycles_by_tt[tt_name][entry.teacher_code][activity_type_short_name][0] += entry.cycles * float(
                    entry.percentage)
                cycles_by_tt[tt_name][entry.teacher_code][activity_type_short_name][1] += real_cycles * float(
                    entry.percentage)
        return cycles_by_tt

    timetable_set = timetable.models.TimetableSet.objects.get(slug=timetable_set_slug)
    ttables = timetable_set.timetables.distinct().order_by('start')
    q = Q()
    for tt in ttables:
        q = q | Q(activities__activity__subject__activities__teachers=user, activities__activityset__timetable=tt)
    q = q | Q(activities__activity__subject__managers=user)
    visible_teachers = friprosveta.models.Teacher.objects.filter(q).distinct()
    shown_activity_types = ['LV', 'AV', 'P']
    cycles = cycles_by_timetable_type(ttables, shown_activity_types)
    teacher_data = []
    for teacher in visible_teachers.order_by('user__last_name'):
        data = []
        suma = dict()
        for activity_type in shown_activity_types:
            suma[activity_type] = [0, 0]
        for tt in ttables:
            if teacher.code not in cycles[tt.name]:
                cycles[tt.name][teacher.code] = dict()
                for activity_type in shown_activity_types:
                    cycles[tt.name][teacher.code][activity_type] = [0, 0]
            for activity_type in shown_activity_types:
                data.append(cycles[tt.name][teacher.code][activity_type])
                for i in range(len(cycles[tt.name][teacher.code][activity_type])):
                    suma[activity_type][i] += cycles[tt.name][teacher.code][activity_type][i]
        for activity_type in shown_activity_types:
            data.append(suma[activity_type])
        data.append([suma['LV'][0] + suma['AV'][0], suma['LV'][1] + suma['AV'][1]])
        teacher_data.append([teacher, data])
    return render(request, 'friprosveta/teacher_hours_table.html',
                  {'teacher_data': teacher_data,
                   'timetables': ttables.all,
                   'timetable_colspan': 2 * len(shown_activity_types),
                   'activity_colspan': 2,
                   'activity_types': shown_activity_types,
                   'timetable_set_slug': timetable_set_slug,
                   })


@login_required
def place_realization(request, timetable_slug, realization_id):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    realization = get_object_or_404(ActivityRealization, id=realization_id)
    tt = get_object_or_404(Timetable, slug=timetable_slug)
    existing_allocations = Allocation.objects.filter(
        activityRealization_id=realization_id, timetable=tt)
    if request.method == 'POST':
        data = request.POST.copy()
        data['activityrealization_id'] = [realization_id]
        data['timetable_id'] = [realization_id]
        form = friprosveta.forms.AllocationNoIdPlaceForm(data)
        if form.is_valid():
            n_existing = existing_allocations.count()
            if n_existing > 1:
                existing_allocations.delete()
            elif n_existing == 1:
                form.instance.pk = existing_allocations.first().pk
            form.instance.activityRealization = realization
            form.instance.timetable = tt
            form.save()
            try:
                success_url = request.META['HTTP_REFERER']
            except:
                # success_url = reverse('allocations')
                success_url = reverse('allocations',
                                      timetable_slug=timetable_slug,
                                      ) + "?activity=" + form.instance.activityRealization.activity
            return HttpResponseRedirect(success_url)
    else:
        form = friprosveta.forms.AllocationNoIdPlaceForm()
    return render(request, 'friprosveta/place_realization.html',
                  {'form': form})


class SubjectActivityDetail(DetailView):
    model = friprosveta.models.Activity


class SubjectActivityUpdate(UpdateView):
    model = friprosveta.models.Activity


class SubjectActivityCreate(CreateView):
    model = friprosveta.models.Activity


class SubjectActivityDelete(DeleteView):
    model = friprosveta.models.Activity
