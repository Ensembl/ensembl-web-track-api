#!/usr/bin/env python
import django
import os
import sys
import yaml

# import modules from parent directory
sys.path.insert(1, os.path.join(sys.path[0], ".."))
if __name__ == "__main__":
    # use data models outside the Django app
    django.setup()

from tracks.models import Genome, Category, CategoryType, Track

"""
Script for importing track categories data from a yaml file.
Sample input: ./data/track_categories.yaml
Target data models: ./tracks/models.py
Data structure: Genome => [Category => [Track, ...], ...], Genome => ...
Clean existing database before data import: python manage.py flush
"""

yaml_file = "data/track_categories.yaml"
if len(sys.argv) > 1:
    if "." in sys.argv[1]:
        yaml_file = sys.argv[1]
    else:
        print(
            "Data importer for track API endpoint.\nUsage:",
            sys.argv[0],
            " <input_file.yaml>",
        )

print("Importing", yaml_file)

with open(yaml_file) as f:
    try:
        data = yaml.safe_load(f)
    except yaml.parser.ParserError as e:
        sys.exit("Failed to parse yaml file: " + str(e))

    try:
        data = data["genome_track_categories"]
        for genome_id in data.keys():
            print("Adding genome", genome_id)
            # does get() => [create() => save()]
            genome_obj, created = Genome.objects.get_or_create(genome_id=genome_id)
            if not created:
                sys.exit(
                    "Genome ID '%s' already imported!\nEmpty the database before running data import: ./manage.py flush"
                    % genome_id
                )
            categories = data[genome_id]
            for category in categories:
                category_obj = Category.objects.create(
                    label=category["label"],
                    track_category_id=category["track_category_id"],
                    genome=genome_obj,
                )
                for type in category["types"]:
                    # reuse stored category types
                    category_type_obj, created = CategoryType.objects.get_or_create(
                        type=type
                    )
                    # link Category to CategoryType
                    category_obj.types.add(category_type_obj)
                for track in category["track_list"]:
                    track_obj = Track.objects.create(
                        label=track["label"],
                        track_id=track["track_id"],
                        category=category_obj,
                    )
                    # fill optional fields
                    for field in ["colour", "additional_info"]:
                        if field in track:
                            setattr(track_obj, field, track[field])
                    track_obj.save()
    except KeyError as e:
        print("Missing data field:", e)

    print("Done!")
