from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracks", "0002_hyphenated_uuid_storage"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="track",
            index=models.Index(
                fields=["dataset_id"],
                name="tracks_track_dataset_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="track",
            index=models.Index(
                fields=["genome_id", "dataset_id"],
                name="tracks_track_genome_dataset_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="datasetrelease",
            index=models.Index(
                fields=["genome_id", "-release_label"],
                name="tracks_release_genome_label_idx",
            ),
        ),
    ]
