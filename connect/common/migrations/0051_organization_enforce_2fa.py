# Generated by Django 3.2.13 on 2022-05-16 19:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0050_project_flow_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='enforce_2fa',
            field=models.BooleanField(default=False, verbose_name='Only users with 2fa can access the organization'),
        ),
    ]
