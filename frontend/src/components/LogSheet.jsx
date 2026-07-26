// Draws one FMCSA daily log grid (24h x 4 duty rows) from a day's segments.

const ROWS = [
  { key: 'off_duty', label: '1. Off Duty' },
  { key: 'sleeper', label: '2. Sleeper Berth' },
  { key: 'driving', label: '3. Driving' },
  { key: 'on_duty', label: '4. On Duty (not driving)' },
]
const ROW_INDEX = { off_duty: 0, sleeper: 1, driving: 2, on_duty: 3 }

// Grid geometry (SVG user units).
const LEFT = 150 // room for row labels
const RIGHT_TOTAL = 70 // "Total Hours" column
const TOP = 26 // hour-number strip
const HOUR_W = 34
const ROW_H = 30
const GRID_W = HOUR_W * 24
const GRID_H = ROW_H * 4
const WIDTH = LEFT + GRID_W + RIGHT_TOTAL
const HEIGHT = TOP + GRID_H + 24

const STATUS_COLOR = {
  off_duty: '#6b7280',
  sleeper: '#7c3aed',
  driving: '#2563eb',
  on_duty: '#d97706',
}

function hourLabel(h) {
  if (h === 0 || h === 24) return 'M'
  if (h === 12) return 'N'
  return String(h % 12)
}

// Minutes from the day's midnight for an ISO datetime on that day.
function minutesInto(iso, dateKey) {
  const t = new Date(iso)
  const midnight = new Date(`${dateKey}T00:00:00`)
  return (t - midnight) / 60000
}

function xForMinutes(min) {
  return LEFT + (min / 1440) * GRID_W
}

function rowY(statusKey) {
  return TOP + ROW_INDEX[statusKey] * ROW_H + ROW_H / 2
}

export default function LogSheet({ day, index }) {
  const segments = day.segments || []

  // Build the stepped duty-status line.
  const points = []
  segments.forEach((seg) => {
    let sMin = Math.max(0, minutesInto(seg.start, day.date))
    let eMin = Math.min(1440, minutesInto(seg.end, day.date))
    if (eMin <= sMin) return
    const y = rowY(seg.status)
    points.push([xForMinutes(sMin), y])
    points.push([xForMinutes(eMin), y])
  })
  // Insert vertical connectors between successive horizontal runs.
  const path = []
  for (let i = 0; i < points.length; i += 2) {
    const [x1, y] = points[i]
    const [x2] = points[i + 1]
    if (i === 0) path.push(`M ${x1} ${y}`)
    else path.push(`L ${x1} ${y}`) // vertical connector to new row at same x
    path.push(`L ${x2} ${y}`)
  }

  const dateLabel = new Date(`${day.date}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
  })

  return (
    <div className="logsheet">
      <div className="logsheet__head">
        <h3>Day {index + 1} — {dateLabel}</h3>
        <div className="logsheet__miles">{day.driving_miles} mi driven</div>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="logsheet__svg" role="img"
           aria-label={`Daily log for ${day.date}`}>
        {/* Hour number strip */}
        {Array.from({ length: 25 }, (_, h) => (
          <text key={`hl${h}`} x={xForMinutes(h * 60)} y={TOP - 10}
                textAnchor="middle" className="ls-hour">{hourLabel(h)}</text>
        ))}

        {/* Row bands + labels + right totals */}
        {ROWS.map((row, r) => {
          const yTop = TOP + r * ROW_H
          return (
            <g key={row.key}>
              <rect x={LEFT} y={yTop} width={GRID_W} height={ROW_H}
                    className="ls-rowband" />
              <text x={LEFT - 8} y={yTop + ROW_H / 2} textAnchor="end"
                    dominantBaseline="middle" className="ls-rowlabel">
                {row.label}
              </text>
              <text x={LEFT + GRID_W + RIGHT_TOTAL / 2} y={yTop + ROW_H / 2}
                    textAnchor="middle" dominantBaseline="middle"
                    className="ls-total">
                {(day.totals?.[row.key] ?? 0).toFixed(2)}
              </text>
            </g>
          )
        })}

        {/* Quarter-hour minor lines */}
        {Array.from({ length: 24 * 4 + 1 }, (_, q) => {
          const x = LEFT + (q / (24 * 4)) * GRID_W
          const isHour = q % 4 === 0
          return (
            <line key={`q${q}`} x1={x} y1={TOP} x2={x} y2={TOP + GRID_H}
                  className={isHour ? 'ls-hourline' : 'ls-quarterline'} />
          )
        })}

        {/* Row separators */}
        {Array.from({ length: 5 }, (_, r) => (
          <line key={`rs${r}`} x1={LEFT} y1={TOP + r * ROW_H}
                x2={LEFT + GRID_W} y2={TOP + r * ROW_H} className="ls-hourline" />
        ))}

        {/* Duty-status line */}
        <path d={path.join(' ')} className="ls-dutyline" fill="none" />

        {/* Right total header */}
        <text x={LEFT + GRID_W + RIGHT_TOTAL / 2} y={TOP - 10}
              textAnchor="middle" className="ls-hour">Total</text>
      </svg>

      {/* Remarks: the notable events of the day */}
      <Remarks segments={segments} date={day.date} />
    </div>
  )
}

function Remarks({ segments, date }) {
  const events = segments.filter(
    (s) => s.note && s.note !== 'Off duty' && s.status !== 'driving',
  )
  if (events.length === 0) return null
  return (
    <div className="remarks">
      <span className="remarks__label">Remarks:</span>
      <ul>
        {events.map((s, i) => {
          const t = new Date(s.start).toLocaleTimeString(undefined, {
            hour: '2-digit', minute: '2-digit',
          })
          const isFuel = s.note.startsWith('Fueling')
          const suffix = isFuel
            ? (s.verified ? ' (suggested stop)' : ' (approx. — no station found)')
            : (s.location ? ` @ ${s.location}` : '')
          return (
            <li key={i}>
              <strong>{t}</strong> — {s.note}{suffix}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
