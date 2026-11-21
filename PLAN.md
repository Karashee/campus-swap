# CampusSwap — chunk-by-chunk build plan

**How to use this file**
1. Put `CLAUDE.md` and `PLAN.md` in the repo root (`C:\dev\djangoproject`), next to `manage.py`.
2. Open the folder in VS Code and start Claude Code.
3. For each chunk, paste the **Prompt** block. For the bigger chunks, ask Claude Code to show its plan before it edits anything.
4. Work through the **Check** list yourself in the browser, then commit with the suggested message.
5. Run `/clear` between chunks so each one starts with a clean context. `CLAUDE.md` reloads automatically.

**Phase A (chunks A0–A6) = today's assignment: models, forms, authentication.** About 3–4 hours in total.
Phase B maps to the rest of the course: CRUD → Security → APIs → Deployment, plus optional WebSockets.

---

## PHASE A — Assignment: Models, Forms, Authentication

### A0 · Foundation and secrets (≈15 min)
Your current `SECRET_KEY` is committed in a **public** repo. Rotate it now.

**Prompt**
```
Do chunk A0 from PLAN.md.
- Create requirements.txt pinning the installed Django version, plus Pillow and python-dotenv (install them).
- Move SECRET_KEY, DEBUG and ALLOWED_HOSTS into a .env file loaded with python-dotenv. Generate a NEW secret key
  (the old one was published on GitHub). Add .env.example with placeholder values. Make sure .env and /media/ are gitignored.
- Set TIME_ZONE = "Africa/Nairobi". Configure STATICFILES_DIRS = [BASE_DIR / "static"], plus MEDIA_URL and MEDIA_ROOT,
  and serve media in development from config/urls.py.
- Add 'django.contrib.humanize' to INSTALLED_APPS.
- Leave the existing MAILERS block alone for now.
- Create a short README.md: project name, one-paragraph description answering "what problem / who uses it / what
  can they do", and setup steps for Windows.
- Run python manage.py check.
```
**Check:** `runserver` still works · `git status` does not show `.env`
**Commit:** `chore: env-based settings, requirements, media/static config, README`

---

### A1 · Design system and base layout (≈30 min)
Build the look first, so every page from here on comes out polished.

**Prompt**
```
Do chunk A1 from PLAN.md, following the "Design system" section of CLAUDE.md exactly.
- static/css/app.css: CSS variables, reset, typography, layout container, buttons (primary/secondary/ghost/danger),
  form controls (input, select, textarea, checkbox, file input, error state, help text), cards, badges, the rotated
  price-tag sticker, toasts, empty-state block, responsive navbar with a vanilla-JS hamburger under 768px, and footer.
- templates/base.html: Google Fonts (Bricolage Grotesque + Inter), app.css, meta viewport, a {% block title %} that
  appends "· CampusSwap", a navbar (logo wordmark, Browse, Sell an item button, and an auth area that shows
  Log in / Sign up for now), a messages block rendered as dismissible toasts that auto-hide after 4 seconds,
  {% block content %}, and a footer.
- templates/includes/form_field.html: renders one bound field (label, widget, help text, errors, required marker).
  Also add a small FormStyleMixin (put it in config/forms.py, or a core module if you think that's cleaner) that adds CSS
  classes and an error class to widgets, so every form looks the same.
- Redesign templates/home.html as a landing page: a hero ("Buy, sell & swap with fellow Stratizens"), a search bar
  (non-functional for now), category chips (static placeholders), a "How it works" 3-step strip
  (List → Connect → Meet on campus), and an empty "Latest listings" section with an empty state.
- Update products/index.html to extend the new base.
- Add templates/404.html and 500.html in the same style.
Keep it accessible: focus rings, labels, contrast, prefers-reduced-motion.
```
**Check:** the home page looks finished on desktop and mobile (DevTools device mode) · the hamburger works
**Commit:** `feat(ui): design system, base layout, landing page`

---

### A2 · `accounts` app and custom User model (≈20 min) ⚠️ Must come before any other migrations

