from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Let students log in with their email address as well as their username.

    Looked up case-insensitively on both fields. Falls back to ModelBackend's
    password check and is_active check, so nothing about password handling changes.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identifier = username or kwargs.get(User.USERNAME_FIELD) or kwargs.get('email')
        if not identifier or password is None:
            return None

        lookup = 'email__iexact' if '@' in identifier else 'username__iexact'
        try:
            user = User.objects.get(**{lookup: identifier.strip()})
        except User.DoesNotExist:
            # Run the default hasher anyway so a missing user takes the same
            # time as a wrong password (no timing clue about who exists).
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
