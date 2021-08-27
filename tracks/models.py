from django.db import models

"""
Database models for storing track category lists.
Structure: Genome => [Category => [Track, ...], ...], Genome => ...
Sample data: data/track_categories.yaml
"""


class Genome(models.Model):
    genome_id = models.CharField(max_length=100, unique=True)


class Category(models.Model):
    genome = models.ForeignKey(
        Genome, related_name="track_categories", on_delete=models.CASCADE
    )
    label = models.CharField(max_length=100)
    track_category_id = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        ordering = ['id']


class CategoryType(models.Model):
    category = models.ManyToManyField(Category, related_name="types")
    type = models.CharField(
        max_length=30, unique=True
    )  # type = 'Genomic'|'Expression'|'Variation'

    def __str__(self):
        return str(self.type)


class Track(models.Model):
    category = models.ForeignKey(
        Category, related_name="track_list", on_delete=models.CASCADE
    )
    colour = models.CharField(max_length=30, blank=True, default="")
    label = models.CharField(max_length=100)
    track_id = models.CharField(max_length=100)
    additional_info = models.TextField(blank=True, default="")

    class Meta:
        ordering = ['id']
