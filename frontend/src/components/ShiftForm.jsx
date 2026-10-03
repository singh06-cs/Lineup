import { useState } from 'react'

import * as api from '../api'
import { fromLocalInput, toLocalInput } from '../format'
import ErrorMessage from './ErrorMessage'

// Creates a new shift for `organizationId`, or edits `shift` if one is given.
export default function ShiftForm({ organizationId, shift, onSaved, onCancel }) {
  const [fields, setFields] = useState({
    title: shift?.title ?? '',
    location: shift?.location ?? '',
    description: shift?.description ?? '',
    start_time: toLocalInput(shift?.start_time),
    end_time: toLocalInput(shift?.end_time),
    capacity: shift?.capacity ?? 1,
  })
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const update = (event) => setFields({ ...fields, [event.target.name]: event.target.value })

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    const body = {
      ...fields,
      start_time: fromLocalInput(fields.start_time),
      end_time: fromLocalInput(fields.end_time),
      capacity: Number(fields.capacity),
    }
    try {
      const saved = shift
        ? await api.shifts.update(shift.id, body)
        : await api.shifts.create({ ...body, organization: organizationId })
      onSaved(saved)
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h3>{shift ? 'Edit shift' : 'New shift'}</h3>
      <label>
        Title
        <input name="title" value={fields.title} onChange={update} required maxLength={200} />
      </label>
      <label>
        Location
        <input name="location" value={fields.location} onChange={update} maxLength={200} />
      </label>
      <div className="row">
        <label>
          Starts
          <input type="datetime-local" name="start_time" value={fields.start_time} onChange={update} required />
        </label>
        <label>
          Ends
          <input type="datetime-local" name="end_time" value={fields.end_time} onChange={update} required />
        </label>
        <label className="narrow">
          Spots
          <input type="number" name="capacity" min={1} value={fields.capacity} onChange={update} required />
        </label>
      </div>
      <label>
        Description
        <textarea name="description" rows={2} value={fields.description} onChange={update} />
      </label>
      <ErrorMessage error={error} />
      <div className="actions">
        <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save shift'}</button>
        <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
