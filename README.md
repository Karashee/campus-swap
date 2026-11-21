# CampusSwap

A student-only marketplace for Strathmore University.

Students end every semester with textbooks, calculators, hotplates and furniture they no longer
need, and the usual option is a WhatsApp group where posts scroll away in minutes. CampusSwap gives
Stratizens one place to list those items — to **sell**, **trade** or **give away free** — and to
browse what other students are offering. A student signs up with their Strathmore email, posts an
item with a photo, price and a campus meet-up spot, browses or searches what others have listed, and
contacts a seller on WhatsApp to arrange the hand-over.

Individual semester project for BBT 3101 (Internet Programming with Django)
by Andrew Karanja (167144).

## Stack

- Python 3.12+, Django 6.1
- SQLite in development (PostgreSQL planned for deployment)
- Server-rendered Django templates, one hand-written CSS file, no build step
- Pillow for image handling, python-dotenv for settings

## Features

**Accounts and authentication**
- Sign up restricted to configured email domains (default `strathmore.edu`), with a friendly error
- Log in with **either** email address or username, case-insensitively
- "Keep me logged in" controls how long the session lasts
- Logout as a POST form (Django 5+ removed GET logout)
- Password change and the full four-step password reset flow (email to the console in development)
- Public student profile (avatar or initials, course, year, bio, member since, their listings) and a
  private profile editor

**Marketplace**
- Post a listing with a photo, category, condition, meet-up spot and a Sell / Trade / Free type
- Price rules per type: selling needs a price, trading needs what you want in exchange, free has no price
- Listing detail page with the price tag, badges, seller card and a WhatsApp contact link for
  logged-in students
- Edit, delete and mark a listing Available / Reserved / Sold — owner only
- "My listings" with status tabs and counts
- Home page search across title and description, plus category chips with live counts
- A per-visitor "Recently viewed" strip driven by the session
- View counter that does not count the owner's own visits

**Admin and demo data**
- Custom user admin with the student profile fields
- Listing admin with thumbnails, filters, search and inline status editing
- Seven categories seeded by a data migration, plus a `seed_demo` command

## Requirements coverage

### Models

| Requirement | Where |
| --- | --- |
| Custom user model | `accounts/models.py` → `User(AbstractUser)`, with `AUTH_USER_MODEL = "accounts.User"` in `config/settings.py` |
| Field types and options | `accounts/models.py` (`EmailField(unique=True)`, `ImageField`, `PositiveSmallIntegerField` with choices); `products/models.py` (`DecimalField`, `SlugField`, `TextField`, `ImageField`, `PositiveIntegerField`) |
| Validators | `accounts/models.py` → `kenyan_phone_validator` (`RegexValidator`); `products/models.py` → `MinValueValidator(0)` on `price` |
| Choices | `products/models.py` → `Listing.Condition`, `Listing.ListingType`, `Listing.Status` (all `TextChoices`) |
| One-to-many relationships | `products/models.py` → `Listing.seller` (FK to `AUTH_USER_MODEL`, `CASCADE`, `related_name="listings"`) and `Listing.category` (FK `PROTECT`) |
| Many-to-many through a table | `products/models.py` → `SavedListing` (user + listing) with a `UniqueConstraint` on the pair |
| Model-level validation | `products/models.py` → `Listing.clean()` (Sell/Trade/Free price rules); `accounts/models.py` → `User.clean()` (normalises the phone to `+254…`) |
| Meta options and indexes | `products/models.py` → `Listing.Meta.ordering`, two `models.Index` entries; `Category.Meta.ordering` |
| Model methods and properties | `__str__`, `get_absolute_url`, `Listing.display_price`, `Listing.is_available`, `User.display_name`, `User.initials` |
| Custom `save()` | `products/models.py` → `Listing.save()` builds a unique slug from the title plus a random suffix |
| Data migration | `products/migrations/0002_seed_categories.py` |
| Management command | `products/management/commands/seed_demo.py` |

> Note on where validation runs: `Model.clean()` is **not** called by `save()`. It runs when something
> calls `full_clean()` — which `ModelForm` does during its `_post_clean()` step, and which the admin
> and `seed_demo` do too. Code that calls `Listing.objects.create(...)` directly bypasses it, which is
> why the rules are also expressed as database-level field options (`null`, `blank`, validators).

### Forms

| Requirement | Where |
| --- | --- |
| `ModelForm` | `products/forms.py` → `ListingForm`; `accounts/forms.py` → `ProfileForm` |
| `ModelForm` subclassing a built-in | `accounts/forms.py` → `SignUpForm(UserCreationForm)` |
| Plain `forms.Form` | `products/forms.py` → `ListingSearchForm` (GET search, saves nothing; has a `filter(queryset)` method using `Q` objects) |
| Field-level custom validation | `accounts/forms.py` → `SignUpForm.clean_email()` (lowercases, case-insensitive uniqueness, domain restriction) |
| Cross-field validation | `products/models.py` → `Listing.clean()`, surfaced on the `price` / `trade_for` inputs by `ListingForm`; `products/forms.py` → `ListingForm.clean()` mirrors the "free has no price" rule |
| File-upload validation | `products/forms.py` → `ListingForm.clean_image()` (max 5 MB, jpg/png/webp); `accounts/forms.py` → `ProfileForm.clean_avatar()` (max 2 MB) |
| Widgets and labels | `products/forms.py` → `RadioSelect` segmented buttons for `listing_type` and `condition`, `Textarea`, placeholders |
| Shared form styling | `config/forms.py` → `FormStyleMixin` adds the CSS classes and an error class to every widget |
| Shared field rendering | `templates/includes/form_field.html` (label, widget, help text, errors, required marker) |

