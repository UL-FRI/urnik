from django.conf.urls import url, include
import django.views
from django.contrib import admin
from django.contrib.auth.views import login, logout
from dal import autocomplete


admin.autodiscover()

urlpatterns = [
    url(r'^jsi18n/(?P<packages>\S+?)/$', django.views.i18n.javascript_catalog),
    url(r'^', include('friprosveta.urls')),
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^impersonate/', include('impersonate.urls')),
    url(r'^accounts/login/$', login, name='django.contrib.auth.views.login'),
    url(r'^accounts/logout/$', logout),
    url(r'^exchange/', include('exchange.urls')),
] 

