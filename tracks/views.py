from tracks.models import Genome
from tracks.serializers import GenomeTracksSerializer
from rest_framework import generics


class GenomeTrackList(generics.RetrieveAPIView):
    """
    Retrieve a list of tracks (in categories) linked to a genome id.
    """
    queryset = Genome.objects.all()
    serializer_class = GenomeTracksSerializer
    lookup_field = "genome_id"
    pagination_class = None