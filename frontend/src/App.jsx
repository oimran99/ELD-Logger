import { useState } from 'react'
import { planTrip } from './api'
import TripForm from './components/TripForm'
import TripSummary from './components/TripSummary'
import RouteMap from './components/RouteMap'
import LogSheet from './components/LogSheet'
import LogDetailsForm from './components/LogDetailsForm'
import './App.css'

export default function App() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (input) => {
    setLoading(true)
    setError('')
    try {
      const data = await planTrip(input)
      setResult(data)
    } catch (err) {
      setError(err.message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="app__header">
        <h1>ELD Trip Planner</h1>
        <p>FMCSA-compliant route &amp; daily-log generator · property carrier · 70 hr / 8 day</p>
      </header>

      <main className="app__main">
        <aside className="app__sidebar">
          <TripForm onSubmit={handleSubmit} loading={loading} />
          {error && <div className="error">{error}</div>}
        </aside>

        <section className="app__content">
          {!result && !loading && (
            <div className="placeholder">
              Enter trip details to generate the route and daily logs.
            </div>
          )}
          {loading && <div className="placeholder">Planning your trip…</div>}

          {result && (
            <>
              <TripSummary
                summary={result.plan.summary}
                legs={result.route.legs}
                warnings={result.plan.warnings}
              />
              <RouteMap route={result.route} />
              <div className="logs">
                <div className="logs__head">
                  <h2>Daily Log Sheets</h2>
                </div>
                <LogDetailsForm tripId={result.trip_id} />
                {result.plan.days.map((day, i) => (
                  <LogSheet key={day.date} day={day} index={i} />
                ))}
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  )
}
