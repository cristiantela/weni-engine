# Generated by Django 2.2.17 on 2021-02-23 14:05

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0002_auto_20210223_1404'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project', to='common.Organization'),
        ),
    ]