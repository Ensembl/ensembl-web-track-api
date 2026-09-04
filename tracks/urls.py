#
#  See the NOTICE file distributed with this work for additional information
#  regarding copyright ownership.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""
URL Configuration for the Tracks Django app in Ensembl Track API endpoint
"""
from django.urls import path
from . import views

app_name = "tracks"

urlpatterns = [
    # Existing egress endpoints (keeping as-is)
    path(
        "track_categories/<uuid:genome_id>",
        views.GenomeTrackList.as_view(),
        name="genome_tracks_url",
    ),
    path("track/<uuid:track_id>", views.TrackObject.as_view(), name="track_url"),
    path("track", views.TrackObject.as_view(), name="track_url"),
    # New ingress endpoints
    path("tracks/create", views.CreateTrack.as_view(), name="create_track"),
    path("tracks/link_type", views.LinkTypeToTrack.as_view(), name="link_type"),
]
