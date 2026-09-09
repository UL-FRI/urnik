from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.generic.list import ListView

from rest_framework_nested import routers
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from timetable.models import TimetableSet
from timetable import views as timetable_views

from . import (
    preparation_run_views,
    solver_run_views,
    solver_views,
    studis_workflow_views,
    views,
    restapi,
)

# from .restapi import SubjectDetailsView, SubjectsView

urlpatterns = [
    re_path(r"^$", views.default_timetable_redirect, name="default_timetable"),
    # Staff-only OR-Tools Solver Setup UI.
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/?$",
        solver_views.solver_dashboard,
        name="solver_dashboard",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/constraints/?$",
        solver_views.solver_constraint_list,
        name="solver_constraint_list",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/before-relations/?$",
        solver_views.activity_before_relations,
        name="activity_before_relations",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/modules/?$",
        solver_views.study_module_list,
        name="study_module_list",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/modules/new/?$",
        solver_views.study_module_create,
        name="study_module_create",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/modules/(?P<pk>\d+)/edit/?$",
        solver_views.study_module_edit,
        name="study_module_edit",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/modules/(?P<pk>\d+)/delete/?$",
        solver_views.study_module_delete,
        name="study_module_delete",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/constraints/new/?$",
        solver_views.solver_constraint_create,
        name="solver_constraint_create",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/constraints/(?P<pk>\d+)/edit/?$",
        solver_views.solver_constraint_edit,
        name="solver_constraint_edit",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/constraints/(?P<pk>\d+)/delete/?$",
        solver_views.solver_constraint_delete,
        name="solver_constraint_delete",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/run/?$",
        solver_run_views.solver_run_preview,
        name="solver_run_preview",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/repair/?$",
        solver_run_views.solver_repair_preview,
        name="solver_repair_preview",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/groups/?$",
        solver_views.solver_group_rules,
        name="solver_group_rules",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/automatic-rules/?$",
        solver_views.solver_automatic_rules,
        name="solver_automatic_rules",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/copy-group-time-preferences/?$",
        solver_views.copy_group_time_preferences,
        name="copy_group_time_preferences",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/activities/?$",
        solver_views.solver_scheduling_scope,
        name="solver_scheduling_scope",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/manual-activities/?$",
        solver_views.manual_activity_list,
        name="manual_activity_list",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/manual-activities/new/?$",
        solver_views.manual_activity_edit,
        name="manual_activity_create",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/manual-activities/(?P<pk>\d+)/edit/?$",
        solver_views.manual_activity_edit,
        name="manual_activity_edit",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/windows/?$",
        solver_views.scheduling_windows,
        name="scheduling_windows",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/windows/overrides/?$",
        solver_views.scheduling_window_overrides,
        name="scheduling_window_overrides",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/prepare/?$",
        preparation_run_views.preparation_preview,
        name="preparation_preview",
    ),
    re_path(
        r"^solver/(?P<timetable_slug>[\w-]+)/studis-workflow/?$",
        studis_workflow_views.studis_workflow_preview,
        name="studis_workflow_preview",
    ),
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
    # Trade Request URLs
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/$",
        timetable_views.trade_request_list,
        name="trade_request_list",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/my/$",
        timetable_views.my_trade_requests,
        name="my_trade_requests",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/create/$",
        timetable_views.create_trade_request,
        name="create_trade_request",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/overlaps/$",
        timetable_views.trade_request_allocation_stats,
        name="trade_request_allocation_stats",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/overlaps/free-slot/$",
        timetable_views.trade_request_free_slot_stats,
        name="trade_request_free_slot_stats",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/(?P<pk>\d+)/$",
        timetable_views.trade_request_detail,
        name="trade_request_detail",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/(?P<pk>\d+)/cancel/$",
        timetable_views.cancel_trade_request,
        name="cancel_trade_request",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/(?P<pk>\d+)/respond/$",
        timetable_views.respond_to_trade_request,
        name="respond_to_trade_request",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/(?P<pk>\d+)/reject/$",
        timetable_views.reject_trade_request,
        name="reject_trade_request",
    ),
    re_path(
        r"^timetable/(?P<timetable_slug>[\w-]+)/trades/queue/$",
        timetable_views.trade_match_queue,
        name="trade_match_queue",
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
    re_path(
        r"^cookies/?$",
        TemplateView.as_view(template_name="friprosveta/cookies.html"),
        name="cookies",
    ),
]

router = routers.DefaultRouter()
router.register(r'site', restapi.TimetableSiteViewSet)
router.register(r'timetable', restapi.TimetableViewSet)
timetable_router = routers.NestedDefaultRouter(router, r'timetable', lookup='timetable')
timetable_router.register(r'allocation', restapi.AllocationViewSet)
router.register(r'teacher', restapi.TeacherViewSet)
router.register(r'subject', restapi.SubjectViewSet)
router.register(r'location', restapi.LocationViewSet)
location_router = routers.NestedDefaultRouter(router, r'location', lookup='location')
location_router.register(r'classroom', restapi.ClassroomViewSet)
router.register(r'classroom_set', restapi.ClassroomSetViewSet)
router.register(r'activityset', restapi.ActivitySetViewSet)
activityset_router = routers.NestedDefaultRouter(router, r'activityset', lookup='activityset')
activityset_router.register(r'activity', restapi.ActivityViewSet)

urlpatterns += [
    path("api/", include(router.urls)),
    path("api/", include(timetable_router.urls)),
    path("api/", include(location_router.urls)),
    path("api/", include(activityset_router.urls)),

    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
