// Toggle buttons for the days a meeting repeats on. The value is the same compact
// string the API uses ("MWF", with R = Thursday), so students never type day letters.
const DAYS = [
  ['M', 'Mon'], ['T', 'Tue'], ['W', 'Wed'], ['R', 'Thu'], ['F', 'Fri'], ['S', 'Sat'], ['U', 'Sun'],
]

// onToggle(letter) instead of onChange(newValue): the parent applies it with a
// functional state update, so two quick clicks can't both start from the same old
// value and overwrite each other.
export default function DaysPicker({ value, onToggle, label = 'Days' }) {
  return (
    <div className="days-picker" role="group" aria-label={label}>
      {DAYS.map(([letter, name]) => (
        <button
          key={letter}
          type="button"
          className={value.includes(letter) ? 'day on' : 'day'}
          aria-pressed={value.includes(letter)}
          onClick={() => onToggle(letter)}
        >
          {name}
        </button>
      ))}
    </div>
  )
}
