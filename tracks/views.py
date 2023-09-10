from tracks.models import Genome, Track
from tracks.serializers import GenomeTracksSerializer, BackendTrackSerializer
from rest_framework import generics


class GenomeTrackList(generics.RetrieveAPIView):
    """
    Retrieve all tracks (grouped to categories) linked to a genome uuid.
    """
    queryset = Genome.objects.all()
    serializer_class = GenomeTracksSerializer
    lookup_field = "genome_id"
    pagination_class = None

class TrackObject(generics.RetrieveAPIView):
    """
    Retrieve a single track object by its track uuid.
    """
    queryset = Track.objects.all()
    serializer_class = BackendTrackSerializer
    lookup_field = "track_id"
    pagination_class = None