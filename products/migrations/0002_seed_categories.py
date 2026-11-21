from django.db import migrations

CATEGORIES = [
    ('Textbooks', 'textbooks'),
    ('Electronics', 'electronics'),
    ('Stationery', 'stationery'),
    ('Furniture', 'furniture'),
    ('Dorm Essentials', 'dorm-essentials'),
    ('Clothing', 'clothing'),
    ('Other', 'other'),
]


def seed_categories(apps, schema_editor):
    Category = apps.get_model('products', 'Category')
    for position, (name, slug) in enumerate(CATEGORIES, start=1):
        Category.objects.update_or_create(
            slug=slug, defaults={'name': name, 'ordering': position}
        )


def unseed_categories(apps, schema_editor):
    Category = apps.get_model('products', 'Category')
    Category.objects.filter(slug__in=[slug for _, slug in CATEGORIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
