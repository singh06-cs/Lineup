import { useState } from 'react'

import * as api from '../api'
import useApi from '../hooks/useApi'
import ErrorMessage from './ErrorMessage'
import ShiftCard from './ShiftCard'
import ShiftForm from './ShiftForm'

// A paginated list of shifts for the given API filters. Bump `refreshKey` to reload.
export default function ShiftList({ params, showOrg = false, emptyText, refreshKey = 0 }) {
  const paramsKey = JSON.stringify(params)
  const { data, setData, error, loading } = useApi(
    () => api.shifts.list(params),
    [paramsKey, refreshKey],
  )
  const [editingId, setEditingId] = useState(null)
  const [loadMoreError, setLoadMoreError] = useState(null)

  const replace = (updated) => setData((page) => ({
    ...page,
    results: page.results.map((s) => (s.id === updated.id ? updated : s)),
  }))
  const remove = (id) => setData((page) => ({
    ...page,
    count: page.count - 1,
    results: page.results.filter((s) => s.id !== id),
  }))

  async function loadMore() {
    try {
      const next = await api.shifts.nextPage(data.next)
      setData({ ...next, results: [...data.results, ...next.results] })
    } catch (err) {
      setLoadMoreError(err)
    }
  }

  if (loading && !data) return <p className="muted">Loading shifts…</p>
  if (error) return <ErrorMessage error={error} />
  if (data.results.length === 0) return <p className="muted empty">{emptyText}</p>

  return (
    <div className="stack">
      {data.results.map((shift) => (editingId === shift.id ? (
        <ShiftForm
          key={shift.id}
          shift={shift}
          onSaved={(saved) => { replace(saved); setEditingId(null) }}
          onCancel={() => setEditingId(null)}
        />
      ) : (
        <ShiftCard
          key={shift.id}
          shift={shift}
          showOrg={showOrg}
          onChange={replace}
          onDelete={remove}
          onEdit={(s) => setEditingId(s.id)}
        />
      )))}
      {data.next && (
        <button type="button" className="secondary" onClick={loadMore}>
          Load more ({data.count - data.results.length} left)
        </button>
      )}
      <ErrorMessage error={loadMoreError} />
    </div>
  )
}
