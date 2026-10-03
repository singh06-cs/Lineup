import { useEffect, useState } from 'react'

import * as api from '../api'
import ShiftList from '../components/ShiftList'
import useApi from '../hooks/useApi'

export default function ShiftsPage() {
  const orgs = useApi(() => api.organizations.list())
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [organization, setOrganization] = useState('')
  const [availableOnly, setAvailableOnly] = useState(false)
  const [mineOnly, setMineOnly] = useState(false)

  // Wait until typing pauses before searching, instead of one request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])

  // Unchecked boxes send nothing ('' is dropped), not "false": available=false would
  // mean "only full shifts", which isn't what an unchecked box means.
  const params = {
    upcoming: true,
    organization,
    search: debouncedSearch,
    available: availableOnly ? true : '',
    mine: mineOnly ? true : '',
  }

  return (
    <div className="stack">
      <h1>Browse shifts</h1>
      <div className="card filters">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search title, location…"
          aria-label="Search shifts"
        />
        <select value={organization} onChange={(e) => setOrganization(e.target.value)} aria-label="Organization">
          <option value="">All my organizations</option>
          {orgs.data?.results.map((org) => (
            <option key={org.id} value={org.id}>{org.name}</option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={availableOnly} onChange={(e) => setAvailableOnly(e.target.checked)} />
          Has open spots
        </label>
        <label className="check">
          <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} />
          Signed up
        </label>
      </div>
      <ShiftList params={params} showOrg emptyText="No shifts match these filters." />
    </div>
  )
}
