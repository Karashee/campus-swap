"""Cache-based throttle for failed login attempts.

Without this, the login form is an unlimited password-guessing oracle: a script
can try thousands of passwords against one account, or one common password
against every account it can name. Django's password hashing makes each guess
slow, but not slow enough.

Two counters are kept per failure, both in the cache:

* per **username** (what was typed in the form), so one account cannot be
  hammered from a changing set of addresses;
* per **IP address**, so one machine cannot work through a list of accounts.

Either counter reaching ``LOGIN_RATELIMIT_ATTEMPTS`` blocks the form until the
window expires. A successful login clears both, so a student who mistypes their
password three times and then gets it right is not left part-way to a lockout.

Why a cache counter and not django-axes
---------------------------------------
django-axes is the usual answer and it is better at this: it records attempts in
the database so lockouts survive a restart and can be inspected and cleared from
the admin, and it handles proxies and whitelists for you. It is also another
dependency, another set of migrations and another admin surface for a project
this size. The cache approach is about forty lines with no new package, and its
limits are honest ones: the counters live in memory, so they vanish on restart
and - with LocMemCache - are not shared between worker processes, which means
the real limit under N workers is N x the configured one. Pointing CACHES at
Redis fixes the sharing; nothing fixes the restart, and for a student
marketplace that is an acceptable trade.
"""

from django.conf import settings
from django.core.cache import cache

#: Cache key prefixes, kept distinct so the two counters cannot collide.
USER_PREFIX = 'login-fail:user'
IP_PREFIX = 'login-fail:ip'


def attempt_limit():
    return getattr(settings, 'LOGIN_RATELIMIT_ATTEMPTS', 5)


def window_seconds():
    return getattr(settings, 'LOGIN_RATELIMIT_WINDOW', 15 * 60)


def client_ip(request):
    """The address Django saw the request come from.

    Deliberately ``REMOTE_ADDR`` and not ``X-Forwarded-For``: that header is
    just a request header, so anyone can send a fresh fake value with every
    guess and walk straight around a per-IP limit. Behind a real proxy the
    proxy's own trusted header would be read here instead.
    """
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _keys(request, username):
    keys = [f'{IP_PREFIX}:{client_ip(request)}']
    if username:
        # Usernames are matched case-insensitively at login, so count them
        # that way too, or 'Brian' and 'brian' would get a budget each.
        keys.append(f'{USER_PREFIX}:{username.strip().lower()}')
    return keys


def _increment(key, timeout):
    """Add one to a counter, starting it at 1 if it is not there yet.

    ``cache.add`` only writes when the key is free, so it both creates the
    counter and tells us we were the one who created it. ``incr`` afterwards
    leaves the original expiry alone, which is what makes this a fixed window:
    the lockout ends a set time after the *first* failure, so a determined
    script cannot keep itself locked out forever and nor can it reset the clock.
    """
    if cache.add(key, 1, timeout):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # It expired between the add and the incr. Start again.
        cache.set(key, 1, timeout)
        return 1


def is_blocked(request, username):
    """True if this address or this username has used up its attempts."""
    limit = attempt_limit()
    return any((cache.get(key) or 0) >= limit for key in _keys(request, username))


def record_failure(request, username):
    """Count one failed attempt. Returns True if that failure caused a block."""
    limit = attempt_limit()
    timeout = window_seconds()
    counts = [_increment(key, timeout) for key in _keys(request, username)]
    return any(count >= limit for count in counts)


def clear(request, username):
    """Forget this address's and this username's failures after a real login."""
    cache.delete_many(_keys(request, username))


def retry_after_minutes():
    """How long to tell someone to wait, rounded up to whole minutes."""
    return max(1, -(-window_seconds() // 60))
