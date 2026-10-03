# Lineup

Shift sign-ups and class schedules for UC Davis students. Org admins post volunteer
and tabling shifts; members sign up, and the app enforces the rules: no overbooking,
no double-booking yourself, no signing up twice, and no shifts during your classes.
Classes, club meetings and shifts all flow into one calendar feed you can add to
Google Calendar.

Built as an Aggie Works application project: a full web app with a **React**
frontend and a **Django REST Framework** backend.

## Features

- Accounts with JWT login (short-lived access tokens, rotating refresh tokens, real logout)
- Organizations with admin/member roles and invite-code joining (rate-limited)
- Shifts with capacity, filtering, search and pagination
- Signups that can't overbook, even when many people click at the same instant
- No overlapping signups across all of your organizations
- A shared UC Davis course catalog: search sections, or add a missing one with all its meetings
- A weekly schedule builder that blocks class time conflicts
- Shift signups that respect your class schedule, including the daylight-saving change
- Weekly club meetings, and orgs linked to their [Clubly](https://clubly.org) page
- A private calendar feed (.ics) for Google, Apple and Outlook Calendar
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
  scheduling/      Shift, Signup, ClubMeeting, signup rules (services.py), filters
  courses/         Term, Holiday, Course, Section, Meeting, Enrollment, conflict rules
  calendars/       per-user secret feed URL and the .ics builder
frontend/
  src/api/         HTTP client (JWT + refresh) and one function per endpoint
  src/auth/        auth context and route guard
  src/pages/       Dashboard, Organization, My schedule, Browse shifts, Login, Register
  src/components/  WeekGrid, SectionForm, CalendarPanel, ClubMeetings, ShiftCard, ShiftList, ShiftForm, Layout
render.yaml        one-click deploy (database + API + static site)
```

## Running locally

**Backend**, from `backend/`:

```bash
python3 -m venv ../.venv
../.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put a real SECRET_KEY in .env
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py load_terms        # official UC Davis 2026-27 quarter dates
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

109 tests cover authentication, permissions, validation, filtering, query counts
(N+1 guard), every signup and enrollment rule, time-zone handling across the
daylight-saving change, the calendar feed (its repeat rules are expanded and checked
against the real Fall 2026 class days), and a concurrency test where 8 users race for
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
| `GET /api/shifts/class-conflicts/` | Your shifts that clash with your classes |
| `/api/club-meetings/` | An org's weekly meetings (admins create) |
| `GET /api/terms/` | Quarters with holidays |
| `/api/sections/` | Search (`term`, `subject`, `number`, `crn`, `mine`, `search`) or add a section with its course and meetings |
| `POST/DELETE /api/sections/{id}/enroll/` | Add to / drop from your schedule |
| `GET/POST /api/calendar/feed/` | Your calendar links / make a new secret link |
| `GET /calendar/{token}.ics` | The calendar feed itself (the token is the credential) |

## Deploying

`render.yaml` describes the whole stack. On Render, choose **New → Blueprint**
and point it at this repo; it creates the PostgreSQL database, the API (which runs
migrations on each deploy) and the static React site. Production configuration
comes entirely from environment variables (see `backend/.env.example`).
Each deploy also runs `load_terms`, which is safe to repeat, so the quarter dates stay current.

Google Calendar can only subscribe to a feed on the public internet, so "Add to
Google Calendar" works once deployed; locally, use "Download .ics" to check the feed.

## Data sources

UC Davis Schedule Builder has no public API and sits behind campus login, so Lineup
keeps its own shared catalog that students fill in. Quarter dates and holidays come
from the [Registrar's academic calendar](https://registrar.ucdavis.edu/calendar/academic-calendar).
