"""Create demo students and listings so the site has something to show.

    python manage.py seed_demo
    python manage.py seed_demo --reset   # clear demo data first

Idempotent: running it twice leaves the same two students and six listings,
each with one to four placeholder photos.
"""

import textwrap
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageDraw

from products.models import Category, Listing, ListingImage

DEMO_PASSWORD = 'campus123!'

DEMO_STUDENTS = [
    {
        'username': 'wanjiku',
        'email': 'wanjiku.mwangi@strathmore.edu',
        'first_name': 'Wanjiku',
        'last_name': 'Mwangi',
        'phone': '+254712345678',
        'course': 'BSc Informatics and Computer Science',
        'year_of_study': 3,
        'bio': 'Third year ICS. Clearing out my shelf every semester.',
    },
    {
        'username': 'brian',
        'email': 'brian.otieno@strathmore.edu',
        'first_name': 'Brian',
        'last_name': 'Otieno',
        'phone': '+254722334455',
        'course': 'Bachelor of Commerce',
        'year_of_study': 2,
        'bio': 'BCom, Student Centre regular. Happy to meet between classes.',
    },
]

# (student index, title, category slug, type, price, trade_for, condition,
#  status, spot, description, number of photos)
DEMO_LISTINGS = [
    (
        0, 'Calculus Early Transcendentals 8th ed', 'textbooks',
        'SELL', 1800, '', 'GOOD', 'AVAILABLE', 'Library entrance',
        'Used for one semester. All pages intact, a bit of pencil in the margins.',
        3,
    ),
    (
        0, 'Scientific calculator Casio fx-991ES', 'electronics',
        'SELL', 1200, '', 'LIKE_NEW', 'AVAILABLE', 'Student Centre',
        'Bought last year, barely used since I moved to a graphing one. Cover included.',
        2,
    ),
    (
        1, 'Hotplate - 2 burner', 'dorm-essentials',
        'SELL', 2500, '', 'GOOD', 'RESERVED', 'Hostel A reception',
        'Works perfectly. Moving out of hostel so I no longer need it.',
        1,
    ),
    (
        1, 'Study desk and chair', 'furniture',
        'TRADE', None, 'A small bookshelf or a floor lamp', 'FAIR', 'AVAILABLE', 'Phase 2 parking',
        'Solid wooden desk, one scratch on the top. Chair included.',
        4,
    ),
    (
        0, 'A4 refill pads, pack of 5', 'stationery',
        'FREE', None, '', 'NEW', 'AVAILABLE', 'Main gate',
        'Extra pads from a bulk buy. First person to message gets them.',
        1,
    ),
    (
        1, 'Strathmore hoodie, size M', 'clothing',
        'SELL', 900, '', 'GOOD', 'SOLD', 'Student Centre',
        'Official hoodie, washed but no fading. Fits a medium comfortably.',
        1,
    ),
]

# A calm colour per category for the placeholder images.
CATEGORY_COLOURS = {
    'textbooks': (67, 56, 202),
    'electronics': (20, 23, 31),
    'stationery': (21, 128, 61),
    'furniture': (180, 83, 9),
    'dorm-essentials': (14, 116, 144),
    'clothing': (159, 18, 57),
    'other': (91, 97, 112),
}


def shade(colour, step):
    """A lighter version of a colour, so each photo of an item differs."""
    return tuple(min(255, channel + step * 28) for channel in colour)


def placeholder_image(title, colour, label=''):
    """A solid-colour 800x600 JPEG with the item title wrapped on it."""
    image = Image.new('RGB', (800, 600), colour)
    draw = ImageDraw.Draw(image)
    lines = textwrap.wrap(f'{title}{label}', width=22) or ['Listing']
    line_height = 34
    y = 300 - (len(lines) * line_height) // 2
    for line in lines:
        left, top, right, bottom = draw.textbbox((0, 0), line)
        draw.text((400 - (right - left) / 2, y), line, fill=(250, 247, 242))
        y += line_height
    buffer = BytesIO()
    image.save(buffer, format='JPEG', quality=85)
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = 'Seed demo students and listings for development.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete the demo students (and their listings) before seeding.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        usernames = [student['username'] for student in DEMO_STUDENTS]

        if options['reset']:
            deleted, _ = User.objects.filter(username__in=usernames).delete()
            self.stdout.write(f'Reset: removed {deleted} demo rows.')

        students = []
        for data in DEMO_STUDENTS:
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults={key: value for key, value in data.items() if key != 'username'},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=['password'])
            students.append(user)
            self.stdout.write(
                f'{"Created" if created else "Kept"} student {user.username}'
            )

        categories = {category.slug: category for category in Category.objects.all()}
        if not categories:
            self.stderr.write(
                'No categories found. Run `manage.py migrate` first so the '
                'category data migration applies.'
            )
            return

        for row in DEMO_LISTINGS:
            (student_index, title, category_slug, listing_type, price,
             trade_for, condition, status, spot, description, photos) = row

            seller = students[student_index]
            if Listing.objects.filter(seller=seller, title=title).exists():
                self.stdout.write(f'Kept listing "{title}"')
                continue

            listing = Listing(
                seller=seller,
                title=title,
                description=description,
                category=categories[category_slug],
                condition=condition,
                listing_type=listing_type,
                price=price,
                trade_for=trade_for,
                status=status,
                meetup_spot=spot,
            )
            # Same rules the forms use, so bad demo data fails loudly here.
            listing.full_clean(exclude=['slug'])
            listing.save()

            # A couple of listings get a small gallery so the detail page
            # thumbnails and lightbox have something to show.
            colour = CATEGORY_COLOURS[category_slug]
            for position in range(photos):
                label = '' if position == 0 else f' ({position + 1})'
                photo = ListingImage(listing=listing, order=position)
                photo.image.save(
                    f'{title[:40]}-{position + 1}.jpg',
                    placeholder_image(title, shade(colour, position), label),
                    save=False,
                )
                photo.save()

            self.stdout.write(
                f'Created listing "{title}" with {photos} photo'
                f'{"" if photos == 1 else "s"}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. {len(students)} demo students, '
            f'{Listing.objects.filter(seller__in=students).count()} listings.'
        ))
        self.stdout.write(f'Log in as any of: {", ".join(usernames)}')
        self.stdout.write(f'Password: {DEMO_PASSWORD}')