**Prompt**
```
Do chunk A2 from PLAN.md.
- Create an `accounts` app. Model User(AbstractUser) with:
  email (unique, required), phone (optional; validate Kenyan numbers like 0712345678, 0112345678 or
  +254712345678 with a RegexValidator and normalise to +254 format in clean()), course (CharField, optional),
  year_of_study (PositiveSmallIntegerField with choices 1–5, optional), bio (TextField, max 300, optional),
  avatar (ImageField upload_to="avatars/", optional), and date_joined from AbstractUser.
  Add a display_name property (full name, falling back to username) and an avatar_url/initials helper for templates.
- Set AUTH_USER_MODEL = "accounts.User" in settings.
- Register it in admin with UserAdmin, adding the new fields to the fieldsets.
- This project has no real data yet. Tell me to delete my local db.sqlite3 BEFORE running makemigrations/migrate,
  because switching to a custom user model after the first migrate breaks the auth tables.
- Run makemigrations accounts, then migrate. Remind me to run createsuperuser.
```
**Do yourself:** delete `db.sqlite3` → `python manage.py migrate` → `python manage.py createsuperuser`
**Check:** `/admin/` login works and the User admin shows phone, course, year and avatar
**Commit:** `feat(accounts): custom User model with student profile fields`

---

### A3 · Marketplace models, admin and demo data (≈30 min)

**Prompt**
```
Do chunk A3 from PLAN.md, in the `products` app.
Models:
- Category: name (unique), slug (unique), icon (short CharField for an emoji), ordering field. __str__ and get_absolute_url.
- Listing:
  seller (FK to AUTH_USER_MODEL, related_name="listings", CASCADE), title (max 120), slug (unique, auto-generated
  from title + a short random suffix in save()), description, category (FK PROTECT, related_name="listings"),
  condition (TextChoices: NEW "Brand new", LIKE_NEW "Like new", GOOD "Good", FAIR "Fair"),
  listing_type (TextChoices: SELL, TRADE, FREE), price (Decimal 10,2, null/blank, MinValueValidator(0)),
  trade_for (CharField 200, blank: what the seller wants in exchange),
  status (TextChoices: AVAILABLE, RESERVED, SOLD; default AVAILABLE),
  meetup_spot (CharField 120, e.g. "Library entrance"), image (ImageField upload_to="listings/%Y/%m/", required),
  views (PositiveIntegerField default 0), created_at, updated_at.
  Meta: ordering ["-created_at"], indexes on (status, -created_at) and (category, status).
  clean(): SELL requires a price > 0; FREE forces price to None; TRADE requires trade_for; price is not allowed on TRADE
  unless you think "trade + top-up cash" is worth supporting (tell me your choice).
  Helpers: get_absolute_url, is_available, a display_price property ("KSh 1,500" / "Free" / "Trade").
- SavedListing: user FK, listing FK, created_at, unique_together (user, listing). Model only for now; used in Phase B.
Admin: CategoryAdmin with prepopulated slug; ListingAdmin with list_display (title, seller, category, listing_type,
display_price, status, created_at), list_filter, search_fields, list_editable status, readonly views,
and an image thumbnail preview.
Data:
- A data migration that seeds categories: 📚 Textbooks, 💻 Electronics, ✏️ Stationery, 🛋️ Furniture,
  🛏️ Dorm Essentials, 👕 Clothing, 🎒 Other.
- A management command `python manage.py seed_demo` that creates 3 demo students (password "campus123!", printed
  at the end) and about 15 realistic listings across all categories and types (Kenyan-campus flavour: e.g. "Calculus
  Early Transcendentals 8th ed", "Hotplate – 2 burner", "Scientific calculator Casio fx-991ES"). Generate simple
  placeholder images with Pillow (category colour + emoji/initial + title). Make it idempotent (--reset flag clears demo data).
Then makemigrations, migrate, and run seed_demo.
```
**Check:** admin shows categories and listings with thumbnails · in the shell, `Listing(... listing_type="SELL", price=None).full_clean()` raises a ValidationError
**Commit:** `feat(products): Category, Listing, SavedListing models, admin, seed data`

---

### A4 · Authentication: sign up, log in, log out, password flows, profile (≈40 min)

