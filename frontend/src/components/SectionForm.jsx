import { useState } from 'react'

import * as api from '../api'
import ErrorMessage from './ErrorMessage'

const emptyMeeting = () => ({ kind: 'LEC', days: '', start_time: '', end_time: '', location: '' })

// Adds a missing section to the shared catalog: course, CRN and every weekly meeting
// go up in ONE request (the API saves them together in a transaction).
export default function SectionForm({ termId, onSaved, onCancel }) {
  const [course, setCourse] = useState({ subject: '', number: '', title: '', units: '' })
  const [section, setSection] = useState({ crn: '', section_code: '', instructor: '' })
  const [meetings, setMeetings] = useState([emptyMeeting()])
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const updateMeeting = (index, field, value) => setMeetings(
    meetings.map((m, i) => (i === index ? { ...m, [field]: value } : m)),
  )

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const created = await api.sections.create({
        term: termId,
        course: { ...course, units: course.units || null },
        ...section,
        meetings,
      })
      onSaved(created)
    } catch (err) {
      setError(err)
      setSaving(false)
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h3>Add a missing section</h3>
      <p className="muted small">
        Copy the details from Schedule Builder. Once added, every Lineup student can find it.
      </p>
      <div className="row">
        <label className="narrow">Subject
          <input value={course.subject} onChange={(e) => setCourse({ ...course, subject: e.target.value })} placeholder="ECS" required />
        </label>
        <label className="narrow">Number
          <input value={course.number} onChange={(e) => setCourse({ ...course, number: e.target.value })} placeholder="036A" required />
        </label>
        <label>Title
          <input value={course.title} onChange={(e) => setCourse({ ...course, title: e.target.value })} placeholder="Programming in Python" required />
        </label>
      </div>
      <div className="row">
        <label className="narrow">CRN
          <input value={section.crn} onChange={(e) => setSection({ ...section, crn: e.target.value })} inputMode="numeric" pattern="\d{5}" title="5 digits" required />
        </label>
        <label className="narrow">Section
          <input value={section.section_code} onChange={(e) => setSection({ ...section, section_code: e.target.value })} placeholder="A01" />
        </label>
        <label className="narrow">Units
          <input value={course.units} onChange={(e) => setCourse({ ...course, units: e.target.value })} inputMode="decimal" placeholder="4" />
        </label>
        <label>Instructor
          <input value={section.instructor} onChange={(e) => setSection({ ...section, instructor: e.target.value })} />
        </label>
      </div>

      <fieldset className="meetings-fieldset">
        <legend>Weekly meetings</legend>
        {meetings.map((m, i) => (
          // Rows have no id yet; index keys are fine because rows are only appended/removed here.
          // oxlint-disable-next-line react/no-array-index-key
          <div className="row meeting-row" key={i}>
            <select value={m.kind} onChange={(e) => updateMeeting(i, 'kind', e.target.value)} aria-label="Type">
              <option value="LEC">Lecture</option>
              <option value="DIS">Discussion</option>
              <option value="LAB">Lab</option>
              <option value="SEM">Seminar</option>
              <option value="OTH">Other</option>
            </select>
            <input value={m.days} onChange={(e) => updateMeeting(i, 'days', e.target.value)} placeholder="Days, e.g. MWF or TR" aria-label="Days" required />
            <input type="time" value={m.start_time} onChange={(e) => updateMeeting(i, 'start_time', e.target.value)} aria-label="Start" required />
            <input type="time" value={m.end_time} onChange={(e) => updateMeeting(i, 'end_time', e.target.value)} aria-label="End" required />
            <input value={m.location} onChange={(e) => updateMeeting(i, 'location', e.target.value)} placeholder="Location" aria-label="Location" />
            {meetings.length > 1 && (
              <button type="button" className="link-button danger" onClick={() => setMeetings(meetings.filter((_, j) => j !== i))}>
                Remove
              </button>
            )}
          </div>
        ))}
        <button type="button" className="link-button" onClick={() => setMeetings([...meetings, emptyMeeting()])}>
          + Add another meeting (e.g. discussion)
        </button>
        <p className="muted small">Days use UC Davis letters: M T W R F (R = Thursday).</p>
      </fieldset>

      <ErrorMessage error={error} />
      <div className="actions">
        <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Add section & enroll'}</button>
        <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
