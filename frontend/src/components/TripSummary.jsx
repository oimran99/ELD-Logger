export default function TripSummary({ summary, legs, warnings }) {
  const stat = (label, value) => (
    <div className="stat">
      <div className="stat__value">{value}</div>
      <div className="stat__label">{label}</div>
    </div>
  )
  return (
    <div className="summary">
      <div className="stats">
        {stat('Total distance', `${summary.total_distance_miles} mi`)}
        {stat('Driving time', `${summary.total_drive_hours} h`)}
        {stat('Trip duration', `${summary.total_duration_hours} h`)}
        {stat('Log days', summary.days_required)}
        {stat('Cycle used', `${summary.cycle_hours_start} → ${summary.cycle_hours_end} h`)}
      </div>
      <div className="legs">
        {legs.map((l, i) => (
          <div key={i} className="leg">
            <span className="leg__route">{l.from} → {l.to}</span>
            <span className="leg__meta">{l.distance_miles} mi · {l.drive_hours} h</span>
          </div>
        ))}
      </div>
      {warnings?.length > 0 && (
        <div className="warnings">
          {warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}
    </div>
  )
}
