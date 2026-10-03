import { DAY_NAMES, formatTimeOfDay, minutesOfDay } from '../format'

const PX_PER_MINUTE = 0.9

// Side-by-side lanes for blocks that overlap on the same day (e.g. a club meeting
// during a class), so neither hides the other.
function assignLanes(blocks) {
  const laneEnds = []
  const placed = [...blocks]
    .sort((a, b) => a.start - b.start)
    .map((block) => {
      let lane = laneEnds.findIndex((end) => end <= block.start)
      if (lane === -1) lane = laneEnds.length
      laneEnds[lane] = block.end
      return { ...block, lane }
    })
  return placed.map((block) => ({ ...block, lanes: laneEnds.length }))
}

/**
 * Weekly calendar of recurring slots.
 * items: [{ key, label, sublabel, days: "MWF", start_time: "10:00:00", end_time, tone }]
 */
export default function WeekGrid({ items }) {
  const usesWeekend = items.some((item) => /[SU]/.test(item.days))
  const days = usesWeekend ? ['M', 'T', 'W', 'R', 'F', 'S', 'U'] : ['M', 'T', 'W', 'R', 'F']

  // Show 8am-6pm at minimum, stretched to fit early or late slots, on whole hours.
  const starts = items.map((i) => minutesOfDay(i.start_time))
  const ends = items.map((i) => minutesOfDay(i.end_time))
  const dayStart = Math.floor(Math.min(8 * 60, ...starts) / 60) * 60
  const dayEnd = Math.ceil(Math.max(18 * 60, ...ends) / 60) * 60
  const hours = []
  for (let m = dayStart; m < dayEnd; m += 60) hours.push(m)

  return (
    <div className="week-grid" style={{ '--days': days.length }}>
      <div className="week-corner" />
      {days.map((d) => <div key={d} className="week-day-name">{DAY_NAMES[d]}</div>)}

      <div className="week-hours" style={{ height: (dayEnd - dayStart) * PX_PER_MINUTE }}>
        {hours.map((m) => (
          <span key={m} style={{ top: (m - dayStart) * PX_PER_MINUTE }}>
            {formatTimeOfDay(`${m / 60}:00`).replace(':00 ', ' ')}
          </span>
        ))}
      </div>

      {days.map((day) => {
        const blocks = assignLanes(
          items
            .filter((item) => item.days.includes(day))
            .map((item) => ({ ...item, start: minutesOfDay(item.start_time), end: minutesOfDay(item.end_time) })),
        )
        return (
          <div key={day} className="week-column" style={{ height: (dayEnd - dayStart) * PX_PER_MINUTE }}>
            {hours.map((m) => (
              <div key={m} className="week-hour-line" style={{ top: (m - dayStart) * PX_PER_MINUTE }} />
            ))}
            {blocks.map((block) => (
              <div
                key={block.key}
                className={`week-block tone-${block.tone ?? 'class'}`}
                style={{
                  top: (block.start - dayStart) * PX_PER_MINUTE,
                  height: (block.end - block.start) * PX_PER_MINUTE,
                  left: `${(block.lane / block.lanes) * 100}%`,
                  width: `${100 / block.lanes}%`,
                }}
                title={`${block.label} ${formatTimeOfDay(block.start_time)}–${formatTimeOfDay(block.end_time)}`}
              >
                <strong>{block.label}</strong>
                <span>{block.sublabel}</span>
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}
