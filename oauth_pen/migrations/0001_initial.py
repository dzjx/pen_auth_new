# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2018-08-21 03:14
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Application',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_id', models.CharField(db_index=True, default='', max_length=100, unique=True)),
                ('user_id', models.CharField(db_index=True, default=0, max_length=20)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