**Prompt**
```
Do chunk A4 from PLAN.md, in the `accounts` app. Use Django's built-in auth views wherever possible, styled with
our design system, and render every form through includes/form_field.html.
Forms (all with FormStyleMixin):
- SignUpForm(UserCreationForm): username, first_name, last_name, email, password1, password2.
  clean_email: lowercase, case-insensitive uniqueness, and if settings.ALLOWED_SIGNUP_EMAIL_DOMAINS (read from .env,
  comma-separated, default "strathmore.edu"; an empty value means allow all) is set, require one of those domains,
  with a friendly error ("Use your Strathmore email so we know you're a student").
- LoginForm(AuthenticationForm) relabelled "Email or username", plus a custom auth backend
  EmailOrUsernameBackend (case-insensitive email lookup) added to AUTHENTICATION_BACKENDS alongside ModelBackend.
- ProfileForm(ModelForm): first_name, last_name, phone, course, year_of_study, bio, avatar
  (validate: max 2 MB, jpg/png/webp only).
Views and URLs (namespace "accounts"):
- signup (logs the user in on success, shows a welcome message, redirects to the profile edit page with a
  "complete your profile" nudge)
- login / logout (LogoutView via a POST form in the navbar) with "next" handled correctly
- password change and password-change-done
- password reset: all four views. Configure a console email backend for development (check how this Django version
  configures email: the settings file has a MAILERS block from startproject, so use whichever is correct and don't
  invent settings). Templates in templates/registration/.
- profile/<username>/ public profile (avatar or initials, name, course, year, bio, member since, listing count;
  the listings grid comes in A5)
- profile/edit/ (login_required)
Settings: LOGIN_URL, LOGIN_REDIRECT_URL = "home", LOGOUT_REDIRECT_URL = "home".
Navbar: when logged in, show an avatar dropdown (My profile, Edit profile, My listings placeholder, Change password,
Log out button) and the "Sell an item" button; when logged out, show Log in and Sign up.
Auth pages: a centred card layout with a short value message beside the form on desktop
("Your campus. Your stuff. Swap it.").
Write tests: signup rejects a non-allowed domain, rejects a duplicate email in different case, login works with
email AND username, profile edit requires login, logout via GET is not allowed.
```
**Check:** sign up with a `@strathmore.edu` address works and a gmail address gets rejected (then try with the env var empty) · log in with email · password reset link appears in the terminal and works end to end
**Commit:** `feat(accounts): signup/login/logout, password flows, profile with email-domain restriction`

---

### A5 · Listing forms and core pages (≈45 min)

**Prompt**
```
Do chunk A5 from PLAN.md, in the `products` app.
Forms (FormStyleMixin):
- ListingForm(ModelForm): title, category, listing_type, condition, price, trade_for, description, meetup_spot, image.
  Use radio "segmented" buttons for listing_type and condition. clean() mirrors the model rules with field-level
  errors (add_error on price/trade_for). clean_image: max 5 MB, jpg/png/webp, minimum 400px wide.
  Add a little vanilla JS to show/hide price vs trade_for as listing_type changes (server-side validation stays
  the source of truth).
- ListingSearchForm(forms.Form) with GET fields q, category, listing_type, condition, min_price, max_price, sort
  (newest, price low→high, price high→low). clean(): min_price ≤ max_price. Build it now; wire it up in B1, except
  put q on the home hero search.
Views (CBVs), URLs under namespace "products":
- ListingCreateView (LoginRequiredMixin; seller = request.user in form_valid; success message; redirect to detail)
- ListingDetailView by slug: big image, price tag, badges, condition, meet-up spot, description, seller card
  (avatar, name, course, member since, link to profile). "Contact seller" shows a WhatsApp link
  (https://wa.me/<phone> with a prefilled message naming the item) ONLY to logged-in users; logged-out users see
  "Log in to contact the seller". Increment views (not for the owner). Owner sees Edit / Delete / Mark reserved / Mark sold.
- ListingUpdateView and ListingDeleteView: the queryset is filtered to seller=request.user, so anyone else gets a 404.
  Delete uses a confirmation page.
- Mark status view (POST only, owner only) for AVAILABLE/RESERVED/SOLD.
- MyListingsView ("/my-listings/"): the user's listings with status tabs (All / Available / Reserved / Sold) and counts.
- Home: show the 8 latest AVAILABLE listings in the card grid; category chips come from the database with counts.
- Public profile (accounts): add the seller's available listings grid.
Reusable partial templates/includes/listing_card.html: image (aspect-ratio 4/3, object-fit cover, lazy loading),
rotated price tag, type badge, title (2-line clamp), condition plus time-since, and a SOLD/RESERVED overlay.
Point the navbar "Sell an item" and "My listings" links at the real views.
Tests: anonymous user is redirected from create; SELL without a price shows a form error; non-owner gets 404 on
edit/delete; owner can mark sold; views counter doesn't increment for the owner.
```
**Check:** post a listing with a photo · edit and delete it · log in as another demo user and try `/…/edit/` → 404 · WhatsApp link only when logged in
**Commit:** `feat(products): listing forms, create/detail/edit/delete, my listings, home feed`

