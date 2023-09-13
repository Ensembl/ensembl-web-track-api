"""
URL Configuration for the Tracks Django app in Ensembl Track API endpoint
"""
from django.urls import path
from . import views

app_name = "tracks"

urlpatterns = [
    path("track_categories/<uuid:genome_id>", views.GenomeTrackList.as_view(), name="genome_tracks"),
    path("track/<uuid:track_id>", views.TrackObject.as_view(), name="track"),
]