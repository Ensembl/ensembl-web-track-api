from tracks.models import Track, Category
from tracks.serializers import ReadTrackSerializer, WriteTrackSerializer, CategorySerializer, CategoryTrackSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import IntegrityError
from ensembl_track_api import settings


class GenomeTrackList(APIView):
    """
    Retrieve or remove all tracks and track categories linked to a genome uuid.
    """
    http_method_names = settings.ALLOWED_METHODS

    def get(self, request, genome_id):
        tracks = Track.objects.filter(genome_id=genome_id)
        if(not tracks.exists()):
            return Response({"error": "No tracks found for this genome."}, status=status.HTTP_404_NOT_FOUND)
        categories = {}
        for track in tracks: #group tracks by category
            if(track.category_id not in categories):
                category_obj = Category.objects.get(id=track.category_id)
                categories[track.category_id] = CategorySerializer(category_obj).data
                categories[track.category_id]["track_list"] = []
            categories[track.category_id]["track_list"].append(CategoryTrackSerializer(track).data)
        return Response({"track_categories": [categories[category_id] for category_id in categories]}, status=status.HTTP_200_OK)
    
    def delete(self, request, genome_id):
        tracks = Track.objects.filter(genome_id=genome_id)
        if(not tracks.exists()):
            return Response({"error": "No tracks found for this genome."}, status=status.HTTP_404_NOT_FOUND)
        tracks.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class TrackObject(APIView):
    """
    Retrieve or create a single track object.
    """
    http_method_names = settings.ALLOWED_METHODS
    
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
            try:
                serializer.save()
            except IntegrityError as e:
                return Response({f"error": "Track already exists: {e}"}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"track_id": serializer.data.get("track_id")}, status=status.HTTP_201_CREATED)
        return Response({"error": f"Payload validation failed: {serializer.errors}"}, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, track_id):
        try:
            track = Track.objects.get(track_id=track_id)
        except Track.DoesNotExist:
            return Response({"error": "No track found with this track id."}, status=status.HTTP_404_NOT_FOUND)
        track.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
