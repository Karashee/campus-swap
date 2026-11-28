# Security notes — CampusSwap

What this project does to protect student accounts and their listings, and why.
Written as part of chunk B7. Every measure below has a test; the file that holds
each set of tests is named next to it.

> **Scope.** CampusSwap is a semester project submitted as a repository, not a
> deployed site, so the HTTPS-only settings (`SECURE_SSL_REDIRECT`, HSTS,
> `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`) are deliberately left out
> rather than configured for a deployment that does not exist. They are the
> first thing to add before putting this on a real domain. See "What `check
> --deploy` still reports" and "If this were deployed" at the end.

---

## 1. Authentication and sessions

* **Custom user model** (`accounts.User`) from the first migration, so account
  fields can be added later without a painful swap.
* **Login accepts an email or a username**, matched case-insensitively
  (`accounts/backends.py`). When no such account exists the backend still runs
  a password hash before returning `None`, so "no such student" and "wrong
  password" take the same amount of time and the form does not leak which
  usernames are real.
* **Password rules** are Django's four validators, including the common-password
  list, so `Password1` is refused.
* **Passwords are never stored**, only PBKDF2 hashes — Django's default.
* **Session cookies are HttpOnly** (Django's default), so a script cannot read
  the session id even if one did run.
* **The session key is cycled on login**, which is what stops session fixation:
  a session id planted before login stops being the one that is authenticated.
* **"Keep me logged in" is an explicit choice.** Left unchecked, the session
  cookie expires when the browser closes — the right default on a shared
  library machine.
* **Logout is POST-only**, with a CSRF token, so a crafted `<img>` or link
  cannot log a student out. Django 5 removed GET logout; the navbar uses a form.

Tests: `accounts/tests.py` (`LoginTests`, `RememberMeSessionTests`,
`LogoutTests`, `PasswordResetTests`).

## 2. Login rate limiting

The login form is otherwise an unlimited password-guessing oracle. Hashing makes
each guess slow, but not slow enough to matter to a script.

`accounts/ratelimit.py` keeps two counters in the cache per failed attempt:

| Counter | Stops |
| --- | --- |
| per username typed | one account being hammered from many addresses |
| per `REMOTE_ADDR` | one machine working through a list of accounts |

Either counter reaching `LOGIN_RATELIMIT_ATTEMPTS` (5) locks the form for
`LOGIN_RATELIMIT_WINDOW` (15 minutes). While it is locked, `LoginForm.clean()`
raises before `AuthenticationForm` calls `authenticate()`, so no password is
checked at all and the response carries **429 Too Many Requests**. A successful
login clears both counters, so three mistypes followed by the right password
leaves no residue.

The window is *fixed*, not sliding: it ends a set time after the first failure,
and further attempts do not push it back. That means a locked-out student always
gets back in after 15 minutes.

`X-Forwarded-For` is deliberately **not** read. It is an ordinary request
header, so anyone can send a fresh fake value with every guess and walk straight
around a per-IP limit. Behind a real proxy, the proxy's own trusted header would
be read here instead.

### Why a cache counter rather than django-axes

django-axes is the usual answer and is better at this job: it records attempts in
the database, so lockouts survive a restart and can be inspected and cleared
from the admin, and it handles proxy headers and whitelists properly. The cost
is another dependency, another set of migrations and another admin surface.

The cache approach is about forty lines and no new package, and its limits are
honest ones:

* the counters are **in memory**, so a restart clears every lockout;
* with `LocMemCache` they are **per process**, so behind *N* worker processes the
  real limit is *N* × the configured one.

Pointing `CACHES` at Redis fixes the sharing. Nothing fixes the restart. For a
student marketplace that is an acceptable trade; for anything holding money it
would not be, and django-axes would be the right call.

Tests: `accounts/tests.py` (`LoginRateLimitTests`).

## 3. Authorisation — who may do what

Ownership is enforced **in the queryset**, not by hiding buttons. A student who
guesses the edit URL of someone else's listing gets a plain 404, which does not
even confirm that the listing exists:

```python
class OwnerListingMixin(LoginRequiredMixin):
    def get_queryset(self):
        return Listing.objects.filter(seller=self.request.user)
