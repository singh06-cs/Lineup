import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import * as api from '../api'
import ErrorMessage from '../components/ErrorMessage'
import ShiftList from '../components/ShiftList'
import useApi from '../hooks/useApi'

export default function DashboardPage() {
  const orgs = useApi(() => api.organizations.list())

  return (
    <div className="dashboard">
      <section>
        <h2>My upcoming shifts</h2>
        <ShiftList
          params={{ mine: true, upcoming: true }}
          showOrg
          emptyText="You haven't signed up for anything yet. Browse shifts to find one."
        />
      </section>

      <aside className="stack">
        <section>
          <h2>My organizations</h2>
          {orgs.loading && <p className="muted">Loading…</p>}
          <ErrorMessage error={orgs.error} />
          {orgs.data?.results.length === 0 && (
            <p className="muted empty">You're not in any organizations yet. Create one or join with a code.</p>
          )}
          <ul className="org-list">
            {orgs.data?.results.map((org) => (
              <li key={org.id}>
                <Link to={`/orgs/${org.id}`} className="card org-link">
                  <strong>{org.name}</strong>
                  <span className="muted small">
                    {org.member_count} {org.member_count === 1 ? 'member' : 'members'}
                    {org.my_role === 'admin' && <span className="pill">Admin</span>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
        <JoinOrgForm />
        <CreateOrgForm />
      </aside>
    </div>
  )
}

function JoinOrgForm() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [error, setError] = useState(null)

  async function submit(event) {
    event.preventDefault()
    setError(null)
    try {
      const org = await api.organizations.join(code.trim())
      navigate(`/orgs/${org.id}`)
    } catch (err) {
      setError(err.status === 404 ? new Error('No organization has that invite code.') : err)
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h3>Join with an invite code</h3>
      <div className="row">
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. 2t_UiD1P" required />
        <button type="submit">Join</button>
      </div>
      <ErrorMessage error={error} />
    </form>
  )
}

function CreateOrgForm() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState(null)

  async function submit(event) {
    event.preventDefault()
    setError(null)
    try {
      const org = await api.organizations.create({ name, description })
      navigate(`/orgs/${org.id}`)
    } catch (err) {
      setError(err)
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h3>Create an organization</h3>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" required maxLength={100} />
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" rows={2} />
      <ErrorMessage error={error} />
      <button type="submit">Create</button>
    </form>
  )
}
