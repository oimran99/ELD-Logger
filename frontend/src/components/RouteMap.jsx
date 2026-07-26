import { MapContainer, TileLayer, Polyline, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Colored circular marker (avoids bundler issues with Leaflet's PNG icons).
function dot(color, label) {
  return L.divIcon({
    className: 'map-dot',
    html: `<span style="background:${color}">${label ?? ''}</span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  })
}

const CURRENT = dot('#16a34a', 'A')
const PICKUP = dot('#2563eb', 'P')
const DROPOFF = dot('#dc2626', 'D')

function stopColor(stop) {
  if (stop.kind === 'fuel') return '#d97706'
  if (stop.note.includes('restart')) return '#7c3aed'
  return '#6b7280' // rest / reset / break
}

export default function RouteMap({ route }) {
  const { points, geometry, stops } = route
  // Backend geometry is [lon, lat]; Leaflet wants [lat, lon].
  const line = geometry.map(([lon, lat]) => [lat, lon])
  const center = line.length
    ? line[Math.floor(line.length / 2)]
    : [points.current.lat, points.current.lon]

  return (
    <MapContainer center={center} zoom={5} className="route-map"
                  scrollWheelZoom>
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={line} pathOptions={{ color: '#2563eb', weight: 4 }} />

      <Marker position={[points.current.lat, points.current.lon]} icon={CURRENT}>
        <Popup><strong>Start</strong><br />{points.current.label}</Popup>
      </Marker>
      <Marker position={[points.pickup.lat, points.pickup.lon]} icon={PICKUP}>
        <Popup><strong>Pickup</strong><br />{points.pickup.label}</Popup>
      </Marker>
      <Marker position={[points.dropoff.lat, points.dropoff.lon]} icon={DROPOFF}>
        <Popup><strong>Drop-off</strong><br />{points.dropoff.label}</Popup>
      </Marker>

      {stops
        .filter((s) => !['Pickup (loading)', 'Drop-off (unloading)'].includes(s.note))
        .map((s, i) => (
          <Marker key={i} position={[s.lat, s.lon]} icon={dot(stopColor(s), '')}>
            <Popup>
              <strong>{s.note}</strong><br />
              {s.kind === 'fuel' && (
                <em>{s.verified ? 'Suggested fuel stop (OSM)' : 'Approx. fuel point — no station found'}</em>
              )}
              {s.kind === 'fuel' && <br />}
              {new Date(s.start).toLocaleString()}<br />
              {s.hours} h
            </Popup>
          </Marker>
        ))}
    </MapContainer>
  )
}
