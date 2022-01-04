# Generated by Django 3.2.9 on 2021-12-28 21:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0033_auto_20211222_1819'),
    ]

    operations = [
        migrations.AlterField(
            model_name='billingplan',
            name='plan',
            field=models.CharField(choices=[('free', 'free'), ('enterprise', 'enterprise'), ('custom', 'custom')], default='custom', max_length=10, verbose_name='plan'),
        ),
    ]