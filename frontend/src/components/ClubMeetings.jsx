import { useState } from 'react'

import * as api from '../api'
import { formatSlot, pickCurrentTerm, toggleDay } from '../format'
import useApi from '../hooks/useApi'
import DaysPicker from './DaysPicker'
import ErrorMessage from './ErrorMessage'

// An org's weekly meetings (they show up on every member's schedule and calendar feed).
export default function ClubMeetings({ orgId, isAdmin }) {
  const meetings = useApi(() => api.clubMeetings.list({ organization: orgId }), [orgId])
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState(null)

  async function remove(meeting) {
    if (!window.confirm(`Delete "${meeting.title}"?`)) return
    try {
      await api.clubMeetings.remove(meeting.id)
      meetings.reload()
    } catch (err) {
      setError(err)
    }
  }

  return (
    <section className="card">
      <div className="section-head">
        <h3>Weekly meetings</h3>
        {isAdmin && !adding && (
          <button type="button" className="link-button" onClick={() => setAdding(true)}>+ Add</button>
        )}
      </div>
      <ErrorMessage error={meetings.error || error} />
      {meetings.data?.length === 0 && !adding && <p className="muted small">No regular meetings yet.</p>}
      <ul className="members">
        {meetings.data?.map((m) => (
          <li key={m.id}>
            <div>
              <strong>{m.title}</strong>
              <div className="muted small">
                {formatSlot(m)}{m.location && ` · ${m.location}`} · {m.term_name}
              </div>
            </div>
            {m.can_manage && (
              <button type="button" className="link-button danger" onClick={() => remove(m)}>Delete</button>
            )}
          </li>
        ))}
      </ul>
      {adding && (
        <ClubMeetingForm
          orgId={orgId}
          onSaved={() => { setAdding(false); meetings.reload() }}
          onCancel={() => setAdding(false)}
        />
      )}
    </section>
  )
}

function ClubMeetingForm({ orgId, onSaved, onCancel }) {
  const terms = useApi(() => api.terms.list())
  const [fields, setFields] = useState({
    term: '', title: 'General meeting', days: '', start_time: '', end_time: '', location: '',
  })
  const [error, setError] = useState(null)
  const update = (e) => {
    const { name, value } = e.target
    setFields((f) => ({ ...f, [name]: value }))
  }
  const termId = fields.term || (terms.data?.length ? pickCurrentTerm(terms.data).id : '')

  async function submit(event) {
    event.preventDefault()
    if (!fields.days) {
      setError(new Error('Pick at least one day.'))
      return
    }
    setError(null)
    try {
      await api.clubMeetings.create({ ...fields, term: termId, organization: Number(orgId) })
      onSaved()
    } catch (err) {
      setError(err)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="row">
        <label>Term
          <select name="term" value={termId} onChange={update} required>
            {terms.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <label>Title
          <input name="title" value={fields.title} onChange={update} required />
        </label>
      </div>
      <div className="field">
        <span className="field-label">Days</span>
        <DaysPicker value={fields.days} onToggle={(day) => setFields((f) => ({ ...f, days: toggleDay(f.days, day) }))} />
      </div>
      <div className="row">
        <label>Starts
          <input type="time" name="start_time" value={fields.start_time} onChange={update} required />
        </label>
        <label>Ends
          <input type="time" name="end_time" value={fields.end_time} onChange={update} required />
        </label>
      </div>
      <label>Location
        <input name="location" value={fields.location} onChange={update} />
      </label>
      <p className="muted small">Repeats every week of the term, skipping holidays.</p>
      <ErrorMessage error={error} />
      <div className="actions">
        <button type="submit">Save meeting</button>
        <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
