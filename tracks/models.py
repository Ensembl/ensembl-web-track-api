from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid

"""
Django datamodels representing tracks in Track API database.
"""

class Category(models.Model):
    label = models.CharField(max_length=50)
    track_category_id = models.CharField(unique=True, max_length=50)
    category_type = models.CharField(models.TextChoices('CategoryType', ['Genomic','Variation','Regulation']), max_length=20)

class Track(models.Model):
    track_id = models.UUIDField(unique=True, default=uuid.uuid4) #auto-generate track IDs
    genome_id = models.UUIDField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    label = models.CharField(max_length=50)
    trigger = ArrayField(models.CharField(max_length=50))
    type = models.CharField(models.TextChoices('TrackType', ['gene','variant','regular']), max_length=20)
    datafiles = models.JSONField(default=dict)
    colour = models.CharField(max_length=20, blank=True, default="")
    on_by_default = models.BooleanField(default=False)
    display_order = models.IntegerField(null=True)
    additional_info = models.CharField(blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ['id'] #order tracks by its insertion order
        constraints = [models.UniqueConstraint(fields=['genome_id', 'label', 'datafiles'])]

class Source(models.Model):
    track = models.ManyToManyField(Track, related_name="sources")
    name = models.CharField(max_length=50)
    url = models.URLField()
