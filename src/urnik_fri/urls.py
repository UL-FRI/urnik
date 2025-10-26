import django.views
from django.urls import include, re_path
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView

admin.autodiscover()

urlpatterns = [
    # url(r'^jsi18n/(?P<packages>\S+?)/$', django.views.i18n.javascript_catalog),
    re_path(r"^jsi18n/", django.views.i18n.JavaScriptCatalog.as_view()),
    re_path(r"^", include("friprosveta.urls")),
    re_path(r"^admin/doc/", include("django.contrib.admindocs.urls")),
    re_path(r"^admin/", admin.site.urls),
    re_path(r"^impersonate/", include("impersonate.urls")),
    re_path(
        r"^accounts/login/$",
        LoginView.as_view(),
        name="django.contrib.auth.views.login",
    ),
    re_path(r"^accounts/logout/$", LogoutView.as_view()),
    re_path(r"^exchange/", include("exchange.urls")),
]