---

### A6 · Verify, document, submit (≈20 min)

**Prompt**
```
Do chunk A6 from PLAN.md.
- Run the full test suite and python manage.py check; fix anything failing.
- Review the code for: missing login/ownership checks, unhandled validation, N+1 queries on list pages
  (add select_related("seller", "category")), and templates not using the shared partials. Fix what you find.
- Update README.md with: features so far; a "Requirements coverage" table mapping
  Models → accounts/models.py, products/models.py (fields, validation, relationships);
  Forms → the file and class names (ModelForms, forms.Form, custom validation, file upload validation);
  Authentication → views/backend/settings (signup with domain restriction, email-or-username login, POST logout,
  password change/reset, login_required, ownership enforcement);
  setup instructions including seed_demo and the demo login; and a Screenshots section with placeholders
  (docs/screenshots/*.png).
- Give me a list of the 6 screenshots I should take for submission.
```
**Do yourself:** take the screenshots (home, sign up with validation error, login, create listing with errors, listing detail, admin) and save them to `docs/screenshots/`
**Submit:** commit → `git push` → tag it: `git tag -a v0.1-models-forms-auth -m "Assignment: models, forms, authentication"` then `git push --tags`. Submit the repo link (and the tag link if they want a fixed snapshot).
**Commit:** `docs: README requirements coverage and screenshots`

---

## PHASE B — Complete product (follow the course topics as they come up)

### B1 · Browse, search and filter (CRUD "Read" done properly)
```
Do chunk B1. Add /browse/ ListingListView using ListingSearchForm: search across title and description (Q objects),
filters for category/type/condition/price range, sort, pagination (12 per page, keep query params across pages),
a filter sidebar (a bottom sheet on mobile), active-filter chips you can click to remove, result count, and empty state.
Category pages /c/<slug>/ reuse the same view. Exclude SOLD by default with a "show sold" toggle.
Hook the home hero search and category chips up to it. Add tests for the filters.
```

### B2 · Multi-image gallery (formsets)
```
Do chunk B2. Add a ListingImage model (listing FK, image, order). Use an inline formset on create/edit (up to 5 photos,
choose the cover image, drag or arrow-button reordering). Downscale uploads to max 1600px and strip EXIF with Pillow
in a helper. Detail page: gallery with thumbnails, keyboard navigation and a lightbox. Migrate the existing single
image to be the cover image (data migration).
```

### B3 · Saved items and HTMX interactivity
```
Do chunk B3. Add HTMX (CDN). A heart toggle on cards and the detail page saves/unsaves a listing (SavedListing) via
POST and swaps a partial, with no page reload; anonymous users get sent to login. Add a /saved/ page.
Make the browse filters update results live with hx-get, debounced on the search input, and push the URL.
Add Alpine.js for the avatar dropdown and mobile menu, replacing the vanilla JS.
```

