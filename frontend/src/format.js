const dateTime = new Intl.DateTimeFormat(undefined, {
  weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
})
const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })

// The API sends UTC timestamps; Intl shows them in the viewer's own time zone.
export function formatShiftTime(startIso, endIso) {
  const start = new Date(startIso)
  const end = new Date(endIso)
  const sameDay = start.toDateString() === end.toDateString()
  return `${dateTime.format(start)} – ${sameDay ? time.format(end) : dateTime.format(end)}`
}

// <input type="datetime-local"> wants "YYYY-MM-DDTHH:mm" in LOCAL time, no zone.
export function toLocalInput(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  const offsetMs = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

// ...and the reverse: local input value -> UTC ISO string for the API.
export function fromLocalInput(value) {
  return value ? new Date(value).toISOString() : ''
}
