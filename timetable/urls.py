from django.conf.urls import *

from . import views

urlpatterns = [
    url(r"^$", views.index, "index"),
    url(r"^allocations$", views.allocations, "allocations"),
    url(r"^results$", views.results, "results"),
    url(
        r"^activity_requirements$", views.activity_requirements, "activity_requirements"
    ),
    
    # Trade Request URLs
    url(r"^trades/$", views.trade_request_list, name="trade_request_list"),
    url(r"^trades/my/$", views.my_trade_requests, name="my_trade_requests"),
    url(r"^trades/create/$", views.create_trade_request, name="create_trade_request"),
    url(r"^trades/overlaps/$", views.trade_request_allocation_stats, name="trade_request_allocation_stats"),
    url(r"^trades/overlaps/free-slot/$", views.trade_request_free_slot_stats, name="trade_request_free_slot_stats"),
    url(r"^trades/(?P<pk>\d+)/$", views.trade_request_detail, name="trade_request_detail"),
    url(r"^trades/(?P<pk>\d+)/cancel/$", views.cancel_trade_request, name="cancel_trade_request"),
    url(r"^trades/(?P<pk>\d+)/respond/$", views.respond_to_trade_request, name="respond_to_trade_request"),
    url(r"^trades/(?P<pk>\d+)/reject/$", views.reject_trade_request, name="reject_trade_request"),
    url(r"^trades/queue/$", views.trade_match_queue, name="trade_match_queue"),
]
