# Generated by Django 4.1.11 on 2023-09-13 14:30

import django.contrib.postgres.fields
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("label", models.CharField(max_length=100)),
                (
                    "track_category_id",
                    models.CharField(blank=True, default="", max_length=100),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Genome",
            fields=[
                (
                    "genome_id",
                    models.UUIDField(
                        default=uuid.uuid4, primary_key=True, serialize=False
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Track",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("colour", models.CharField(blank=True, default="", max_length=30)),
                ("label", models.CharField(max_length=100)),
                ("track_id", models.UUIDField(default=uuid.uuid4)),
                (
                    "trigger",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=50), size=None
                    ),
                ),
                ("type", models.CharField(max_length=50)),
                ("datafiles", models.JSONField(default=dict)),
                ("on_by_default", models.BooleanField(default=False)),
                ("display_order", models.IntegerField(null=True)),
                ("additional_info", models.TextField(blank=True, default="")),
                ("description", models.TextField(blank=True, default="")),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="track_list",
                        to="tracks.category",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Source",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("url", models.URLField()),
                (
                    "track",
                    models.ManyToManyField(related_name="sources", to="tracks.track"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CategoryType",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("type", models.CharField(max_length=30, unique=True)),
                (
                    "category",
                    models.ManyToManyField(related_name="types", to="tracks.category"),
                ),
            ],
        ),
        migrations.AddField(
            model_name="category",
            name="genome",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="track_categories",
                to="tracks.genome",
            ),
        ),
    ]