### Authentication

| Requirement | Where |
| --- | --- |
| Registration | `accounts/views.py` → `signup()`; `accounts/forms.py` → `SignUpForm` |
| Email-domain restriction | `config/settings.py` → `ALLOWED_SIGNUP_EMAIL_DOMAINS` (read from `.env`; empty means allow any) |
| Login with email **or** username | `accounts/backends.py` → `EmailOrUsernameBackend`, registered in `AUTHENTICATION_BACKENDS` ahead of `ModelBackend` |
| Login view and form | `accounts/views.py` → `CampusLoginView`; `accounts/forms.py` → `LoginForm` |
| Logout via POST | `accounts/urls.py` → `LogoutView`, posted from the navbar form in `templates/base.html` with `{% csrf_token %}` |
| Password change | `accounts/urls.py` → `PasswordChangeView` / `PasswordChangeDoneView` |
| Password reset (4 views) | `accounts/urls.py` → `PasswordResetView`, `PasswordResetDoneView`, `PasswordResetConfirmView`, `PasswordResetCompleteView`; templates in `templates/registration/` |
| Development email backend | `config/settings.py` → `MAILERS["default"]` console backend (the current Django 6.1 API; `EMAIL_BACKEND` is deprecated) |
| Login-required views | `accounts/views.py` → `ProfileUpdateView(LoginRequiredMixin, …)`; `products/views.py` → `ListingCreateView`, `MyListingsView`, `OwnerListingMixin` |
| Ownership enforcement | `products/views.py` → `OwnerListingMixin.get_queryset()` filters to `seller=request.user`, so a non-owner gets a 404 on edit/delete; `mark_status()` is `@require_POST` with the same filter |
| Auth redirect settings | `config/settings.py` → `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL` |
| Password hashing and validators | Django defaults, with `AUTH_PASSWORD_VALIDATORS` in `config/settings.py` |

### Sessions

| Requirement | Where |
| --- | --- |
| Session middleware | `config/settings.py` → `django.contrib.sessions.middleware.SessionMiddleware` in `MIDDLEWARE`, with `django.contrib.sessions` installed (sessions stored in the database) |
| Session-based login | `accounts/views.py` → `CampusLoginView`; `django.contrib.auth.login()` writes the user id into `request.session` and cycles the session key to prevent fixation |
| "Remember me" session expiry | `accounts/forms.py` → `LoginForm.remember_me`; `accounts/views.py` → `CampusLoginView.form_valid()` calls `request.session.set_expiry(0)` (ends when the browser closes) or `set_expiry(None)` to fall back to `SESSION_COOKIE_AGE` = 2 weeks in `config/settings.py` |
| Recently viewed listings | `products/views.py` → `remember_viewed()` and `recently_viewed_listings()` store the last `RECENTLY_VIEWED_LIMIT` (5) listing ids under the `recently_viewed` session key, most recent first, no duplicates, skipping the visitor's own listings; rendered as a strip in `templates/home.html` |
| Messages framework (session-backed) | `django.contrib.messages` rendered as toasts in `templates/base.html` |

## Setup (Windows / PowerShell)

```powershell
git clone https://github.com/Karashee/campus-swap.git
cd campus-swap

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

# Create your own .env from the template
copy .env.example .env

# Generate a SECRET_KEY and paste it into .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

The site runs at http://127.0.0.1:8000/ and the admin at http://127.0.0.1:8000/admin/.

### Environment variables

Set these in `.env` (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django secret key. Generate your own; never reuse one from a repo. |
| `DEBUG` | `True` in development, `False` in production. |
| `ALLOWED_HOSTS` | Comma-separated host names, e.g. `127.0.0.1,localhost`. |
| `ALLOWED_SIGNUP_EMAIL_DOMAINS` | Comma-separated domains allowed to sign up. Empty means any domain. |

`.env`, `db.sqlite3` and `/media/` are gitignored.

### Demo logins

`python manage.py seed_demo` creates two students and six listings across all three listing types.
Pass `--reset` to clear and recreate them.

| Username | Email | Password |
| --- | --- | --- |
| `wanjiku` | `wanjiku.mwangi@strathmore.edu` | `campus123!` |
| `brian` | `brian.otieno@strathmore.edu` | `campus123!` |

Either username or email works at the login form.

## Tests

```powershell
python manage.py test          # 49 tests
python manage.py check
```

**49 tests** covering: the email-domain restriction and case-insensitive duplicate emails, login by
email and by username, remember-me session expiry, POST-only logout, login-required views, listing
validation per type, ownership (404 for non-owners on edit, delete and status changes), the view
counter skipping the owner, search filtering, and the recently-viewed session behaviour.
