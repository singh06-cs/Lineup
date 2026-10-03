# Lineup

Shift sign-ups for student organizations. Org admins post volunteer and tabling
shifts; members sign up, and the app enforces the rules: no overbooking, no
double-booking yourself, no signing up twice.

Built as an Aggie Works application project: a full web app with a **React**
frontend and a **Django REST Framework** backend.

## Features

- Accounts with JWT login (short-lived access tokens, rotating refresh tokens, real logout)
- Organizations with admin/member roles and invite-code joining (rate-limited)
- Shifts with capacity, filtering, search and pagination
- Signups that can't overbook, even when many people click at the same instant
- No overlapping signups across all of your organizations
- A customized Django admin for staff

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite, React Router |
| API | Django 6.1, Django REST Framework, SimpleJWT, django-filter |
| Database | SQLite in development, PostgreSQL in production |
| Production | gunicorn, WhiteNoise, Render |

## Project layout

```
backend/
  config/          settings, root URLs
  accounts/        custom User, register/login/refresh/logout/me
  organizations/   Organization, Membership (role), invite codes, member management
  scheduling/      Shift, Signup, signup rules (services.py), filters
frontend/
  src/api/         HTTP client (JWT + refresh) and one function per endpoint
  src/auth/        auth context and route guard
  src/pages/       Dashboard, Organization, Browse shifts, Login, Register
  src/components/  ShiftCard, ShiftList, ShiftForm, Layout
render.yaml        one-click deploy (database + API + static site)
```

## Running locally

**Backend**, from `backend/`:

```bash
python3 -m venv ../.venv
../.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put a real SECRET_KEY in .env
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py createsuperuser
../.venv/bin/python manage.py runserver
```

The API runs at http://localhost:8000/api/ and the admin at http://localhost:8000/admin/.

**Frontend**, from `frontend/`:

```bash
npm install
npm run dev
```

Open http://localhost:5173.

## Tests

```bash
cd backend && ../.venv/bin/python manage.py test
```

56 tests cover authentication, permissions, validation, filtering, query counts
(N+1 guard), every signup rule, and a concurrency test where 8 users race for
2 spots at the same instant.

## API overview

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/register/`, `login/`, `refresh/`, `logout/` | Account and tokens |
| `GET/PATCH /api/auth/me/` | Your profile |
| `/api/organizations/` | List/create your orgs; `GET/PATCH/DELETE` one |
| `POST /api/organizations/join/` | Join with an invite code |
| `POST /api/organizations/{id}/leave/` | Leave (the last admin can't) |
| `GET /api/organizations/{id}/members/` | Member list |
| `PATCH/DELETE /api/organizations/{id}/members/{membership_id}/` | Change a role / remove someone (admins) |
| `POST /api/organizations/{id}/regenerate-invite-code/` | Revoke the old code (admins) |
| `/api/shifts/` | List (filters: `organization`, `upcoming`, `available`, `mine`, `starts_after`, `starts_before`, `search`) and create |
| `POST/DELETE /api/shifts/{id}/signup/` | Sign up / cancel |
| `GET /api/shifts/{id}/roster/` | Who's signed up (admins) |

## Deploying

`render.yaml` describes the whole stack. On Render, choose **New → Blueprint**
and point it at this repo; it creates the PostgreSQL database, the API (which runs
migrations on each deploy) and the static React site. Production configuration
comes entirely from environment variables (see `backend/.env.example`).
