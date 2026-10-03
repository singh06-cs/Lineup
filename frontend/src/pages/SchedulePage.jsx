import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import * as api from '../api'
import CalendarPanel from '../components/CalendarPanel'
import ErrorMessage from '../components/ErrorMessage'
import SectionForm from '../components/SectionForm'
import WeekGrid from '../components/WeekGrid'
import { formatSlot, pickCurrentTerm } from '../format'
import useApi from '../hooks/useApi'

const KIND_LABELS = { LEC: 'Lecture', DIS: 'Discussion', LAB: 'Lab', SEM: 'Seminar', OTH: 'Other' }

// Messages for when Google sends the browser back here (?google=...).
const GOOGLE_RESULTS = {
  connected: ['ok', 'Google Calendar connected. Your schedule is in the "Lineup" calendar.'],
  cancelled: ['info', 'Google Calendar was not connected.'],
  error: ['error', 'Google Calendar could not be connected. Please try again.'],
}
const GOOGLE_REASONS = {
  permission: 'Lineup needs permission to manage its own calendar. Please tick that box on Google\'s screen.',
  expired: 'The connection request expired. Please try again.',
}

export default function SchedulePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const googleResult = GOOGLE_RESULTS[searchParams.get('google')]
  const terms = useApi(() => api.terms.list())
  const [chosenTermId, setChosenTermId] = useState(null)
  const termId = chosenTermId ?? (terms.data?.length ? pickCurrentTerm(terms.data).id : null)

  // Bumped after any enroll/drop/add so every list below reloads together.
  const [version, setVersion] = useState(0)
  const refresh = () => setVersion((v) => v + 1)

  const mine = useApi(
    () => (termId ? api.sections.list({ term: termId, mine: true }) : Promise.resolve(null)),
    [termId, version],
  )
  const clubs = useApi(
    () => (termId ? api.clubMeetings.list({ term: termId }) : Promise.resolve(null)),
    [termId, version],
  )
  const shiftConflicts = useApi(() => api.shifts.classConflicts(), [version])

  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])
  const results = useApi(
    () => (termId && query ? api.sections.list({ term: termId, search: query }) : Promise.resolve(null)),
    [termId, query, version],
  )

  const [adding, setAdding] = useState(false)
  const [errors, setErrors] = useState({}) // per-section enroll/drop errors
  const [busyId, setBusyId] = useState(null)

  async function act(sectionId, action) {
    setBusyId(sectionId)
    setErrors((e) => ({ ...e, [sectionId]: null }))
    try {
      await action()
      refresh()
    } catch (err) {
      setErrors((e) => ({ ...e, [sectionId]: err }))
    } finally {
      setBusyId(null)
    }
  }

  async function addedSection(section) {
    setAdding(false)
    setSearch(`${section.course.subject} ${section.course.number}`)
    await act(section.id, () => api.sections.enroll(section.id))
  }

  if (terms.loading && !terms.data) return <p className="muted">Loading…</p>
  if (terms.error) return <ErrorMessage error={terms.error} />
  if (!terms.data.length) return <p className="empty">No terms have been set up yet.</p>

  const myClasses = mine.data?.results ?? []
  const gridItems = [
    ...myClasses.flatMap((section) => section.meetings.map((m) => ({
      key: `meeting-${m.id}`,
      label: `${section.course.subject} ${section.course.number}`,
      sublabel: [KIND_LABELS[m.kind], m.location].filter(Boolean).join(' · '),
      days: m.days,
      start_time: m.start_time,
      end_time: m.end_time,
      tone: 'class',
    }))),
    ...(clubs.data ?? []).map((m) => ({
      key: `club-${m.id}`,
      label: m.organization_name,
      sublabel: [m.title, m.location].filter(Boolean).join(' · '),
      days: m.days,
      start_time: m.start_time,
      end_time: m.end_time,
      tone: 'club',
    })),
  ]

  return (
    <div className="stack">
      <header className="org-header">
        <h1>My schedule</h1>
        <select value={termId ?? ''} onChange={(e) => setChosenTermId(Number(e.target.value))} aria-label="Term">
          {terms.data.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </header>

      {googleResult && (
        <div className={`notice notice-${googleResult[0]}`} role="status">
          <span>
            {GOOGLE_REASONS[searchParams.get('reason')] ?? googleResult[1]}
            {searchParams.get('synced') === 'false' && ' The first sync failed; use "Sync now" to retry.'}
          </span>
          <button type="button" className="link-button" onClick={() => setSearchParams({}, { replace: true })}>
            Dismiss
          </button>
        </div>
      )}

      {shiftConflicts.data?.length > 0 && (
        <div className="warning" role="status">
          <strong>Heads up:</strong> some shifts you signed up for overlap your classes.
          <ul>
            {shiftConflicts.data.map(({ shift, conflicts }) => (
              <li key={shift.id}>
                <Link to={`/orgs/${shift.organization}`}>{shift.organization_name}: {shift.title}</Link>
                {' '}clashes with {conflicts[0]}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="dashboard">
        <section className="stack">
          <WeekGrid items={gridItems} />
          {gridItems.length === 0 && (
            <p className="muted empty">Search for your classes on the right to build your week.</p>
          )}

          <h2>Classes</h2>
          {myClasses.length === 0 && <p className="muted">No classes yet this term.</p>}
          {myClasses.map((section) => (
            <article key={section.id} className="card">
              <div className="shift-main">
                <div>
                  <h3>{section.course.subject} {section.course.number} <span className="muted">{section.section_code}</span></h3>
                  <p className="muted small">{section.course.title} · CRN {section.crn}{section.instructor && ` · ${section.instructor}`}</p>
                  <ul className="slot-list">
                    {section.meetings.map((m) => (
                      <li key={m.id}>{KIND_LABELS[m.kind]}: {formatSlot(m)}{m.location && ` · ${m.location}`}</li>
                    ))}
                  </ul>
                </div>
                <div className="shift-side">
                  <button
                    type="button"
                    className="secondary"
                    disabled={busyId === section.id}
                    onClick={() => act(section.id, () => api.sections.drop(section.id))}
                  >
                    Drop
                  </button>
                </div>
              </div>
              <ErrorMessage error={errors[section.id]} />
            </article>
          ))}
        </section>

        <aside className="stack">
          <section className="card stack">
            <h3>Find a class</h3>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="e.g. ECS 36A, 12345, or Python"
              aria-label="Search classes"
            />
            <ErrorMessage error={results.error} />
            {results.data?.results.length === 0 && (
              <p className="muted small">Not in Lineup yet. You can add it below.</p>
            )}
            <ul className="result-list">
              {results.data?.results.map((section) => (
                <li key={section.id}>
                  <div className="row">
                    <div className="grow">
                      <strong>{section.course.subject} {section.course.number}</strong>{' '}
                      <span className="muted small">{section.section_code} · CRN {section.crn}</span>
                      <div className="muted small">
                        {section.meetings.map((m) => formatSlot(m)).join(' · ') || 'No set meeting times'}
                      </div>
                    </div>
                    {section.is_enrolled ? (
                      <span className="pill">Added</span>
                    ) : (
                      <button
                        type="button"
                        disabled={busyId === section.id}
                        onClick={() => act(section.id, () => api.sections.enroll(section.id))}
                      >
                        Add
                      </button>
                    )}
                  </div>
                  <ErrorMessage error={errors[section.id]} />
                </li>
              ))}
            </ul>
            {!adding && (
              <button type="button" className="link-button" onClick={() => setAdding(true)}>
                Can't find it? Add a missing section
              </button>
            )}
          </section>
          {adding && <SectionForm termId={termId} onSaved={addedSection} onCancel={() => setAdding(false)} />}
          <CalendarPanel />
        </aside>
      </div>
    </div>
  )
}
