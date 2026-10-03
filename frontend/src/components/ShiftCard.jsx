import { useState } from 'react'
import { Link } from 'react-router'

import * as api from '../api'
import { formatShiftTime } from '../format'
import ErrorMessage from './ErrorMessage'

export default function ShiftCard({ shift, showOrg, onChange, onDelete, onEdit }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [roster, setRoster] = useState(null)
  // Read the clock once when the card mounts, not on every render.
  const [now] = useState(() => Date.now())

  const started = new Date(shift.start_time).getTime() <= now
  const full = shift.spots_left <= 0

  async function run(action) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  // The API responds with the updated shift (new spots_left, is_signed_up), so the
  // card shows the server's truth rather than guessing locally.
  const toggleSignup = () => run(async () => {
    const updated = shift.is_signed_up
      ? await api.shifts.cancel(shift.id)
      : await api.shifts.signUp(shift.id)
    onChange(updated)
    if (roster) setRoster(await api.shifts.roster(shift.id))
  })

  const toggleRoster = () => run(async () => {
    setRoster(roster ? null : await api.shifts.roster(shift.id))
  })

  const remove = () => {
    if (!window.confirm(`Delete "${shift.title}"? Everyone signed up will lose their spot.`)) return
    run(async () => {
      await api.shifts.remove(shift.id)
      onDelete(shift.id)
    })
  }

  let signupLabel = 'Sign up'
  if (shift.is_signed_up) signupLabel = 'Cancel signup'
  else if (full) signupLabel = 'Full'

  return (
    <article className={`card shift${shift.is_signed_up ? ' signed-up' : ''}`}>
      <div className="shift-main">
        <div>
          <h3>{shift.title}</h3>
          <p className="muted">
            {formatShiftTime(shift.start_time, shift.end_time)}
            {shift.location && ` · ${shift.location}`}
          </p>
          {showOrg && (
            <p className="muted small">
              <Link to={`/orgs/${shift.organization}`}>{shift.organization_name}</Link>
            </p>
          )}
          {shift.description && <p className="small">{shift.description}</p>}
        </div>
        <div className="shift-side">
          <span className={`pill${full ? ' pill-full' : ''}`}>
            {shift.signup_count}/{shift.capacity} filled
          </span>
          {!started && (
            <button
              type="button"
              className={shift.is_signed_up ? 'secondary' : ''}
              disabled={busy || (full && !shift.is_signed_up)}
              onClick={toggleSignup}
            >
              {signupLabel}
            </button>
          )}
          {started && <span className="muted small">Started</span>}
        </div>
      </div>

      {shift.can_manage && (
        <div className="admin-row">
          <button type="button" className="link-button" onClick={toggleRoster} disabled={busy}>
            {roster ? 'Hide roster' : 'Roster'}
          </button>
          <button type="button" className="link-button" onClick={() => onEdit(shift)}>Edit</button>
          <button type="button" className="link-button danger" onClick={remove} disabled={busy}>
            Delete
          </button>
        </div>
      )}

      {roster && (
        <ul className="roster">
          {roster.length === 0 && <li className="muted">Nobody yet.</li>}
          {roster.map((entry) => (
            <li key={entry.id}>{entry.user.username} <span className="muted">{entry.user.email}</span></li>
          ))}
        </ul>
      )}

      <ErrorMessage error={error} />
    </article>
  )
}
