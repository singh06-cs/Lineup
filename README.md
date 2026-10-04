# Lineup

Shift sign-ups and class schedules for UC Davis students. Org admins post volunteer
and tabling shifts; members sign up, and the app enforces the rules: no overbooking,
no double-booking yourself, no signing up twice, and no shifts during your classes.
Classes, club meetings and shifts all flow into one calendar feed you can add to
Google Calendar.

Built as an Aggie Works application project: a full web app with a **React**
frontend and a **Django REST Framework** backend.

## Demo videos

### Web demo

https://github.com/user-attachments/assets/14f2f6fe-71db-43c0-a96f-80caebd2b828

### Mobile demo

https://github.com/user-attachments/assets/ab96ecb5-ae97-404b-a330-3d4b03a45353

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
- Sign in with Google, and direct Google Calendar sync into a dedicated "Lineup" calendar
- An Account page for your profile and sign-in methods
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
  calendars/       calendar feed (.ics), Google Calendar OAuth + sync, encrypted token storage
frontend/
  src/api/         HTTP client (JWT + refresh) and one function per endpoint
  src/auth/        auth context and route guard
  src/pages/       Dashboard, Organization, My schedule, Browse shifts, Login, Register
  src/components/  WeekGrid, SectionForm, CalendarPanel, ClubMeetings, ShiftCard, ShiftList, ShiftForm, Layout
render.yaml        one-click deploy (database + API + static site)
```

## Running locally

**Prerequisites:** Python 3.12+ (Django 6.1's minimum) and Node.js 22.22+ (React Router's
minimum; Vite needs 20.19+). SQLite is built into Python, so no database server is needed
for development.

**Backend**, from `backend/`:

```bash
python3 -m venv ../.venv
../.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then set SECRET_KEY in .env (command below)
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py load_terms        # official UC Davis 2026-27 quarter dates
../.venv/bin/python manage.py createsuperuser
../.venv/bin/python manage.py runserver
```

To generate a `SECRET_KEY` for `.env`:

```bash
../.venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

The API runs at http://localhost:8000/api/ and the admin at http://localhost:8000/admin/.

**Frontend**, from `frontend/`:

```bash
npm install
npm run dev
```

Open http://localhost:5173.

**Demo data** (optional, development only):

```bash
cd backend && ../.venv/bin/python manage.py seed_demo
```

Creates two fictional orgs, shifts for the coming week, weekly club meetings, five demo
course sections, and two accounts: `demo_admin` (runs both orgs) and `demo_student`
(enrolled in two classes). Their shared password is `DEMO_PASSWORD` in
`backend/scheduling/management/commands/seed_demo.py`. Re-running resets the demo data.
Add `--if-empty` to preserve existing data. With `DEBUG` off, the command requires
an explicit `DEMO_MODE=True`.

## Tests

```bash
cd backend && ../.venv/bin/python manage.py test
```

147 tests cover authentication, permissions, validation, filtering, query counts
(N+1 guard), every signup and enrollment rule, time-zone handling across the
daylight-saving change, Google sign-in and Calendar sync (against a fake Google), the calendar feed (its repeat rules are expanded and checked
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
| `POST/DELETE /api/auth/google/` | Sign in with Google (or link it while logged in) / unlink |
| `GET /api/auth/google/config/` | Whether Google is set up, and the public client ID |
| `GET/DELETE /api/calendar/google/` | Google Calendar connection status / disconnect |
| `POST /api/calendar/google/connect/` | Get Google's approval URL |
| `POST /api/calendar/google/sync/` | Sync now |

## Deploying

`render.yaml` describes the whole stack. On Render, choose **New → Blueprint**
and point it at this repo; it creates the PostgreSQL database, the API (which runs
migrations on each deploy) and the static React site. Production configuration
comes entirely from environment variables (see `backend/.env.example`).
Each deploy also runs `load_terms`, which is safe to repeat, so the quarter dates stay current.

The Blueprint enables a reviewer demo with `DEBUG=False`, `DEMO_MODE=True`, and
`VITE_DEMO_MODE=true`. On the first deploy, `seed_demo --if-empty` creates sample
accounts and schedules; later deploys preserve reviewers' changes. The login page
offers **Try student demo** and **Try organizer demo**, so no account setup is needed.
These shared accounts have no Django staff or superuser access. Google credentials
are optional and can be added later in Render's environment settings.

For a normal production deployment, turn both demo flags off and remove the
`seed_demo --if-empty` build step. The free Render database expires after 30 days;
use a paid database to keep the demo available beyond that period.

Google Calendar can only subscribe to a feed on the public internet, so "Add to
Google Calendar" works once deployed; locally, use "Download .ics" to check the feed.

## Google sign-in and Calendar sync (optional)

Everything Google-related stays hidden until these are set. To turn it on:

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and
   enable the **Google Calendar API**.
2. Set up the **OAuth consent screen** (External). While it's in "Testing", add your own
   Google account under **Test users**.
3. Under **Credentials**, create an **OAuth client ID** of type **Web application**:
   - Authorized JavaScript origins: `http://localhost:5173`
   - Authorized redirect URIs: `http://localhost:8000/api/calendar/google/callback/`
4. Put the client ID and secret in `backend/.env`:
   ```
   GOOGLE_CLIENT_ID=....apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-...
   ```
5. Restart the backend. The Google button appears on the login page, and "Connect
   Google Calendar" appears on My schedule and the Account page.

Lineup asks only for the `calendar.app.created` scope: it can create and manage its own
"Lineup" calendar, and cannot read or change anything else in your Google Calendar.
Refresh tokens are encrypted before they're stored.

## Data sources

UC Davis Schedule Builder has no public API and sits behind campus login, so Lineup
keeps its own shared catalog that students fill in. Quarter dates and holidays come
from the [Registrar's academic calendar](https://registrar.ucdavis.edu/calendar/academic-calendar).
