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

from .models import Category, Track, Source, Specifications
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
        3. All types are for DIFFERENT browsers (can't have multiple specs for same browser on one track)
        """
        # Check all types exist
        types = Specifications.objects.filter(name__in=value)
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

        # Check all are for DIFFERENT browsers
        browsers = list(types.values_list('browser', flat=True))
        if len(browsers) != len(set(browsers)):
            raise serializers.ValidationError(
                "Cannot link multiple specifications for the same browser to one track. "
                "Each track can only have one specification per browser type."
            )

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
            track.specifications.add(type_obj)

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
            track = Track.objects.prefetch_related('specifications').get(track_id=data['track_id'])
        except Track.DoesNotExist:
            raise serializers.ValidationError({"track_id": "Track not found"})

        # Check type exists
        try:
            new_type = Specifications.objects.get(name=data['type_name'])
        except Specifications.DoesNotExist:
            raise serializers.ValidationError({"type_name": "Type not found"})

        # Check if type already linked
        if track.specifications.filter(id=new_type.id).exists():
            raise serializers.ValidationError(
                {"type_name": "Type already linked to this track"}
            )

        # Check if files match existing types
        existing_types = track.specifications.all()
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
        track.specifications.add(new_type)
        return track

class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ["name", "url"]
        validators = []


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["label", "track_category_id", "type"]
        extra_kwargs = {
            "track_category_id": {"validators": []}
        }


# Changed from ModelSerializer to Serializer
class BaseTrackSerializer(serializers.Serializer):
    """Output format for track data (combines Track + Specification)."""
    track_id = serializers.UUIDField()
    label = serializers.CharField()
    trigger = serializers.ListField()
    type = serializers.CharField()
    display_order = serializers.IntegerField()
    on_by_default = serializers.BooleanField()
    sources = SourceSerializer(many=True)


class CategoryTrackSerializer(BaseTrackSerializer):
    """For /track_categories endpoint - adds description fields."""
    additional_info = serializers.CharField()
    description = serializers.CharField()


class ReadTrackSerializer(BaseTrackSerializer):
    """For /track/{id} endpoint - adds datafiles and settings."""
    datafiles = serializers.DictField()
    settings = serializers.DictField()
