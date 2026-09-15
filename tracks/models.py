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

import uuid
from typing import ClassVar

from django.db import models

from .fields import HyphenatedUUIDField

"""
Django datamodels representing tracks in Track API database.
"""


class Category(models.Model):
    class CategoryType(models.TextChoices):
        GENOMIC = "Genomic", "Genomic"
        VARIATION = "Variation", "Variation"
        REGULATION = "Regulation", "Regulation"

    label = models.CharField(max_length=50)
    track_category_id = models.CharField(unique=True, max_length=50)
    type = models.CharField(
        choices=CategoryType.choices,
        default=CategoryType.GENOMIC,
        max_length=20,
    )


class Specifications(models.Model):
    class TrackType(models.TextChoices):
        GENE = "gene", "gene"
        VARIANT = "variant", "variant"
        REGULAR = "regular", "regular"

    class StrandType(models.TextChoices):
        FORWARD = "forward", "forward"
        REVERSE = "reverse", "reverse"

    class BrowserType(models.TextChoices):
        GENOME_BROWSER = "GenomeBrowser", "GenomeBrowser"
        STRUCTURAL_VARIANT = "StructuralVariant", "StructuralVariant"

    name = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=50)

    category = models.ForeignKey(
        Category,
        related_name="tracks",
        on_delete=models.CASCADE,
    )

    trigger = models.JSONField(default=list)

    type = models.CharField(
        choices=TrackType.choices,
        max_length=8,
    )

    on_by_default = models.BooleanField(default=False)
    display_order = models.IntegerField(default=2000)
    additional_info = models.CharField(blank=True, default="", max_length=50)
    description = models.TextField(blank=True, default="")
    settings = models.JSONField(blank=True, default=dict)
    files = models.JSONField(default=list)

    strand = models.CharField(
        choices=StrandType.choices,
        max_length=20,
        blank=True,
        null=True,
    )

    browser = models.CharField(
        choices=BrowserType.choices,
        max_length=20,
    )


class Track(models.Model):
    specifications: models.ManyToManyField = models.ManyToManyField(
        Specifications,
        related_name="tracks",
    )
    sources: models.ManyToManyField = models.ManyToManyField(
        "Source",
        related_name="tracks",
    )

    track_id = HyphenatedUUIDField(
        unique=True,
        editable=False,
        default=uuid.uuid4,
    )
    dataset_id = HyphenatedUUIDField()
    genome_id = HyphenatedUUIDField()
    datafiles = models.JSONField(default=dict)

    class Meta:
        indexes: ClassVar = [
            models.Index(fields=["dataset_id"]),
            models.Index(fields=["genome_id", "dataset_id"]),
        ]


class Source(models.Model):
    name = models.CharField(max_length=100)
    url = models.URLField()
    details = models.CharField(max_length=100)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["name", "url", "details"], name="unique_source"
            )
        ]


class DatasetRelease(models.Model):
    dataset_id = HyphenatedUUIDField()
    genome_id = HyphenatedUUIDField()
    release_label = models.CharField(max_length=50)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["dataset_id", "genome_id", "release_label"],
                name="unique_dataset_genome_release",
            )
        ]
        indexes: ClassVar = [
            models.Index(fields=["genome_id", "-release_label"]),
        ]
