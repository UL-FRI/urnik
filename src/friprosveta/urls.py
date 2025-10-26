from django.urls import re_path
from django.views.generic import TemplateView
from django.views.generic.list import ListView

from timetable.models import TimetableSet

from . import views

# from .restapi import SubjectDetailsView, SubjectsView

urlpatterns = [
    re_path(r"^$", views.default_timetable_redirect, name="default_timetable"),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/allocations.json",
        views.allocations_json,
        name="allocations_json",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/realizations.json",
        views.realizations_json,
        name="realizations_json",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/allocations_edit",
        views.allocations_edit,
        name="allocations_edit",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/allocations/?$",
        views.allocations,
        name="allocations",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/allocations_ical",
        views.allocations_ical,
        name="allocations_ical",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/authenticated_allocations",
        views.authenticated_allocations,
        {},
        name="authenticated_allocations",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/problematic_allocations",
        views.problematic_allocations,
        {},
        name="problematic_allocations",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/realization/$",
        views.UnplacedRealizationsList.as_view(),
        {},
        name="unplaced_realizations",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/realization/(?P<realization_id>[0-9]+)/$",
        views.busy_students,
        {},
        name="busy_students",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/realization/(?P<realization_id>[0-9]+)/students_list$",
        views.students_list,
        {},
        name="students_list",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/realization/(?P<realization_id>[0-9]+)/students_list\.json$",
        views.students_list_json,
        {},
        name="students_list_json",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/realization/(?P<realization_id>[0-9]+)/busy_students_admin",
        views.busy_students_admin,
        {},
        name="busy_students_admin",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/realization/(?P<realization_id>[0-9]+)/place",
        views.place_realization,
        {},
        name="place_realization",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/?", views.results, {}, name="results"
    ),
    re_path(r"^timetable/?", views.TimetableList.as_view(), name="timetables"),
    # Gregor
    # (r'^najave/(?P<timetable_set_slug>[\w-]+)/subjects/(?P<subject_code>[\w-]+)/$', 'subject'),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/subjects/(?P<subject_code>[0-9A-Z]+)/?$",
        views.subject,
        {},
        name="subject",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/subjects/(?P<subject_code>[0-9A-Z]+)/activity/(?P<pk>[\d]+)/?$",
        views.SubjectActivityDetail.as_view(),
        {},
        name="subject",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/subjects/(?P<subject_code>[0-9A-Z]+)/activity/(?P<pk>[\d]+)/update$",
        views.SubjectActivityUpdate.as_view(),
        {},
        name="subject",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/subjects/(?P<subject_code>[0-9A-Z]+)/activity/(?P<pk>[\d]+)/create$",
        views.SubjectActivityCreate.as_view(),
        {},
        name="subject",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/subjects/(?P<subject_code>[0-9A-Z]+)/activity/(?P<pk>[\d]+)/delete$",
        views.SubjectActivityDelete.as_view(),
        {},
        name="subject",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/subjects/?",
        views.subject_list,
        {},
        name="subject_list",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/assignments/(?P<subject_code>[\w-]+)",
        views.assignments,
        {},
        name="assignments",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/assignments_table/?",
        views.teacher_hours_table,
        {},
        name="teacher_hours_table",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/assignments/?",
        views.teacher_hours,
        {},
        name="teacher_hours",
    ),
    re_path(
        r"^najave/(?P<timetable_slug>[\w-]+)/?",
        TemplateView.as_view(template_name="friprosveta/najave_list.html"),
    ),
    re_path(
        r"^najave/?",
        ListView.as_view(queryset=TimetableSet.objects.all()),
        {},
        name="najave_timetables",
    ),
    re_path(
        r"^preferences/(?P<timetable_slug>[\w-]+)/teacher_preferences/(?P<teacher_id>\d+)/?$",
        views.teacher_single_preferences,
        {},
        name="teacher_single_preferences",
    ),
    re_path(
        r"^preferences/(?P<timetable_slug>[\w-]+)/teacher_preferences/?$",
        views.teacher_preference_list,
        {},
        name="teacher_preference_list",
    ),
    re_path(
        r"^preferences/(?P<timetable_slug>[\w-]+)/my_preferences/?$",
        views.teacher_preference_redirect,
        {},
        name="my_preferences",
    ),
    re_path(
        r"^preferences/(?P<timetable_slug>[\w-]+)/group_preferences/(?P<group_id>\d+)/?$",
        views.group_single_preferences,
        {},
        name="group_single_preferences",
    ),
    re_path(
        r"^preferences/(?P<timetable_slug>[\w-]+)/group_preferences/?$",
        views.GroupListView.as_view(),
        {},
        name="group_preference_list",
    ),
    re_path(
        r"^preferences/(?P<timetable_slug>[\w-]+)/tag_preferences/(?P<tag_id>\d+)/?$",
        views.tag_time_preferences,
        {},
        name="tag_time_preferences",
    ),
    re_path(
        r"^preferences/(?P<timetable_slug>[\w-]+)/tag_preferences/?$",
        views.TagListView.as_view(),
        {},
        name="tag_preference_list",
    ),
    re_path(
        r"^preferences/(?P<timetable_slug>[\w-]+)/?$",
        TemplateView.as_view(template_name="friprosveta/preference_types_list.html"),
        {},
        name="preferences",
    ),
    re_path(
        r"^preferences/?$",
        views.TimetableList.as_view(),
        {},
        name="preference_set_list",
    ),
    # (r'^my_preferences/(?P<timetable_id>\d+)/$', 'teacher_single_preferences'),
    # (r'^/my_preferences/$', 'teacher_single_preferences'),
    # (r'^others_preferences/overview/(?P<timetable_id>\d+)/$', 'teacher_requirements_list'),
    # (r'^others_preferences/overview/(?P<timetable_id>\d+)/(?P<teacher_id>\d+)/$', 'teacher_single_preferences'),
    # (r'^/subjects/timetables/(?P<timetable_set_slug>[\w-]+)/$', 'subject_list'),
    # (r'^/subjects/timetables/(?P<timetable_set_slug>[\w-]+)/(?P<subject_code>[\w-]+)/$', 'subject'),
    # (r'^/teacher_hours/timetables/(?P<timetable_set_slug>[\w-]+)/$', 'teacher_hours'),
    # (r'^/assignments/timetables/(?P<timetable_set_slug>[\w-]+)/(?P<subject_code>[\w-]+)/$', 'assignments'),
    #    re_path(r'^subjects/(?P<subject_code>\d+)/$', 'problems', name='subject'),
    #    re_path(r'^assignments$', 'problems', name='assignments'),
    # (r'^tag_preferences/(?P<tag_id>\d+)/time/$', 'tag_time_preferences'),
    # (r'^tag_preferences/$', 'tag_preference_list'),
    #    re_path(r'^teacher_preferences/$', 'object_list',
    #        {'queryset':Timetable.objects.all(),
    #        'template_name':'timetable/timetable_teacherpreference_list.html'}, "preference_timetables"),
    re_path(r"^allocations.json$", views.allocations_json),
    re_path(r"^allocations$", views.allocations),
    re_path(
        r"^faq$",
        TemplateView.as_view(template_name="friprosveta/faq.html"),
        {},
        name="faq",
    ),
    # re_path(r'^api/subject/?$', SubjectsView.as_view()),
    # re_path(r'^api/subject/(?P<code>[0-9]+[A-B]?)/?$', SubjectDetailsView.as_view()),
    re_path(
        r"^cookies/?$",
        TemplateView.as_view(template_name="friprosveta/cookies.html"),
        name="cookies",
    ),
]
