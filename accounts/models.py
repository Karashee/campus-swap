from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

# Accepts the three ways Kenyan students actually write their number:
# 0712345678 / 0112345678 (Safaricom, Airtel), 712345678, +254712345678 or 254712345678.
KENYAN_PHONE_REGEX = r'^(?:\+?254|0)?(?:1|7)\d{8}$'

kenyan_phone_validator = RegexValidator(
    regex=KENYAN_PHONE_REGEX,
    message='Enter a Kenyan phone number, e.g. 0712345678 or +254712345678.',
)


class User(AbstractUser):
    """Student account. Set as AUTH_USER_MODEL so we never touch auth.User."""

    YEAR_CHOICES = [(year, f'Year {year}') for year in range(1, 6)]

    email = models.EmailField('email address', unique=True)
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[kenyan_phone_validator],
        help_text='Used for the WhatsApp contact link. e.g. 0712345678',
    )
    course = models.CharField(max_length=100, blank=True)
    year_of_study = models.PositiveSmallIntegerField(
        choices=YEAR_CHOICES, null=True, blank=True
    )
    bio = models.TextField(max_length=300, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)

    def __str__(self):
        return self.display_name

    def clean(self):
        """Normalise the phone number to +254XXXXXXXXX so links are consistent."""
        super().clean()
        if self.phone:
            digits = self.phone.strip().replace(' ', '').lstrip('+')
            if digits.startswith('254'):
                digits = digits[3:]
            else:
                digits = digits.lstrip('0')
            self.phone = f'+254{digits}'

    @property
    def display_name(self):
        """Full name if the student gave one, otherwise the username."""
        return self.get_full_name() or self.username

    @property
    def initials(self):
        """One or two letters for the avatar placeholder."""
        parts = [part for part in (self.first_name, self.last_name) if part]
        if not parts:
            parts = [self.username]
        return ''.join(part[0].upper() for part in parts[:2])
