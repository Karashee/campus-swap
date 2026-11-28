import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the gallery table. The existing single images move across in 0004."""

    dependencies = [
        ('products', '0002_seed_categories'),
    ]

    operations = [
        migrations.CreateModel(
            name='ListingImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='listings/%Y/%m/')),
                ('order', models.PositiveSmallIntegerField(default=0, help_text='Lowest first. The first photo is the cover.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='products.listing')),
            ],
            options={
                'ordering': ['order', 'pk'],
                'indexes': [models.Index(fields=['listing', 'order'], name='products_li_listing_69f6f1_idx')],
            },
        ),
    ]
