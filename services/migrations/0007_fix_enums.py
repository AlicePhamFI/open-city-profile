# Generated by Django 2.2.4 on 2019-12-02 18:33

from django.db import migrations
import enumfields.fields
import services.enums


class Migration(migrations.Migration):

    dependencies = [("services", "0006_add_custom_permissions_to_service")]

    operations = [
        migrations.AlterField(
            model_name="service",
            name="service_type",
            field=enumfields.fields.EnumField(
                enum=services.enums.ServiceType, max_length=32, unique=True
            ),
        )
    ]
