from django.conf.urls import *

from . import views

urlpatterns = [
    url(r'^$', views.index, 'index'),
    url(r'^allocations$', views.allocations, 'allocations'),
    url(r'^oldallocations$', views.oldallocations, 'oldallocations'),
    url(r'^results$', views.results, 'results'),
    url(r'^teacher_preferences/(?P<timetable_id>\d+)/$', views.teacher_single_preferences, 'teacher_single_preferences'),
    url(r'^activity_requirements$', views.activity_requirements, 'activity_requirements'),
]