### B4 · Offers and trade proposals
```
Do chunk B4. Add an Offer model: listing, buyer, offer_type (CASH/TRADE), amount, offered_listing (one of the buyer's
own available listings, for trades), message, status (PENDING/ACCEPTED/DECLINED/WITHDRAWN/COMPLETED), and timestamps.
Rules: you can't offer on your own listing, one pending offer per buyer per listing, and accepting one offer reserves
the listing and declines the others. Pages: "Offers received" and "Offers sent" with status tabs; accept/decline/
withdraw/mark-completed actions (POST, permission-checked). Completing a deal marks the listing SOLD.
Add a Notification model with a navbar bell and unread count. Tests for every rule.
```

### B5 · In-app messaging, then real-time with WebSockets (optional advanced)
```
Do chunk B5 part 1. Add Conversation (listing, buyer, seller, unique per listing+buyer) and Message models.
"Message seller" on the detail page opens or creates the conversation. Inbox with unread badges; a chat thread page.
Only participants can read a conversation.
```
```
Do chunk B5 part 2. Add Django Channels with an in-memory channel layer for dev (Redis in prod) and a
ChatConsumer so messages appear live, plus a typing indicator. Authenticate the websocket with the session and
check participant permissions in connect(). Keep the non-JS POST fallback working.
```

### B6 · Trust and safety
```
Do chunk B6. Reviews: after an Offer is COMPLETED, buyer and seller can each leave one 1–5 star review with a comment.
Show the average rating and count on profiles and seller cards. ReportListing model (reason choices + details)
with an admin moderation queue and "hide listing" action. Auto-hide listings with 3+ open reports.
Block users from posting more than 10 listings per day.
```

### B7 · Security hardening (Security topic)
```
Do chunk B7. Audit and fix: every view's auth and permission checks (write a test per view), CSRF on all POSTs,
upload validation (content sniffing with Pillow, not just extensions), safe redirects for "next", and login rate limiting
(django-axes or a simple cache-based limiter; explain the trade-off). Add Django's built-in Content Security Policy
support (available since Django 6.0; check the docs for the installed version) and production security settings
in a separate settings block driven by env vars (SECURE_* cookies, HSTS, SSL redirect).
Make `python manage.py check --deploy` clean with DEBUG=False. Write SECURITY.md summarising the measures.
```

### B8 · REST API (APIs topic)
```
Do chunk B8. Add Django REST Framework under /api/v1/: categories (read), listings (list/filter/search/paginate,
retrieve, and create/update/delete for the owner only via a custom IsOwnerOrReadOnly permission), me/profile,
saved listings, and offers. Token or session auth. Serializers validate the same business rules as the forms.
Add OpenAPI docs with drf-spectacular at /api/docs/. Add API tests.
```

### B9 · Deployment (Deployment topic)
```
Do chunk B9. Prepare for production: settings read DATABASE_URL (PostgreSQL via dj-database-url), WhiteNoise
for static files, gunicorn, and a cloud media storage backend (e.g. Cloudinary via django-storages) because hosting
filesystems are often ephemeral. Add a build script (collectstatic, migrate) and a Procfile/render.yaml as needed.
Walk me step by step through deploying to Render (or PythonAnywhere if simpler), setting the env vars, creating a
superuser, and running seed_demo on production. Add the live URL to the README.
```

### B10 · Final polish and demo
```
Do chunk B10. Run an accessibility and performance pass (Lighthouse targets ≥ 90): image sizes, lazy loading,
query counts on list pages (django-debug-toolbar in dev), meta tags/Open Graph for listing sharing, and a favicon.
Add an "About / How it works" page and a friendly onboarding empty state for new users.
Finalise the README with screenshots, an architecture diagram (Mermaid), ER diagram, feature list and test count.
Write me a 5-minute demo script that walks through the app and names the Django concepts behind each feature.
```

---

## Tips for working with Claude Code on this
- **One chunk per session.** If a chunk feels too big, say "Do only the models and admin parts of A3 first."
- **Read every migration before running it**, especially in A2 and A3.
- When something breaks, paste the full traceback and say "fix the root cause, don't suppress the error."
- Make sure you can explain each file. You'll be demoing this, so ask "explain what you just did and why" after each chunk.
- Commit after every chunk. The commit history is your evidence of progressive development.
