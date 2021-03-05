from django.http import HttpResponse, JsonResponse

# from rest_framework.parsers import JSONParser
from tracks.models import Genome
from tracks.serializers import GenomeTracksSerializer

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def genome_tracks(request, genome_id):
    """
    Retrieve a list of tracks (in categories) linked to a genome id.
    """
    try:
        genome_tracks = Genome.objects.get(genome_id=genome_id)
    except Genome.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        serializer = GenomeTracksSerializer(genome_tracks)
        return JsonResponse(serializer.data)
    else:
        return Response(status=status.HTTP_400_BAD_REQUEST)