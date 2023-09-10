from .models import Genome, Category, Track, Source
from rest_framework import serializers

"""
DRF Serializers corresponding to tracks app datamodels
"""

class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ["name", "url"]


class ClientTrackSerializer(serializers.ModelSerializer):
    sources = SourceSerializer(many=True, read_only=True)

    class Meta:
        model = Track
        fields = ["label", "track_id", "colour", "trigger", "type",
            "display_order", "on_by_default", "additional_info", "description", "sources"]

class BackendTrackSerializer(serializers.ModelSerializer):
    sources = SourceSerializer(many=True, read_only=True)

    class Meta:
        model = Track
        fields = ["label", "track_id", "colour", "trigger", "type", "datafiles",
            "display_order", "on_by_default"]


class CategorySerializer(serializers.ModelSerializer):
    types = serializers.StringRelatedField(many=True)
    track_list = ClientTrackSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ["label", "track_category_id", "types", "track_list"]


class GenomeTracksSerializer(serializers.ModelSerializer):
    track_categories = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Genome
        fields = ["track_categories"]
