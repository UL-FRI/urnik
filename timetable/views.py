import logging
from collections import namedtuple, OrderedDict

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.forms import formsets
from django.http import Http404
from django.shortcuts import render
from django.template import RequestContext
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView
from django.views.generic.list import ListView

from timetable.forms import ActivityRequirementsFormset, \
    TeacherPreferenceForm, GroupPreferenceForm
from timetable.models import Timetable, Group, Classroom, Teacher, \
    Allocation, Activity, WORKHOURS, WEEKDAYS

logger = logging.getLogger(__name__)


def index(request):
    params = {}
    return render(request, 'timetable/index.html', params)


def results(request):
    class TimetableChoiceForm(forms.Form):
        timetable = forms.ModelMultipleChoiceField(Timetable.objects.all(), label='Urnik:')

    params = {
        'timetable': TimetableChoiceForm,
        'teachers': Teacher.objects.filter().order_by('user__first_name', 'user__last_name'),
        'classrooms': Classroom.objects.all(),
        'studyGroups': Group.objects.filter(parent=None)}
    return render(request, 'timetable/results.html', params)


def timetable_preference_links(request):
    timetables = Timetable.objects.order_by('period.start').all()
    return render(
        request,
        'timetable/teacher_preference_links.html',
        {'timetables': timetables})


def teacher_preference_links(request, timetable_id=None):
    teachers = Teacher.objects.order_by('surname', 'name', 'sifra').filter()
    return render(
        request
        'timetable/teacher_preference_links.html',
        {'teachers': teachers, 'timetable_id': timetable_id})


