# Generated by Django 3.1.2 on 2020-10-23 13:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("repository", "0008_journal_repo"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="journal",
            options={"ordering": ["-timestamp"], "verbose_name": "Journal"},
        ),
        migrations.AlterField(
            model_name="journal",
            name="action",
            field=models.CharField(
                choices=[
                    ("1", "Backup"),
                    ("2", "Backup (new)"),
                    ("3", "Restore"),
                    ("4", "New Repository"),
                    ("5", "Repository changed"),
                ],
                max_length=2,
                verbose_name="Action",
            ),
        ),
    ]
