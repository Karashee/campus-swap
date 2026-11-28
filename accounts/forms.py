from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.core.files.uploadedfile import UploadedFile

from config.forms import FormStyleMixin
from products.imaging import (
    ImageTooLarge,
    ImageTooSmall,
    UnidentifiedImageError,
    process_upload,
)

User = get_user_model()

AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB

#: Avatars are shown at 40px in the navbar and 96px on a profile, so there is
#: no reason to store anything larger than this.
AVATAR_MAX_DIMENSION = 512

#: Small enough that a cropped profile picture passes, large enough that the
#: 96px version is not visibly soft.
AVATAR_MIN_WIDTH = 96


class SignUpForm(FormStyleMixin, UserCreationForm):
    """Student registration, restricted to the allowed email domains."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        # Case-insensitive uniqueness. The column is unique, but 'A@x.com' and
        # 'a@x.com' are different strings, so check it here too.
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')

        domains = getattr(settings, 'ALLOWED_SIGNUP_EMAIL_DOMAINS', [])
        if domains:
            domain = email.rpartition('@')[2]
            if domain not in domains:
                raise forms.ValidationError(
                    "Use your Strathmore email so we know you're a student."
                )
        return email


class LoginForm(FormStyleMixin, AuthenticationForm):
    """Log in with either the email address or the username.

    Also the place the login throttle takes effect: when the view says this
    attempt is locked out, clean() refuses before AuthenticationForm gets as
    far as calling authenticate(), so no password is checked at all.
    """

    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        label='Keep me logged in',
        help_text='Leave this off on a shared computer: you will be logged out '
                  'when the browser closes.',
    )

    def __init__(self, *args, locked_out_message=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.locked_out_message = locked_out_message
        self.fields['username'].label = 'Email or username'
        self.fields['username'].widget.attrs.update({
            'autofocus': True,
            'autocomplete': 'username',
        })

    def clean(self):
        if self.locked_out_message:
            raise forms.ValidationError(
                self.locked_out_message, code='locked_out'
            )
        return super().clean()


class ProfileForm(FormStyleMixin, forms.ModelForm):
    """Edit your own student profile.

    The avatar goes through the same processor as listing photos
    (products.imaging), so an upload is only accepted if Pillow can actually
    decode it as an image, and what reaches storage is a re-encoded JPEG with
    the EXIF metadata - which on a phone photo can include GPS coordinates -
    left behind.
    """

    class Meta:
        model = User
        fields = (
            'first_name', 'last_name', 'phone', 'course', 'year_of_study',
            'bio', 'avatar',
        )
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
            'avatar': forms.FileInput(
                attrs={'accept': 'image/jpeg,image/png,image/webp'}
            ),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')

        # Only a new upload is an UploadedFile. An untouched avatar's value is
        # the stored FieldFile and must be left alone: re-processing it would
        # write a second copy to the media folder on every profile save.
        if not isinstance(avatar, UploadedFile):
            return avatar

        # Size first, before Pillow is asked to decode anything: a decompression
        # bomb is a small file that expands into an enormous bitmap.
        if avatar.size > AVATAR_MAX_BYTES:
            raise forms.ValidationError('Keep your avatar under 2 MB.')

        try:
            return process_upload(
                avatar,
                max_dimension=AVATAR_MAX_DIMENSION,
                min_width=AVATAR_MIN_WIDTH,
            )
        except ImageTooSmall:
            raise forms.ValidationError(
                f'That picture is too small. Use one at least '
                f'{AVATAR_MIN_WIDTH}px wide.'
            )
        except ImageTooLarge:
            raise forms.ValidationError(
                'That image has far too many pixels to be a real photo.'
            )
        except UnidentifiedImageError:
            # Belt and braces: a file that is named .jpg but is really a PDF, a
            # zip or a script is normally stopped one layer earlier, by
            # ImageField itself, which also decides with Pillow rather than the
            # extension. This catches the same case if that ever changes.
            raise forms.ValidationError('That file is not an image we can read.')


# Styled versions of Django's own password forms, so they match every other page.

class StyledPasswordChangeForm(FormStyleMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(FormStyleMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(FormStyleMixin, SetPasswordForm):
    pass
