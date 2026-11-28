"""Safe handling of ``?next=`` redirect targets.

A ``next`` parameter is attacker-controlled: it arrives in a URL that anyone
can craft and mail around. Redirecting to it blindly turns our own login page
into an open redirect, which is how phishing links borrow a trusted domain
("you were on campusswap.example, so the page it sent you to must be fine").

Django's own ``LoginView`` already runs this check on the ``next`` it is given.
Every place where *we* read ``next`` ourselves goes through the helper below so
it behaves the same way.
"""

from django.utils.http import url_has_allowed_host_and_scheme


#: The GET/POST parameter we read the redirect target from, matching Django's
#: ``REDIRECT_FIELD_NAME``.
NEXT_PARAM = 'next'


def safe_next_url(request, fallback):
    """Return the request's ``next`` target if it is ours, else ``fallback``.

    Accepts a relative path on this site ("/listings/calculus/") and rejects
    anything pointing elsewhere: another host, a protocol-relative
    "//evil.example/" URL, or a "javascript:" scheme.
    """
    target = request.POST.get(NEXT_PARAM) or request.GET.get(NEXT_PARAM)
    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return fallback
