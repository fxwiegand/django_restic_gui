# Generated by Django 3.1.2 on 2020-10-20 06:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("repository", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CallStack",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("level", models.PositiveIntegerField(default=0, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("url", models.CharField(max_length=200)),
            ],
            options={
                "ordering": ["level"],
            },
        ),
        migrations.AlterField(
            model_name="repository",
            name="path",
            field=models.FilePathField(
                allow_files=False,
                allow_folders=True,
                path="/Users/christianwiegand/backup/",
                verbose_name="Path",
            ),
        ),
    ]
