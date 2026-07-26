import { useState } from 'react'
import { downloadTripPdf } from '../api'

const FIELDS = [
  ['driver_name', 'Driver name'],
  ['co_driver_name', 'Co-driver name'],
  ['carrier_name', 'Carrier name'],
  ['truck_trailer_numbers', 'Truck / trailer numbers'],
  ['main_office_address', 'Main office address'],
  ['home_terminal_address', 'Home terminal address'],
  ['shipping_document', 'DVL / Manifest no.'],
  ['shipper_commodity', 'Shipper & commodity'],
]

export default function LogDetailsForm({ tripId }) {
  const [open, setOpen] = useState(false)
  const [details, setDetails] = useState(
    Object.fromEntries(FIELDS.map(([k]) => [k, ''])),
  )
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')

  const set = (k) => (e) => setDetails({ ...details, [k]: e.target.value })

  const download = async () => {
    setDownloading(true)
    setError('')
    try {
      await downloadTripPdf(tripId, details)
    } catch (err) {
      setError(err.message)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="logdetails">
      <div className="logdetails__bar">
        <button type="button" className="secondary logdetails__toggle"
                onClick={() => setOpen(!open)}>
          {open ? '▾' : '▸'} Log sheet details (optional)
        </button>
        <button type="button" onClick={download} disabled={downloading}>
          {downloading ? 'Preparing…' : '⬇ Download log sheets (PDF)'}
        </button>
      </div>
      {open && (
        <div className="logdetails__grid">
          {FIELDS.map(([k, label]) => (
            <label key={k}>
              {label}
              <input value={details[k]} onChange={set(k)} />
            </label>
          ))}
        </div>
      )}
      {error && <div className="error">{error}</div>}
      <p className="logdetails__hint">
        These fields fill the log header. Leave blank to download with the grid
        only — they don’t affect the computed schedule.
      </p>
    </div>
  )
}
