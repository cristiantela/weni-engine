# Generated by Django 3.2.13 on 2022-08-08 21:33

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0057_auto_20220620_2002'),
        ('billing', '0007_auto_20220726_1416'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='project',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='common.project'),
        ),
        migrations.AddField(
            model_name='contactcount',
            name='project',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='contact_count_project', to='common.project'),
        ),
        migrations.AlterField(
            model_name='contactcount',
            name='channel',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='contact_count_channel', to='billing.channel'),
        ),
    ]
