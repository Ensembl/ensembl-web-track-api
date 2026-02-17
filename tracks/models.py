import uuid

from django.db import models

"""
Django datamodels representing tracks in Track API database.
"""


class Category(models.Model):
    label = models.CharField(max_length=50)
    track_category_id = models.CharField(unique=True, max_length=50)
    CategoryType = models.TextChoices("CategoryType", ["Genomic", "Variation", "Regulation"])
    type = models.CharField(choices=CategoryType.choices, default="Genomic", max_length=20)


class Type(models.Model):
    name = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=50)
    category = models.ForeignKey(Category, related_name="tracks", on_delete=models.CASCADE)
    trigger = models.JSONField(default=list)
    TrackType = models.TextChoices("TrackType", ["gene", "variant", "regular"])
    type = models.CharField(choices=TrackType.choices, max_length=8)
    colour = models.CharField(blank=True, default="", max_length=20)
    on_by_default = models.BooleanField(default=False)
    display_order = models.IntegerField(default=2000)
    additional_info = models.CharField(blank=True, default="", max_length=50)
    description = models.TextField(blank=True, default="")
    settings = models.JSONField(blank=True, default=dict)
    files = models.JSONField(default=list)
    StrandType = models.TextChoices("StrandType", ["forward", "reverse"])
    strand = models.CharField(choices=StrandType.choices, max_length=20, blank=True, null=True)
    BrowserType = models.TextChoices("BrowserType", ["GenomeBrowser", "StructuralVariant"])
    browser = models.CharField(choices=BrowserType.choices, max_length=20)


class Track(models.Model):
    type = models.ManyToManyField(Type, related_name="types")
    track_id = models.UUIDField(unique=True, editable=False, default=uuid.uuid4)
    dataset_id = models.UUIDField()
    genome_id = models.UUIDField()
    datafiles = models.JSONField(default=dict)


class Source(models.Model):
    track = models.ManyToManyField(Track, related_name="sources")  # TODO: Do we want this track or track type? See with
    name = models.CharField(max_length=100)
    url = models.URLField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["name", "url"], name="unique_source")]
