# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-07-01 00:49
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0004_bulkaccount'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='bulkaccount',
            options={'managed': False, 'verbose_name': 'Bulk Account'},
        ),
    ]