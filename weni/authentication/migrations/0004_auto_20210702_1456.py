# Generated by Django 2.2.19 on 2021-07-02 14:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0003_auto_20210701_1432"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="phone",
            field=models.BigIntegerField(
                help_text="Phone number of the user; include area code",
                null=True,
                verbose_name="Telephone Number",
            ),
        ),
    ]