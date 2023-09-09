"""
URL Configuration for Ensembl Track API endpoint
"""
from django.urls import path, include

urlpatterns = [
    path("", include("tracks.urls", namespace="tracks")),
]
