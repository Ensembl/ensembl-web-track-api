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

from .models import Category, Track, Source, Type
from rest_framework import serializers


class CreateTrackSerializer(serializers.Serializer):
    """
    Serializer for creating new tracks.
    Validates UUIDs, datafiles, and track_types compatibility.
    """
    dataset_id = serializers.UUIDField()
    genome_id = serializers.UUIDField()
    datafiles = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        max_length=2,
        help_text="List of 1-2 file paths"
    )
    track_types = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        help_text="List of Type names to associate with this track"
    )

    def validate_track_types(self, value):
        """
        Validate that:
        1. All type names exist
        2. All types have the same files list
        """
        # Check all types exist
        types = Type.objects.filter(name__in=value)
        if types.count() != len(value):
            found = set(types.values_list('name', flat=True))
            missing = set(value) - found
            raise serializers.ValidationError(
                f"Type(s) not found: {', '.join(missing)}"
            )

        # Check all have same files list
        files_lists = list(types.values_list('files', flat=True))
        first_files = files_lists[0]

        if not all(files == first_files for files in files_lists):
            raise serializers.ValidationError(
                "All track_types must have the same files list. "
                f"Found different files configurations across types."
            )

        # Store types for later use in create()
        self.context['validated_types'] = types
        return value

    def validate_datafiles(self, value):
        """Ensure at least one file is provided."""
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one datafile is required")
        if len(value) > 2:
            raise serializers.ValidationError("Maximum 2 datafiles allowed")
        return value

    def create(self, validated_data):
        """
        Create Track and link to Types.
        Build datafiles dict from list, filling empty strings for missing files.
        """
        dataset_id = validated_data['dataset_id']
        genome_id = validated_data['genome_id']
        datafiles_list = validated_data['datafiles']
        track_types = validated_data['track_types']

        # Get the files keys from the first type
        types = self.context['validated_types']
        first_type = types.first()
        files_keys = first_type.files

        # Build datafiles dict
        # If we get 1 file: {"key1": "file.bb", "key2": ""}
        # If we get 2 files: {"key1": "file1.bb", "key2": "file2.bw"}
        datafiles = {}
        for i, key in enumerate(files_keys):
            if i < len(datafiles_list):
                datafiles[key] = datafiles_list[i]
            else:
                datafiles[key] = ""

        track = Track.objects.create(
            dataset_id=dataset_id,
            genome_id=genome_id,
            datafiles=datafiles
        )
        for type_obj in types:
            track.type.add(type_obj)

        return track


class LinkTypeToTrackSerializer(serializers.Serializer):
    """
    Serializer for linking an additional Type to an existing Track.
    Validates that the Type's files match the Track's existing Types.
    """
    track_id = serializers.UUIDField()
    type_name = serializers.CharField()

    def validate(self, data):
        """
        Validate:
        1. Track exists
        2. Type exists
        3. Type not already linked
        4. Type's files match existing types' files
        """
        # Check track exists
        try:
            track = Track.objects.prefetch_related('type').get(track_id=data['track_id'])
        except Track.DoesNotExist:
            raise serializers.ValidationError({"track_id": "Track not found"})

        # Check type exists
        try:
            new_type = Type.objects.get(name=data['type_name'])
        except Type.DoesNotExist:
            raise serializers.ValidationError({"type_name": "Type not found"})

        # Check if type already linked
        if track.type.filter(id=new_type.id).exists():
            raise serializers.ValidationError(
                {"type_name": "Type already linked to this track"}
            )

        # Check if files match existing types
        existing_types = track.type.all()
        if existing_types.exists():
            existing_files = existing_types.first().files
            if new_type.files != existing_files:
                raise serializers.ValidationError(
                    {"type_name": f"Type files {new_type.files} do not match "
                                  f"track's existing types files {existing_files}"}
                )

        data['track'] = track
        data['type'] = new_type
        return data

    def create(self, validated_data):
        """Link the type to the track."""
        track = validated_data['track']
        new_type = validated_data['type']
        track.type.add(new_type)
        return track






"""
Serializers for Track API datamodels
"""

class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ["name", "url"]
        validators = []

class BaseTrackSerializer(serializers.ModelSerializer):
    sources = SourceSerializer(many=True, required=False)

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
        fields = BaseTrackSerializer.Meta.fields + ["datafiles", "settings"]

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["label", "track_category_id", "type"]
        extra_kwargs = {
            "track_category_id": {"validators": []}
        }

# track submission payload
class WriteTrackSerializer(BaseTrackSerializer):
    category = CategorySerializer(write_only=True)

    class Meta(BaseTrackSerializer.Meta):
        fields = BaseTrackSerializer.Meta.fields + ["genome_id", "category", "datafiles", "additional_info", "description", "settings"]
        extra_kwargs = {
            "genome_id": {"write_only": True}
        }
        validators = [] # ignore uniqueness constraint
    
    def create(self, validated_data):
        category_data = validated_data.pop('category')
        category_id = category_data.pop('track_category_id')
        category_obj, created = Category.objects.get_or_create(track_category_id=category_id, defaults=category_data)
        sources = validated_data.pop('sources') if 'sources' in validated_data else []
        track_obj, created = Track.objects.update_or_create(
            category=category_obj,
            genome_id=validated_data["genome_id"],
            label=validated_data["label"],
            additional_info=validated_data.get("additional_info",""),
            datafiles=validated_data["datafiles"],
            defaults=validated_data
        )
        if(track_obj.trigger[1].startswith("expand")): #hack for expansion tracks
            track_obj.trigger.append(track_obj.track_id)
            track_obj.save()
        for source in sources:
            source_obj, created = Source.objects.get_or_create(**source)
            track_obj.sources.add(source_obj)
        return track_obj
