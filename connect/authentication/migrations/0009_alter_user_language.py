# Generated by Django 3.2.11 on 2022-02-08 19:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0008_alter_user_utm'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='language',
            field=models.CharField(choices=[('es', 'Spanish'), ('en-us', 'English'), ('pt-br', 'Portuguese')], default='en-us', help_text='The primary language used by this user', max_length=64, verbose_name='Language'),
        ),
    ]
