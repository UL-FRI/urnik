import django.views
from django.conf.urls import include, url
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView

admin.autodiscover()

urlpatterns = [
    # url(r'^jsi18n/(?P<packages>\S+?)/$', django.views.i18n.javascript_catalog),
    url(r"^jsi18n/", django.views.i18n.JavaScriptCatalog.as_view()),
    url(r"^", include("friprosveta.urls")),
    url(r"^admin/doc/", include("django.contrib.admindocs.urls")),
    url(r"^admin/", admin.site.urls),
    url(r"^impersonate/", include("impersonate.urls")),
    url(
        r"^accounts/login/$",
        LoginView.as_view(),
        name="django.contrib.auth.views.login",
    ),
    url(r"^accounts/logout/$", LogoutView.as_view()),
    url(r"^exchange/", include("exchange.urls")),
]
