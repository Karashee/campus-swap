# CampusSwap — project context for Claude Code

CampusSwap is a student-only marketplace for Strathmore University. Students list used items
(textbooks, electronics, stationery, furniture, dorm essentials) to **sell**, **trade**, or **give away free**,
and other students browse, save, make offers and arrange campus meet-ups.

Individual semester project for BBT 3101 (Internet Programming with Django), by Andrew Karanja (167144).
It is assessed progressively, so every chunk ends in a working, committed state.

The step-by-step build plan is in `PLAN.md`. When asked to "do chunk X", read that chunk in `PLAN.md` and do only that chunk.

## Stack
- Python 3.12+, **Django 6.1** (already installed; check `python -m django --version` before using version-specific APIs)
- SQLite in development, PostgreSQL in deployment (later chunk)
- Server-rendered Django templates and **one hand-written CSS file** (`static/css/app.css`). No CSS framework and no build step.
- Vanilla JS only until the HTMX chunk. HTMX and Alpine.js come in through a CDN later.
- Pillow for images, python-dotenv for settings.

## Environment (Windows, VS Code)
- Project root: `C:\dev\djangoproject`. Repo: github.com/Karashee/campus-swap (branch `main`)
- Django config package: `config/`. Apps: `products` (keep this name; it holds the Listing models), `accounts` (from chunk A2)
- Commands (PowerShell, with the venv active):
  - `.venv\Scripts\activate`
  - `python manage.py runserver`
  - `python manage.py makemigrations` / `python manage.py migrate`
  - `python manage.py test`
  - `python manage.py check`

## Non-negotiable rules
1. **Custom user model**: `AUTH_USER_MODEL = "accounts.User"`. Never reference `django.contrib.auth.models.User` directly. Use `settings.AUTH_USER_MODEL` in FKs and `get_user_model()` in code.
2. **Ownership**: only a listing's seller can edit or delete it. Enforce this in the view (queryset filtered by `seller=request.user`, or 404), not just by hiding buttons.
3. **Logout is a POST form** with `{% csrf_token %}`. Django 5+ removed GET logout.
4. **Secrets stay in `.env`** (gitignored). `settings.py` reads them with python-dotenv. Keep `.env.example` up to date.
5. Any new dependency goes into `requirements.txt` with a pinned version.
6. Every user-facing action gives feedback through the messages framework (rendered as toasts).
7. All forms render through the shared field partial (`templates/includes/form_field.html`) so they look the same everywhere.
8. Don't invent settings. If unsure whether a setting exists in this Django version, check the installed Django source or docs.
9. After each chunk: `python manage.py check`, then `python manage.py test`, then give me a manual test checklist and a suggested commit message. **Don't commit or push yourself** unless I ask.

## Code conventions
- Class-based views for CRUD (`CreateView`, `UpdateView`, `DeleteView`, `ListView`, `DetailView`), with `LoginRequiredMixin` where needed. Function views are fine for small one-offs.
- URL namespaces: `accounts:`, `products:`. Named URLs only; no hard-coded paths in templates.
- Models have `__str__`, `get_absolute_url`, `Meta.ordering`, and `created_at`/`updated_at` where it makes sense.
- Cross-field validation goes in `Model.clean()` and/or `Form.clean()`. Never trust only the frontend.
- Templates: project-level `templates/` for `base.html`, `includes/`, `registration/`, and error pages. App templates go in `<app>/templates/<app>/`.
- Money is in Kenyan shillings: `DecimalField(max_digits=10, decimal_places=2)`, displayed as `KSh 1,500` (use `django.contrib.humanize`).
- Time zone: `Africa/Nairobi`.

## Design system ("campus noticeboard")
Warm, tactile and confident. It should feel like a well-kept notice board, not a generic admin template.

- **Colours (CSS variables in `:root`)**
  - `--paper #FAF7F2` (page background), `--surface #FFFFFF` (cards), `--ink #14171F` (text, primary buttons)
  - `--muted #5B6170` (secondary text), `--line #E7E1D7` (borders)
  - `--accent #F2A900` (marigold: price tags, highlights, focus rings). Ink text on marigold, never white.
  - Listing-type badges: Sell = ink, Trade = `#4338CA` indigo, Free = `#15803D` green
  - Status: Available = green dot, Reserved = `#B45309` amber, Sold = grey with the title struck through
  - `--danger #B42318`
- **Type**: "Bricolage Grotesque" (600–800) for headings and the logo, "Inter" (400–600) for body. Both from Google Fonts.
  Base 16px, 1.6 line-height. Headings use tight letter-spacing (-0.02em).
- **Shape**: cards 14px radius, inputs and buttons 10px, badges as 999px pills. 1px `--line` borders. Shadows soft and rare (hover lift on cards only).
- **Signature element**: the price shows as a small marigold "price tag" sticker, slightly rotated (-2deg), on listing cards and the detail page. "FREE" and "TRADE" use the same tag shape in their colours.
- **Logo**: wordmark `campus⇄swap` in Bricolage Grotesque 800.
- **Layout**: max content width 1200px. The listing grid uses `repeat(auto-fill, minmax(240px, 1fr))`. Mobile-first, with a hamburger nav under 768px.
- **Accessibility**: visible focus rings (marigold, 3px), labels on every input, alt text on images, colour contrast at least WCAG AA, `prefers-reduced-motion` respected.
- **Empty states**: every list has a friendly empty state with an action ("No listings yet. Post the first one").
