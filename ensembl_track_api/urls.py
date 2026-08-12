"""
URL Configuration for Ensembl Track API endpoint
"""
from django.urls import path, include

urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("", include("tracks.urls", namespace="tracks")),
]
