# CampusSwap

A student-only marketplace for Strathmore University.

Students end every semester with textbooks, calculators, hotplates and furniture they no longer
need, and the usual options are WhatsApp groups where posts scroll away in minutes. CampusSwap gives
Stratizens one place to list those items — to **sell**, **trade** or **give away free** — and to
browse what other students are offering. A student can post an item with a photo, price and a
meet-up spot on campus, browse and search listings, save the ones they like, make an offer, and
arrange a hand-over with the seller.

Individual semester project for BBT 3101 (Internet Programming with Django)
by Andrew Karanja (167144).

## Stack

- Python 3.12+, Django 6.1
- SQLite in development (PostgreSQL in deployment)
- Server-rendered Django templates, one hand-written CSS file, no build step
- Pillow for images, python-dotenv for settings

## Setup (Windows / PowerShell)

```powershell
git clone https://github.com/Karashee/campus-swap.git
cd campus-swap

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

# Create your own .env from the template, then put a real SECRET_KEY in it
copy .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The site then runs at http://127.0.0.1:8000/ and the admin at http://127.0.0.1:8000/admin/.

## Environment variables

Set these in `.env` (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django secret key. Generate your own; never reuse one from a repo. |
| `DEBUG` | `True` in development, `False` in production. |
| `ALLOWED_HOSTS` | Comma-separated host names, e.g. `127.0.0.1,localhost`. |

`.env`, `db.sqlite3` and `/media/` are gitignored.
