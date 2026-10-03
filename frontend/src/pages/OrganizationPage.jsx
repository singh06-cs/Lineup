import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import * as api from '../api'
import ClubMeetings from '../components/ClubMeetings'
import useAuth from '../auth/useAuth'
import ErrorMessage from '../components/ErrorMessage'
import ShiftForm from '../components/ShiftForm'
import ShiftList from '../components/ShiftList'
import useApi from '../hooks/useApi'

export default function OrganizationPage() {
  const { orgId } = useParams()
  const navigate = useNavigate()
  const org = useApi(() => api.organizations.get(orgId), [orgId])
  const [creating, setCreating] = useState(false)
  const [shiftsVersion, setShiftsVersion] = useState(0)
  const [error, setError] = useState(null)

  if (org.loading && !org.data) return <p className="muted">Loading…</p>
  if (org.error?.status === 404) return <p className="empty">Organization not found, or you're not a member.</p>
  if (org.error) return <ErrorMessage error={org.error} />

  const isAdmin = org.data.my_role === 'admin'


  async function leave() {
    if (!window.confirm(`Leave ${org.data.name}?`)) return
    try {
      await api.organizations.leave(orgId)
      navigate('/')
    } catch (err) {
      setError(err)
    }
  }

  async function deleteOrg() {
    if (!window.confirm(`Delete ${org.data.name} and ALL of its shifts? This cannot be undone.`)) return
    try {
      await api.organizations.remove(orgId)
      navigate('/')
    } catch (err) {
      setError(err)
    }
  }

  return (
    <div className="stack">
      <header className="org-header">
        <div>
          <h1>{org.data.name}</h1>
          {org.data.description && <p className="muted">{org.data.description}</p>}
          {org.data.clubly_url && (
            <a href={org.data.clubly_url} target="_blank" rel="noreferrer" className="small">
              View on Clubly ↗
            </a>
          )}
        </div>
        <div className="actions">
          <button type="button" className="secondary" onClick={leave}>Leave</button>
          {isAdmin && <button type="button" className="secondary danger" onClick={deleteOrg}>Delete</button>}
        </div>
      </header>
      <ErrorMessage error={error} />

      <div className="dashboard">
        <section className="stack">
          <div className="section-head">
            <h2>Upcoming shifts</h2>
            {isAdmin && !creating && <button type="button" onClick={() => setCreating(true)}>New shift</button>}
          </div>
          {creating && (
            <ShiftForm
              organizationId={Number(orgId)}
              onSaved={() => { setCreating(false); setShiftsVersion((v) => v + 1) }}
              onCancel={() => setCreating(false)}
            />
          )}
          <ShiftList
            params={{ organization: orgId, upcoming: true }}
            refreshKey={shiftsVersion}
            emptyText={isAdmin ? 'No upcoming shifts. Create the first one.' : 'No upcoming shifts yet.'}
          />
        </section>

        <aside className="stack">
          {isAdmin && <InvitePanel org={org.data} onChange={org.setData} />}
          <ClubMeetings orgId={orgId} isAdmin={isAdmin} />
          {isAdmin && <ClublyLinkForm org={org.data} onChange={org.setData} />}
          <MemberList orgId={orgId} isAdmin={isAdmin} onChanged={org.reload} />
        </aside>
      </div>
    </div>
  )
}

function InvitePanel({ org, onChange }) {
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)

  async function copy() {
    await navigator.clipboard.writeText(org.invite_code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  async function regenerate() {
    if (!window.confirm('Make a new code? The current one will stop working.')) return
    try {
      onChange(await api.organizations.regenerateInviteCode(org.id))
    } catch (err) {
      setError(err)
    }
  }

  return (
    <section className="card">
      <h3>Invite code</h3>
      <p className="muted small">Share this so people can join. Only admins can see it.</p>
      <div className="row">
        <code className="invite-code">{org.invite_code}</code>
        <button type="button" className="secondary" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
      </div>
      <button type="button" className="link-button" onClick={regenerate}>Regenerate code</button>
      <ErrorMessage error={error} />
    </section>
  )
}

function MemberList({ orgId, isAdmin, onChanged }) {
  const { user } = useAuth()
  const members = useApi(() => api.organizations.members(orgId), [orgId])
  const [error, setError] = useState(null)

  async function act(action) {
    setError(null)
    try {
      await action()
      // Reload the org too: if you demoted yourself, the page must stop showing admin tools.
      members.reload()
      onChanged()
    } catch (err) {
      setError(err)
    }
  }

  return (
    <section className="card">
      <h3>Members {members.data && <span className="muted">({members.data.length})</span>}</h3>
      <ErrorMessage error={members.error || error} />
      <ul className="members">
        {members.data?.map((m) => (
          <li key={m.id}>
            <div>
              <strong>{m.user.username}</strong>
              {m.user.id === user.id && <span className="muted"> (you)</span>}
              <div className="muted small">{m.user.email}</div>
            </div>
            {isAdmin ? (
              <div className="row">
                <select
                  value={m.role}
                  aria-label={`Role for ${m.user.username}`}
                  onChange={(e) => act(() => api.organizations.setRole(orgId, m.id, e.target.value))}
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
                {m.user.id !== user.id && (
                  <button
                    type="button"
                    className="link-button danger"
                    onClick={() => window.confirm(`Remove ${m.user.username}?`)
                      && act(() => api.organizations.removeMember(orgId, m.id))}
                  >
                    Remove
                  </button>
                )}
              </div>
            ) : (
              m.role === 'admin' && <span className="pill">Admin</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function ClublyLinkForm({ org, onChange }) {
  const [url, setUrl] = useState(org.clubly_url)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setError(null)
    try {
      onChange(await api.organizations.update(org.id, { clubly_url: url.trim() }))
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch (err) {
      setError(err)
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h3>Clubly page</h3>
      <p className="muted small">Link your club's page on Clubly so members can find it.</p>
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://clubly.org/yourclub"
        aria-label="Clubly URL"
      />
      <ErrorMessage error={error} />
      <button type="submit" className="secondary">{saved ? 'Saved' : 'Save link'}</button>
    </form>
  )
}
