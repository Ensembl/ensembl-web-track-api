from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid

"""
Django datamodels representing tracks in Track API database.
"""

class Category(models.Model):
    label = models.CharField(max_length=50)
    track_category_id = models.CharField(unique=True, max_length=50)
    CategoryType = models.TextChoices("CategoryType", ["Genomic","Variation","Regulation"])
    type = models.CharField(choices=CategoryType.choices, default="Genomic", max_length=20)

class Track(models.Model):
    track_id = models.UUIDField(unique=True, editable=False, default=uuid.uuid4) #auto-generate track IDs
    genome_id = models.UUIDField()
    category = models.ForeignKey(Category, related_name="tracks", on_delete=models.CASCADE)
    label = models.CharField(max_length=50)
    trigger = ArrayField(models.CharField(max_length=50))
    TrackType = models.TextChoices("TrackType", ["gene","variant","regular"])
    type = models.CharField(choices=TrackType.choices, max_length=20)
    datafiles = models.JSONField(default=dict)
    colour = models.CharField(blank=True, default="", max_length=20)
    on_by_default = models.BooleanField(default=False)
    display_order = models.IntegerField(null=True)
    additional_info = models.CharField(blank=True, default="", max_length=50)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["display_order"]
        constraints = [models.UniqueConstraint(fields=["genome_id", "label", "additional_info", "datafiles"], name="unique_track")]

class Source(models.Model):
    track = models.ManyToManyField(Track, related_name="sources")
    name = models.CharField(max_length=50)
    url = models.URLField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["name", "url"], name="unique_source")]
