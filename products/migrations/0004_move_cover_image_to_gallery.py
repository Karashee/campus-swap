"""Move each listing's single image into the gallery as its cover photo.

Only the stored file *name* moves, so nothing is copied on disk: the row in
products_listingimage points at the same file the listing used to point at.
Listing.image is then dropped, leaving the gallery as the only place photos
live.
"""

from django.db import migrations, models


def image_to_gallery(apps, schema_editor):
    Listing = apps.get_model('products', 'Listing')
    ListingImage = apps.get_model('products', 'ListingImage')

    ListingImage.objects.bulk_create([
        ListingImage(listing=listing, image=listing.image.name, order=0)
        # A listing with no image should not exist (the field was required),
        # but skip the blank ones rather than create empty gallery rows.
        for listing in Listing.objects.exclude(image='').only('pk', 'image')
    ])


def gallery_to_image(apps, schema_editor):
    """Put each listing's cover photo back on the listing itself."""
    Listing = apps.get_model('products', 'Listing')
    ListingImage = apps.get_model('products', 'ListingImage')

    for listing in Listing.objects.all():
        cover = (
            ListingImage.objects
            .filter(listing=listing)
            .order_by('order', 'pk')
            .first()
        )
        if cover:
            listing.image = cover.image.name
            listing.save(update_fields=['image'])

    ListingImage.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_listingimage'),
    ]

    operations = [
        migrations.RunPython(image_to_gallery, gallery_to_image),
        # Give the field a blank default before dropping it, purely so this
        # migration can be reversed: SQLite rebuilds the whole table to add a
        # column back, and a NOT NULL column with no default fails on the
        # rows that are already there.
        migrations.AlterField(
            model_name='listing',
            name='image',
            field=models.ImageField(default='', upload_to='listings/%Y/%m/'),
        ),
        migrations.RemoveField(
            model_name='listing',
            name='image',
        ),
    ]
