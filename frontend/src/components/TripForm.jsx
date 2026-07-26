import { useState } from 'react'

const EXAMPLE = {
  current_location: 'Dallas, TX',
  pickup_location: 'Oklahoma City, OK',
  dropoff_location: 'Denver, CO',
  current_cycle_used: 12,
}

export default function TripForm({ onSubmit, loading }) {
  const [form, setForm] = useState({
    current_location: '',
    pickup_location: '',
    dropoff_location: '',
    current_cycle_used: '',
  })

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = (e) => {
    e.preventDefault()
    onSubmit({
      ...form,
      current_cycle_used: Number(form.current_cycle_used || 0),
    })
  }

  return (
    <form className="trip-form" onSubmit={submit}>
      <label>
        Current location
        <input value={form.current_location} onChange={set('current_location')}
               placeholder="City, State" required />
      </label>
      <label>
        Pickup location
        <input value={form.pickup_location} onChange={set('pickup_location')}
               placeholder="City, State" required />
      </label>
      <label>
        Drop-off location
        <input value={form.dropoff_location} onChange={set('dropoff_location')}
               placeholder="City, State" required />
      </label>
      <label>
        Current cycle used (hrs)
        <input type="number" min="0" max="70" step="0.25"
               value={form.current_cycle_used}
               onChange={set('current_cycle_used')} placeholder="0–70" required />
      </label>
      <div className="trip-form__actions">
        <button type="submit" disabled={loading}>
          {loading ? 'Planning…' : 'Plan trip'}
        </button>
        <button type="button" className="secondary" disabled={loading}
                onClick={() => setForm(EXAMPLE)}>
          Fill example
        </button>
      </div>
    </form>
  )
}
