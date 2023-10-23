from .models import Category, Track, Source
from rest_framework import serializers

"""
Serializers for Track API datamodels
"""

class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ["name", "url"]

class BaseTrackSerializer(serializers.ModelSerializer):
    sources = SourceSerializer(many=True)

    class Meta:
        model = Track
        fields = ["track_id", "label", "colour", "trigger", "type", "display_order", "on_by_default", "sources"]

# track payload in "track_categories" endpoint (consumed by client)
class CategoryTrackSerializer(BaseTrackSerializer):
    class Meta(BaseTrackSerializer.Meta):
        fields = BaseTrackSerializer.Meta.fields + ["additional_info", "description"]

# track payload in "track" endpoint (consumed by genome browser)
class ReadTrackSerializer(BaseTrackSerializer):
    class Meta(BaseTrackSerializer.Meta):
        fields = BaseTrackSerializer.Meta.fields + ["datafiles"]

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["label", "track_category_id", "type"]

# track submission payload
class WriteTrackSerializer(BaseTrackSerializer):
    category = CategorySerializer(write_only=True)

    class Meta(BaseTrackSerializer.Meta):
        fields = BaseTrackSerializer.Meta.fields + ["genome_id", "category", "datafiles", "additional_info", "description"]
    
    def create(self, validated_data):
        category_data = validated_data.pop('category')
        category_id = category_data.pop('track_category_id')
        category, created = Category.objects.get_or_create(track_category_id=category_id, defaults=category_data)
        sources = validated_data.pop('sources')
        track = Track.objects.create(category=category, **validated_data)
        for source in sources:
            Source.objects.create(track=track, **source)
        return track

# payload wrappers in "track_categories" endpoint
class TracksCategorySerializer(CategorySerializer):
    track_list = CategoryTrackSerializer(many=True, read_only=True)

    class Meta:
        fields = CategorySerializer.Meta.fields + ["track_list"]

class CategoryListSerializer(serializers.ModelSerializer):
    track_categories = TracksCategorySerializer(many=True, read_only=True)