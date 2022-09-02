from .models import Genome, Category, CategoryType, Track
from rest_framework import serializers

"""
DRF Serializers corresponding to tracks app datamodels
"""


class TrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Track
        fields = ["colour", "label", "track_id", "additional_info", "description", "sources"]


class CategorySerializer(serializers.ModelSerializer):
    types = serializers.StringRelatedField(many=True, read_only=True)
    track_list = TrackSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ["label", "track_category_id", "types", "track_list"]


class GenomeTracksSerializer(serializers.ModelSerializer):
    track_categories = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Genome
        fields = ["track_categories"]
