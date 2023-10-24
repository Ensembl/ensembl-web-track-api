from tracks.models import Track
from tracks.serializers import ReadTrackSerializer, WriteTrackSerializer, CategoryListSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class GenomeTrackList(APIView):
    """
    Retrieve or remove all tracks and track categories linked to a genome uuid.
    """
    def get(self, request, genome_id):
        tracks = Track.objects.filter(genome_id=genome_id)
        if(not tracks.exists()):
            return Response({"error": "No tracks found for this genome."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategoryListSerializer(tracks, many=True) #group track lists to categories
        return Response(serializer.data)
    
    def delete(self, request, genome_id): #delete all tracks linked to a genome uuid
        tracks = Track.objects.filter(genome_id=genome_id)
        if(not tracks.exists()):
            return Response({"error": "No tracks found for this genome."}, status=status.HTTP_404_NOT_FOUND)
        tracks.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class TrackObject(APIView):
    """
    Retrieve or create a single track object.
    """
    def get(self, request, track_id):
        try:
            track = Track.objects.get(track_id=track_id)
        except Track.DoesNotExist:
            return Response({"error": "No track found with this track id."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ReadTrackSerializer(track)
        return Response(serializer.data)
    
    def post(self, request):
        serializer = WriteTrackSerializer(data=request.data)
        if(serializer.is_valid()):
            serializer.save()
            return Response({"track id": serializer.data.get("track_id")}, status=status.HTTP_201_CREATED)
        return Response(f"Payload validation error: {serializer.errors}", status=status.HTTP_400_BAD_REQUEST)