# Generated by Django 3.2.13 on 2022-05-06 12:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0049_merge_20220505_2015'),
    ]

    operations = [
        migrations.AlterField(
            model_name='requestrocketpermission',
            name='role',
            field=models.PositiveIntegerField(choices=[(0, 'not set'), (1, 'user'), (2, 'admin'), (3, 'agent'), (4, 'service manager')], default=0, verbose_name='role'),
        ),
        migrations.AlterField(
            model_name='rocketauthorization',
            name='role',
            field=models.PositiveIntegerField(choices=[(0, 'not set'), (1, 'user'), (2, 'admin'), (3, 'agent'), (4, 'service manager')], default=0, verbose_name='role'),
        ),
    ]