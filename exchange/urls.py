from django.conf.urls import url
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    # general
    url(r'^$', views.main_redirect, name='main_redirect_root'),
    url(r'^(?P<timetable_slug>[\w-]+)/$', views.main_redirect_with_timetable, name='main_redirect_timetable'),

    url(r'^help/?$', TemplateView.as_view(template_name="exchange/exchange_create_help.html"), name='exchange_create_help'),

    # mixed student-teacher
    url(r'^(?P<timetable_slug>[\w-]+)/cancel/(?P<exchange_id>\d+)/?$', views.cancel_exchange, name='cancel_exchange'),

    # student-only
    url(r'^(?P<timetable_slug>[\w-]+)/student/?$', views.landing_student, name='landing_student'),
    url(r'^(?P<timetable_slug>[\w-]+)/student/create/?$', views.create_exchange_student, name='create_exchange_student'),
    url(r'^(?P<timetable_slug>[\w-]+)/student/accept/(?P<exchange_id>\d+)/?$', views.accept_exchange, name='accept_exchange'),

    # teacher-only
    url(r'^(?P<timetable_slug>[\w-]+)/teacher/$', views.landing_teacher, name='landing_teacher'),
    url(r'^(?P<timetable_slug>[\w-]+)/teacher/manage/(?P<subject_code>[\d\w\-_]+)/?$',
        views.subject_management, name='subject_management'),
    url(r'^(?P<timetable_slug>[\w-]+)/teacher/manage/(?P<subject_code>[\d\w\-_]+)/create/?$',
        views.create_exchange_teacher, name='create_exchange_teacher'),
]
