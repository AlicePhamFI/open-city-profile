# Generated by Django 2.2.8 on 2020-03-12 10:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("profiles", "0020_add_indexes_to_searchable_fields")]

    operations = [
        migrations.AlterField(
            model_name="address",
            name="postal_code",
            field=models.CharField(max_length=32),
        )
    ]
