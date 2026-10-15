# BlogReach - Guest Post Placement Marketplace

A marketplace where publishers list their websites for guest post placements and advertisers
browse listings, place orders, and track each order from request to published link.

Built for BlogReach.com (TechAbout internship task ZR-26-00740).

## Stack

- Python 3.11+, FastAPI, Jinja2 server-rendered templates, SQLAlchemy 2.0
- SQLite locally, PostgreSQL in production (picked via `DATABASE_URL` in `app/db.py`)
- Auth: bcrypt password hashing (passlib), JWT in HTTP-only cookies (python-jose),
  role-based access (publisher, advertiser, admin)
- Email: pluggable `EmailService`. Default backend stores every email in the `EmailLog`
  table and prints it to stdout. Optional real SMTP via env vars.
- Tests: pytest

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit SECRET_KEY
uvicorn app.main:app --reload
```

Open http://localhost:8000. On first startup the database is created and demo data
is seeded (see below). Set `SEED_ON_STARTUP=false` to skip seeding.

To use PostgreSQL:

```bash
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/blogreach uvicorn app.main:app
```

(Install `psycopg2-binary` for the Postgres driver.)

## Demo credentials (seeded on first startup)

| Role       | Email                   | Password      |
|------------|-------------------------|---------------|
| Admin      | admin@blogreach.com     | Admin123!     |
| Publisher  | publisher@blogreach.com | Publisher123! |
| Advertiser | advertiser@blogreach.com| Advertiser123!|

Six sample listings across SEO, Tech, Health, Finance, Travel and Food are seeded
under the demo publisher.

Note: if you start with an empty database and `SEED_ON_STARTUP=false`, the first
user to register becomes admin automatically.

## Architecture

```
app/
  main.py          # FastAPI app, HTML routes, JSON API routes
  db.py            # engine + session; SQLite by default, Postgres via DATABASE_URL
  models.py        # User, Listing, Order, EmailLog (SQLAlchemy 2.0)
  schemas.py       # Pydantic schemas for the JSON API
  auth.py          # bcrypt hashing, JWT creation/validation, cookie helpers
  orders.py        # order status state machine + email notifications
  email_service.py # pluggable email backends (log default, SMTP optional)
  seed.py          # demo users + listings for fresh databases
  templates/       # Jinja2 pages (light theme)
  static/style.css # styling
```

Order status flow (enforced in `app/orders.py`, invalid transitions return 400):

- `requested` -> `accepted` or `rejected` (publisher)
- `accepted` -> `in_progress` or `rejected` (publisher)
- `in_progress` -> `delivered` or `rejected` (publisher)
- `delivered` -> `completed` (advertiser)
- `completed` and `rejected` are terminal

Every status change emails the other party and records the email in `EmailLog`.

## JSON API

Auth: login via `/login` first (sets the JWT cookie), or send
`Authorization: Bearer <token>`.

- `GET /api/listings?niche=&min_price=&max_price=&q=` - active listings
- `POST /api/listings` - create listing (publisher). Body: `ListingCreate`
- `POST /api/orders` - place order (advertiser). Body: `OrderCreate`
- `GET /api/orders/{id}` - order detail (parties + admin)
- `POST /api/orders/{id}/status` - change status. Body: `{"status": "accepted"}`.
  Returns 400 on invalid transitions.

## Running tests

```bash
pytest -q
```

Tests use an isolated SQLite database at `/tmp/blogreach_test.db` with seeding
disabled, and cover: registration/login, the first-user-becomes-admin rule, role
guards, listing CRUD and ownership, order placement, the full happy-path flow
with email assertions, rejection flow, invalid transitions (400), unauthenticated
redirects, admin views, and the JSON API.

## Email backends

Default (`EMAIL_BACKEND=log`): emails are stored in the `EmailLog` table, visible
at `/admin/email-log`, and printed to stdout. No real email is sent.

Real SMTP (`EMAIL_BACKEND=smtp`): set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM`. Every email is still logged in `EmailLog`.

## Limitations (honest)

- Payments are mock only. The checkout page labels itself as mock, card fields are
  not validated and nothing is stored; paying records a `MOCK-XXXX` reference.
- Default email backend does not send real email; it logs to the database.
- SQLite is the default; on serverless hosts (e.g. Vercel) use Postgres via
  `DATABASE_URL` because the local filesystem is ephemeral.
- No file uploads, no listing images, no real payment disputes or refunds.
- Session JWTs live in cookies for 7 days; there is no "forgot password" flow yet.

## Deploying to Vercel

`vercel.json` and `api/index.py` are included. Set `DATABASE_URL` to a Postgres
database and `SECRET_KEY` in the Vercel project settings before deploying.