```

| View | Who | How |
| --- | --- | --- |
| home, browse, category, listing detail, public profile | anyone | no check needed |
| create listing, my listings | logged in | `LoginRequiredMixin` |
| edit listing, delete listing | the seller | queryset filtered by `seller` → 404 |
| mark sold/reserved/available | the seller | `@require_POST` + `get_object_or_404(..., seller=request.user)` |
| edit profile | yourself | `get_object()` returns `request.user`; there is no pk in the URL |
| admin | staff | `django.contrib.admin` |

Two further points:

* **The seller is never a posted field.** `ListingCreateView.form_valid` sets
  `form.instance.seller = self.request.user`, so posting `seller=<someone
  else>` has no effect.
* **A disabled account has no public profile.** `profile_detail` filters
  `is_active=True`, so suspending a student also takes their page down.

The permission table above is mirrored by tests in `config/tests_security.py`,
which fail if a later chunk adds a named URL and does not classify it — the
point being that the audit cannot quietly go stale.

Tests: `config/tests_security.py` (`UrlCoverageTests`, `PublicAccessTests`,
`LoginRequiredTests`, `OwnershipTests`, `AdminAccessTests`).

## 4. CSRF

`CsrfViewMiddleware` is on, every form template has `{% csrf_token %}`, and
every state-changing endpoint is POST — including logout and the status
changes, which were the two easiest to get wrong.

Django's test client skips CSRF checking by default, so the tests use
`Client(enforce_csrf_checks=True)` and assert a **403** for a POST with no
token at each endpoint. Without that flag the protection could be removed and
the tests would still pass.

Tests: `config/tests_security.py` (`CsrfTests`).

## 5. Upload validation

Listing photos and avatars both go through `products/imaging.py`, which does not
trust the file name or the browser-supplied content type:

1. **Byte size first** — 5 MB for a photo, 2 MB for an avatar — checked before
   Pillow is asked to decode anything.
2. **Pillow must be able to decode it.** `Image.open` is what decides whether
   the upload is an image, so `payload.jpg` that is really a shell script, a PDF
   or a zip is rejected with a form error. This is content sniffing, not an
   extension check; `.jpg` means nothing on its own.
3. **Decompression bombs are refused.** A few kilobytes of highly compressible
   PNG can expand into hundreds of millions of pixels and pass the byte check.
   Pillow raises `DecompressionBombError`, which is turned into an
   `ImageTooLarge` form error rather than a 500.
4. **Everything is re-encoded.** The stored file is a fresh JPEG written from a
   new buffer, downscaled to at most 1600px (512px for avatars). Re-encoding is
   also what removes **EXIF metadata**, which on a phone photo can include the
   GPS coordinates of the dorm room the picture was taken in. The orientation
   flag is applied first, so the photo is not left on its side.
5. **The filename is rebuilt**, not reused: the extension is forced to `.jpg`,
   any directory part of the uploaded name is dropped and the stem is cut to 60
   characters, so a name like `../../etc/passwd` cannot steer where the file
   lands.

An untouched existing file is left exactly as it is, so editing a profile or a
listing does not rewrite stored images.

Tests: `products/tests.py` (`ImageProcessingTests`, `PhotoFormsetTests`),
`accounts/tests.py` (`AvatarUploadTests`).

## 6. Safe redirects after login

A `next=` parameter arrives in a URL that anyone can craft and mail around.
Following it blindly turns our own login page into an **open redirect**, which
is how a phishing link borrows a trusted domain: the student sees
`campusswap/accounts/login/?next=…`, logs in, and lands somewhere else
entirely.

Django's `LoginView` already validates its own `next`. Everywhere the project
reads one itself goes through `config/redirects.py`:

```python
def safe_next_url(request, fallback):
    target = request.POST.get(NEXT_PARAM) or request.GET.get(NEXT_PARAM)
    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return fallback
```

A relative path on this site is accepted; another host, a protocol-relative
`//evil.example/` URL and a `javascript:` scheme all fall back. It is used by
`signup`, so a student sent to "log in to contact the seller" who signs up
instead still lands back on the listing.

One related fix: an anonymous POST to the status endpoint used to redirect to
login with `next` pointing at that same URL, which is `@require_POST` — so
logging in produced a 405. It now points at the listing page.

Tests: `config/tests_security.py` (`SafeRedirectTests`).

## 7. Cross-site scripting and the Content Security Policy

Django's template autoescaping is the first line of defence, and nothing in the
project uses `|safe` or `mark_safe` on student-supplied text, so a listing
titled `<script>alert(1)</script>` renders as visible text.

The CSP is the second line, for the case where something slips through. Django
6.0 moved CSP into core, so this needs no package:
`django.middleware.csp.ContentSecurityPolicyMiddleware` plus `SECURE_CSP` in
`config/settings.py`.

