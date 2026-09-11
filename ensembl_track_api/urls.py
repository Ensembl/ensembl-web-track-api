"""
URL Configuration for Ensembl Track API endpoint
"""

from django.urls import include, path

urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("", include("tracks.urls", namespace="tracks")),
]
