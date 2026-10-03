import { useState } from 'react'

import * as api from '../api'
import { formatDateTime } from '../format'
import useApi from '../hooks/useApi'
import ErrorMessage from './ErrorMessage'

// Direct sync: Lineup writes into a "Lineup" calendar in your Google account and
// updates it whenever your classes, meetings or shifts change.
export default function GoogleCalendarSync() {
  const status = useApi(() => api.calendar.googleStatus())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!status.data?.configured) return null
  const { connected, google_email: email, last_synced_at: lastSynced, last_error: lastError } = status.data

  async function run(action) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      // A failed sync responds with the updated status (including last_error), which
      // the card already shows, so don't show the same message a second time.
      if (err.data?.connected !== undefined) status.setData(err.data)
      else setError(err)
    } finally {
      setBusy(false)
    }
  }

  // Full-page redirect to Google's approval screen; Google sends the browser back to
  // our backend, which redirects to /schedule?google=connected.
  const connect = () => run(async () => {
    const { authorization_url: url } = await api.calendar.googleConnect()
    window.location.assign(url)
  })
  const syncNow = () => run(async () => status.setData(await api.calendar.googleSync()))
  const disconnect = () => {
    if (!window.confirm('Stop syncing to Google Calendar? The "Lineup" calendar stays in Google until you delete it.')) return
    run(async () => status.setData(await api.calendar.googleDisconnect()))
  }

  return (
    <div className="google-sync stack">
      <h4>Google Calendar sync</h4>
      {connected ? (
        <>
          <p className="muted small">
            Syncing to a <strong>Lineup</strong> calendar in {email || 'your Google account'}.{' '}
            {lastSynced ? `Last synced ${formatDateTime(lastSynced)}.` : 'Not synced yet.'}
          </p>
          {lastError && <p className="error">{lastError}</p>}
          <div className="actions">
            <button type="button" onClick={syncNow} disabled={busy}>{busy ? 'Syncing…' : 'Sync now'}</button>
            <button type="button" className="secondary" onClick={disconnect} disabled={busy}>Disconnect</button>
          </div>
        </>
      ) : (
        <>
          <p className="muted small">
            Updates appear in Google right away. Lineup only gets access to its own
            "Lineup" calendar, never the rest of your calendar.
          </p>
          <button type="button" onClick={connect} disabled={busy}>Connect Google Calendar</button>
        </>
      )}
      <ErrorMessage error={error} />
    </div>
  )
}