| Directive | Value | Why |
| --- | --- | --- |
| `default-src` | `'self'` | everything comes from our own origin unless stated |
| `script-src` | `'self'` + per-response nonce | **no `unsafe-inline`** |
| `style-src` | `'self'`, `fonts.googleapis.com` | the Google Fonts stylesheet |
| `font-src` | `'self'`, `fonts.gstatic.com` | the font files themselves |
| `img-src` | `'self'`, `data:` | uploads are served from our origin |
| `base-uri` | `'self'` | an injected `<base>` cannot re-point every relative URL |
| `form-action` | `'self'` | a posted form cannot be redirected off-site |
| `frame-ancestors` | `'none'` | clickjacking, alongside `X-Frame-Options: DENY` |
| `object-src` | `'none'` | no Flash/applet surface at all |

The project's four inline `<script>` blocks carry the per-request nonce via
`{% csp_nonce_attr %}`, so they run while anything injected into the page does
not — an attacker cannot guess a value that is regenerated every response.

Because `style-src` has no `'unsafe-inline'`, the handful of
`style="margin:0"` attributes that were in the templates would have been
silently dropped. They are now CSS classes in `static/css/app.css`, and a test
renders every page and asserts that no `style="` attribute has crept back —
otherwise a regression would only show up as broken styling in production.

Tests: `config/tests_security.py` (`ContentSecurityPolicyTests`,
`XssEscapingTests`).

## 8. Other measures

* **SQL injection** — all data access goes through the ORM. There is no `raw()`
  or `extra()` and no string-built SQL anywhere in the project.
* **Mass assignment** — every `ModelForm` lists its `fields` explicitly; none
  uses `fields = '__all__'`, so a posted field that is not on the form (such as
  `seller`, `status` or `views`) is ignored.
* **Secrets** — `SECRET_KEY` and the rest are read from `.env`, which is
  gitignored. `settings.py` reads it with `os.environ['SECRET_KEY']`, with no
  fallback, so a missing key is a loud startup error rather than a site running
  on a default key. `.env.example` documents the variables without their values.
* **`ALLOWED_HOSTS`** comes from the environment, so it is not `['*']`.
* **Clickjacking and sniffing headers** — `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: same-origin`, all from
  Django's `SecurityMiddleware` defaults, asserted by a test so an accidental
  middleware removal is caught.
* **Sign-up is restricted to `strathmore.edu`** addresses
  (`ALLOWED_SIGNUP_EMAIL_DOMAINS`), which is what makes this a student-only
  marketplace. Email uniqueness is checked case-insensitively as well as by the
  database constraint.
* **Phone numbers are validated and normalised** before being put into a
  WhatsApp link, and outbound links use `rel="noopener"`.
* **`DEBUG` defaults to `False`**, so forgetting to set it cannot expose
  tracebacks and settings; development turns it on explicitly in `.env`.

## What `check --deploy` still reports

With `DEBUG=False`, `python manage.py check --deploy` lists six items, and all
six are deployment concerns rather than code defects:

| Item | Why it is still open |
| --- | --- |
| `security.W004` HSTS | no HTTPS to pin |
| `security.W008` `SECURE_SSL_REDIRECT` | nothing to redirect to |
| `security.W012` `SESSION_COOKIE_SECURE` | would stop login working over plain HTTP |
| `security.W016` `CSRF_COOKIE_SECURE` | same |
| `security.W009` `SECRET_KEY` | the development key in the local `.env`; a deployment sets a real one |
| `mail.E001` console email backend | password-reset mail goes to the terminal in development |

The first four are the HTTPS settings this chunk deliberately leaves out. Each
is one environment variable away, and the list below is the order to do it in.

## If this were deployed

In order, before pointing a domain at it:

1. `DEBUG=False`, a fresh 50-character `SECRET_KEY`, and the real host in
   `ALLOWED_HOSTS`.
2. `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS` (start small, then a year
   with `INCLUDE_SUBDOMAINS` and `PRELOAD`), `SESSION_COOKIE_SECURE=True`,
   `CSRF_COOKIE_SECURE=True`, and `CSRF_TRUSTED_ORIGINS` for the domain.
3. Run `python manage.py check --deploy` and clear what it lists.
4. Point `CACHES` at Redis so the login throttle is shared between workers, or
   switch to django-axes.
5. Serve media through storage that is not the application's filesystem, and
   never from the same origin as the application if user uploads can be
   arbitrary — here they are always re-encoded JPEGs, which removes most of
   that worry.

## Reporting something

This is a university coursework project with no production deployment. If you
find a problem in the code, please open an issue on the repository rather than
exploiting it against the development server.
