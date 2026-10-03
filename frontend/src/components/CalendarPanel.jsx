import { useState } from 'react'

import * as api from '../api'
import useApi from '../hooks/useApi'
import ErrorMessage from './ErrorMessage'

export default function CalendarPanel() {
  const links = useApi(() => api.calendar.links())
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)

  async function copy() {
    await navigator.clipboard.writeText(links.data.feed_url)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  async function regenerate() {
    if (!window.confirm('Make a new link? Calendars subscribed to the old one will stop updating.')) return
    try {
      links.setData(await api.calendar.regenerate())
    } catch (err) {
      setError(err)
    }
  }

  return (
    <section className="card stack">
      <h3>Add to your calendar</h3>
      <p className="muted small">
        Classes, club meetings and shifts you sign up for, kept in sync. Google refreshes
        subscribed calendars every few hours, so changes can take a while to appear.
      </p>
      <ErrorMessage error={links.error || error} />
      {links.data && (
        <>
          <a className="button" href={links.data.google_url} target="_blank" rel="noreferrer">
            Add to Google Calendar
          </a>
          <div className="actions">
            <a className="button secondary" href={links.data.webcal_url}>Apple / Outlook</a>
            <a className="button secondary" href={links.data.feed_url} download="lineup.ics">Download .ics</a>
          </div>
          <div className="row">
            <input readOnly value={links.data.feed_url} aria-label="Calendar feed URL" onFocus={(e) => e.target.select()} />
            <button type="button" className="secondary" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
          </div>
          <p className="muted small">
            Treat this link like a password: anyone with it can see your schedule.{' '}
            <button type="button" className="link-button" onClick={regenerate}>Make a new link</button>
          </p>
        </>
      )}
    </section>
  )
}
