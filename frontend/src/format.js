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

const dateTimeShort = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function formatDateTime(iso) {
  return dateTimeShort.format(new Date(iso))
}

export const DAY_NAMES = { M: 'Mon', T: 'Tue', W: 'Wed', R: 'Thu', F: 'Fri', S: 'Sat', U: 'Sun' }

// "14:10:00" (a campus wall-clock time from the API) -> "2:10 PM"
export function formatTimeOfDay(value) {
  const [hours, minutes] = value.split(':').map(Number)
  const suffix = hours >= 12 ? 'PM' : 'AM'
  return `${hours % 12 || 12}:${String(minutes).padStart(2, '0')} ${suffix}`
}

export function minutesOfDay(value) {
  const [hours, minutes] = value.split(':').map(Number)
  return hours * 60 + minutes
}

// "MWF" -> "Mon/Wed/Fri" (UC Davis letters, with R = Thursday, are easy to misread)
export function formatDays(days) {
  return [...days].map((letter) => DAY_NAMES[letter]).join('/')
}

export function formatSlot(slot) {
  return `${formatDays(slot.days)} ${formatTimeOfDay(slot.start_time)}–${formatTimeOfDay(slot.end_time)}`
}

// Add or remove one day letter, keeping weekday order: toggleDay("MF", "W") -> "MWF"
export function toggleDay(days, letter) {
  const chosen = new Set(days)
  if (chosen.has(letter)) chosen.delete(letter)
  else chosen.add(letter)
  return 'MTWRFSU'.split('').filter((l) => chosen.has(l)).join('')
}

// The term that's in session now, otherwise the next one, otherwise the latest.
export function pickCurrentTerm(terms) {
  const today = new Date().toLocaleDateString('en-CA') // local YYYY-MM-DD
  return terms.find((t) => t.instruction_ends >= today) ?? terms[terms.length - 1]
}
