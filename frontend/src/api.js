// Thin client for the Django ELD backend.

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

export async function planTrip(input) {
  const res = await fetch(`${BASE}/plan-trip/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`)
  }
  return data
}

// Fetch the filled log-sheet PDF and trigger a browser download.
export async function downloadTripPdf(tripId, details) {
  const res = await fetch(`${BASE}/trips/${tripId}/pdf/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(details),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error || `Download failed (${res.status})`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `eld-logs-trip-${tripId}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