def show_allocations(allocations):
    def first_free_index(integer_set):
        for i in range(len(integer_set)):
            if i not in integer_set:
                return i

    running_allocations = set()
    taken_indices = set()
    events = set(
        [(allocation.start, "start", allocation) for allocation in allocations] +
        [(allocation.end, "end", allocation) for allocation in allocations]
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
    timetable = None
    teacher = None
    classroom = None
    activity = None
    group = None
    if 'timetable' in r:
        timetable = Timetable.objects.get(id=r['timetable'])
        filtered_allocations = filtered_allocations.filter(timetable=timetable)
    if 'teacher' in r:
        teacher = Teacher.objects.get(id=r['teacher'])
        filtered_allocations = filtered_allocations.filter(activityRealization__teachers__exact=teacher)
    if 'classroom' in r:
        classroom = Classroom.objects.get(id=r['classroom'])
        filtered_allocations = filtered_allocations.filter(classroom=classroom)
    if 'activity' in r:
        activity = Activity.objects.get(id=r['activity'])
        filtered_allocations = filtered_allocations.filter(activity__activity=activity)
    groups_listed = [None]
    if 'group' in r:
        group = Group.objects.get(id=r['group'])
        groups_listed = group.children() + [group]

    # Limit the number of allocations in response to MAX_ALLOCATIONS
    filters = ['timetable', 'teacher', 'classroom', 'activity', 'group']
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
    Span = namedtuple('Span', ['start', 'duration', 'w', 'action'])
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
                        allocation_tab[j].append(Span(start=last_end,
                                                      duration=new_pre_last_duration,
                                                      w=1,
                                                      action=None))
                    allocation_tab[j].append(Span(start=new_start,
                                                  duration=a.duration,
                                                  w=1,
                                                  action=a))
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
                    l.insert(0, Span(start=0, duration=start_hours[i], w=1, action=None))
                last = l[-1]
                duration = len(whdict) - (last.start + last.duration)
                if duration > 0:
                    if prev_duration == duration:
                        # print to_set, l
                        s = allocation_tab[to_set][-1]
                        allocation_tab[to_set][-1] = Span(start=s.start, duration=s.duration, w=s.w + 1, action=None)
                    else:
                        s = Span(start=last.start + last.duration, duration=duration, w=1, action=None)
                        l.append(s)
                        to_set = i
                prev_duration = duration
        # insert allocations from allocation_tab into allocations_by_hour
        for l in allocation_tab:
            for j in l:
                allocations_by_hour[WORKHOURS[j.start][0]][day].append((j.w, j.duration, j.action))
        space_taken_list.append(allocation_tab)
        max_overlaps_day.append(len(allocation_tab))
    daynames = {"MON": "Ponedeljek", "TUE": 'Torek', "WED": "Sreda",
                "THU": "Četrtek", "FRI": "Petek"}
    day_header = []
    for day in range(len(WEEKDAYS)):
        day_header.append((daynames[WEEKDAYS[day][0]], max_overlaps_day[day]))
    return render(request, 'timetable/allocations.html', {
        'timetable': timetable,
        'teacher': teacher,
        'classroom': classroom,
        'activity': activity,
        'group': group,
        'day_header': day_header,
        'allocations_by_hour': allocations_by_hour.iteritems()})


@login_required
def activity_requirements(request):
    try:
        teacher = request.user.teacher
    except ObjectDoesNotExist:
        teacher = None
    if request.method == 'POST':
        complete_formset = ActivityRequirementsFormset(request.POST, request.FILES, prefix="cmplt-")
        if complete_formset.is_valid():
            complete_formset.save()
        user_formset = ActivityRequirementsFormset(request.POST, request.FILES, prefix="usr-")
        if user_formset.is_valid():
            user_formset.save()
    complete_formset = ActivityRequirementsFormset(prefix="cmplt-",
                                                   queryset=Activity.objects.only('id', 'requirements'))
    if teacher is not None:
        l = []
        activities = teacher.activities.all()
        for a in activities:
            l += a.groups.values_list('id', flat=True)
        qs = Group.objects.filter(id__in=l)

        class AFForm(forms.ModelForm):
            groups = forms.ModelMultipleChoiceField(queryset=qs)

            class Meta:
                model = Activity

        AFS = forms.models.modelformset_factory(Activity, form=ActivityRequirementForm, extra=0, max_num=5,
                                                can_delete=False)
        user_formset = AFS(queryset=teacher.activities.only('id', 'requirements'),
                           initial=[{}] * len(activities) + [{'teachers': [teacher]}], prefix="usr-")
    else:
        user_formset = ActivityRequirementsFormset(prefix="usr-")
    return render(request, 'timetable/activity_requirements.html',
                              {'user_formset': user_formset, 'complete_formset': complete_formset,
                               'teacher': teacher},
                              context_instance=RequestContext(request))


@login_required
def teacher_single_preferences(request, timetable_id=None):
    try:
        teacher = request.user.teacher
        timetable = Timetable.objects.get(id=int(timetable_id))
    except:
        raise Http404
    activities = teacher.activities.all()
    pset = timetable.preferences
    problems = False
    if request.method == 'POST':
        preference_form = TeacherPreferenceForm(request.POST, prefix='pref-')
        actreq_formset = ActivityRequirementsFormset(request.POST, request.FILES, prefix="actreq-")
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
        actreq_formset = ActivityRequirementsFormset(queryset=activities,
                                                     initial=[{}] * len(activities) + [{'teachers': [teacher]}],
                                                     prefix="actreq-")
        preference_form = TeacherPreferenceForm(teacher=teacher, preferenceset=pset, prefix="pref-")
    return render(request, 'timetable/teacher_single_preferences.html',
                              {'form': preference_form,
                               'activity_requirement_formset': actreq_formset,
                               },
                              context_instance=RequestContext(request))


@login_required
def all_teacher_preferences(request):
    r = request.REQUEST
    teachers = Teacher.objects.filter()
    if 'teacher' in r:
        teachers = teachers.filter(id=r['teacher'])
    preference_forms_by_period_teacher = {}
    #            preference_forms_by_period_teacher[p][t] = preference_forms_by_time(r, t, p)
    # restored_preferences = []
    if request.method == 'POST':
        # formset = TeacherPreferenceFormSet(request.POST)
        management_form = formsets.ManagementForm(request.POST)
        # if formset.is_valid():
        #    formset.save()
        if management_form.is_valid():
            for i in range(management_form.cleaned_data['TOTAL_FORMS']):
                tpform = TeacherPreferenceForm(request.POST, prefix='ttpref-{0}'.format(i))
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
                prefix='ttpref-{0}'.format(nforms),
                teacher=t, period=p)
            nforms += 1
        #    formset = TeacherPreferenceFormSet(queryset=TeacherPreference.objects.all())
        management_form = formsets.ManagementForm(initial={'INITIAL_FORMS': nforms,
                                                           'MAX_NUM_FORMS': nforms, 'TOTAL_FORMS': nforms})
        # restored_preferences = TeacherPreference.objects.all()
    return render(request, 'timetable/teacher_formset_preferences.html',
                              {'teachers': teachers, 'periods': periods,
                               'WORKHOURS': WORKHOURS, 'WEEKDAYS': WEEKDAYS,
                               'management_form': management_form,
                               'period_preference_forms': preference_forms_by_period_teacher.iteritems(),
                               },
                              context_instance=RequestContext(request))


@login_required
def group_overview(request):
    return render(request, "friprosveta/group_overview.html",
                              {'object_list': visible_timetables(request)}, context_instance=RequestContext(request))


def group_preference_list(request, timetable_id=None):
    if timetable_id is not None:
        t = Timetable.objects.get(id=timetable_id)
        if timetable_visible(request, t):
            q = t.groups
        else:
            q = Group.objects.none()
    else:
        q = Group.objects.all()
    return ListView(request, queryset=q, template_name="friprosveta/group_list.html", ).as_view()


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
    if request.method == 'POST':
        preference_form = GroupPreferenceForm(request.POST, prefix='pref-')
        preference_form.full_clean()
        if preference_form.is_valid() and (
                not preference_form.preferenceset().locked or request.user.is_staff):
            preference_form.save()
        else:
            problems = True
    if not problems:
        preference_form = GroupPreferenceForm(group=group, preferenceset=pset, prefix="pref-")
    return render(request, 'friprosveta/group_preferences.html',
                  {'form': preference_form,
                   'got_post': got_post,
                   }, context_instance=RequestContext(request))


class ActivityDetailView(DetailView):
    model = Activity


class ActivityUpdateView(UpdateView):
    model = Activity
