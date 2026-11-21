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

from config.forms import FormStyleMixin

User = get_user_model()

AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
AVATAR_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')


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
    """Log in with either the email address or the username."""

    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        label='Keep me logged in',
        help_text='Leave this off on a shared computer: you will be logged out '
                  'when the browser closes.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Email or username'
        self.fields['username'].widget.attrs.update({
            'autofocus': True,
            'autocomplete': 'username',
        })


class ProfileForm(FormStyleMixin, forms.ModelForm):
    """Edit your own student profile."""

    class Meta:
        model = User
        fields = (
            'first_name', 'last_name', 'phone', 'course', 'year_of_study',
            'bio', 'avatar',
        )
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        # Only validate a freshly uploaded file; an untouched existing one has no size.
        if avatar and hasattr(avatar, 'size'):
            if avatar.size > AVATAR_MAX_BYTES:
                raise forms.ValidationError('Keep your avatar under 2 MB.')
            if not avatar.name.lower().endswith(AVATAR_EXTENSIONS):
                raise forms.ValidationError('Use a JPG, PNG or WebP image.')
        return avatar


# Styled versions of Django's own password forms, so they match every other page.

class StyledPasswordChangeForm(FormStyleMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(FormStyleMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(FormStyleMixin, SetPasswordForm):
    pass
