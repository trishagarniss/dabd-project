import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowRight, ArrowUp, BarChart3, Clock, Cpu, Database, Gauge, Globe,
  Layers, MapPin, Plane, Radar, RefreshCw, Route, Search, ShieldCheck, Sparkles,
  Timer, Wind,
} from 'lucide-react'
import L from 'leaflet'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'

const API_BASE = 'http://localhost:8000/api/v1'
const headers = { 'x-api-key': import.meta.env.VITE_FDP_API_KEY || 'demo-viewer-key' }

const num = (value, digits = 0) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('id-ID', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

// Canvas renderer: ribuan pesawat digambar sekali per frame, bukan sebagai
// marker DOM. Tetap berputar sesuai true_track_deg dan punya tooltip saat hover.
const FleetLayer = L.Layer.extend({
  onAdd(map) {
    this._map = map
    this._canvas = L.DomUtil.create('canvas', 'fleet-canvas')
    Object.assign(this._canvas.style, {
      position: 'absolute', top: '0', left: '0', pointerEvents: 'auto', zIndex: 450,
    })
    map.getPanes().overlayPane.appendChild(this._canvas)

    this._tooltip = L.DomUtil.create('div', 'fleet-tooltip')
    this._tooltip.style.display = 'none'
    map.getContainer().appendChild(this._tooltip)

    this._onMove = (event) => {
      const hit = (this._points || []).find(
        (point) => Math.hypot(point.x - event.offsetX, point.y - event.offsetY) < 11,
      )
      if (!hit) {
        this._tooltip.style.display = 'none'
        return
      }
      const f = hit.flight
      this._tooltip.innerHTML = `<strong>${f.callsign?.trim() || f.icao24}</strong><br />`
        + `${f.origin_country || 'asal tidak diketahui'}<br />`
        + `Ketinggian ${num(f.altitude_m)} m · ${num(f.velocity_kmh)} km/jam<br />`
        + `Arah ${num(f.true_track_deg)}°`
      this._tooltip.style.left = `${event.offsetX + 14}px`
      this._tooltip.style.top = `${event.offsetY + 14}px`
      this._tooltip.style.display = 'block'
    }
    L.DomEvent.on(this._canvas, 'mousemove', this._onMove)

    map.on('move resize zoom viewreset', this.redraw, this)
    this.redraw()
  },

  onRemove(map) {
    map.off('move resize zoom viewreset', this.redraw, this)
    if (this._canvas) L.DomEvent.off(this._canvas, 'mousemove', this._onMove)
    this._tooltip?.remove()
    this._canvas?.remove()
  },

  setFlights(flights) {
    this._flights = flights
    this.redraw()
  },

  redraw() {
    const map = this._map
    const canvas = this._canvas
    if (!map || !canvas) return
    const size = map.getSize()
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = Math.round(size.x * dpr)
    canvas.height = Math.round(size.y * dpr)
    canvas.style.width = `${size.x}px`
    canvas.style.height = `${size.y}px`
    L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]))

    const ctx = canvas.getContext('2d')
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, size.x, size.y)
    this._points = []
    for (const f of this._flights || []) {
      const lat = Number(f.latitude)
      const lng = Number(f.longitude)
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue
      const point = map.latLngToContainerPoint([lat, lng])
      if (point.x < -16 || point.y < -16 || point.x > size.x + 16 || point.y > size.y + 16) continue
      this._points.push({ x: point.x, y: point.y, flight: f })

      const heading = Number(f.true_track_deg)
      ctx.save()
      ctx.translate(point.x, point.y)
      ctx.rotate(((Number.isFinite(heading) ? heading : 0) - 90) * Math.PI / 180)
      ctx.beginPath()
      ctx.moveTo(9, 0)
      ctx.lineTo(-6, 5.5)
      ctx.lineTo(-3, 0)
      ctx.lineTo(-6, -5.5)
      ctx.closePath()
      ctx.fillStyle = '#f5b942'
      ctx.fill()
      ctx.strokeStyle = 'rgba(8, 14, 22, 0.85)'
      ctx.lineWidth = 1
      ctx.stroke()
      ctx.restore()
    }
    this._tooltip.style.display = 'none'
  },
})

function AircraftLayer({ flights }) {
  const map = useMap()
  const layerRef = useRef(null)

  useEffect(() => {
    const layer = new FleetLayer()
    layer.setFlights(flights)
    layer.addTo(map)
    layerRef.current = layer
    return () => {
      layer.remove()
      layerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  useEffect(() => {
    layerRef.current?.setFlights(flights)
  }, [flights])

  return null
}

function LiveDot() {
  return <span className="dot" />
}

function Panel({ className = '', children }) {
  return <section className={`panel ${className}`}>{children}</section>
}

function Stat({ icon: Icon, label, value, unit, hint }) {
  return (
    <div className="bg-[#0b121c] px-5 py-4 sm:px-6 sm:py-5">
      <div className="flex items-start justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <Icon size={14} className="mt-0.5 shrink-0 text-[#4e6076]" />
      </div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="num text-[26px] font-semibold leading-none text-[#f2f7fd]">{value}</span>
        {unit && <span className="text-[11px] font-medium text-[#7d90a8]">{unit}</span>}
      </div>
      <p className="mt-1.5 text-[11px] leading-snug text-[#5f7189]">{hint}</p>
    </div>
  )
}

function LiveMap({ flights, freshness }) {
  // Tampilkan seluruh pesawat aktif tanpa batas marker (F-13).
  const visible = flights

  return (
    <Panel className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] px-5 py-3.5">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg border border-[rgba(245,185,66,.3)] bg-[var(--amber-dim)] text-[var(--amber)]">
            <Globe size={16} />
          </span>
          <div>
            <h2 className="text-[15px] font-semibold leading-tight text-[#e8eff8]">Ruang udara live</h2>
            <p className="mt-0.5 text-[10px] text-[#5f7189]">OpenSky Network · pembaruan 30 detik</p>
          </div>
        </div>
        <span className="chip chip-live">
          <LiveDot /> {num(flights.length)} pesawat
        </span>
      </div>

      <div className="relative flex-1">
        <MapContainer center={[1, 110]} zoom={3} minZoom={2} scrollWheelZoom={false} className="ops-map">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <AircraftLayer flights={visible} />
        </MapContainer>

        {!flights.length && (
          <div className="pointer-events-none absolute inset-0 z-[400] grid place-items-center">
            <div className="panel px-5 py-4 text-center">
              <p className="text-[12px] font-semibold text-[#dbe6f3]">Menunggu data live</p>
              <p className="mt-1 text-[10px] text-[#5f7189]">Pastikan producer OpenSky dan API berjalan.</p>
            </div>
          </div>
        )}

        <div className="pointer-events-none absolute bottom-2 left-2 z-[500] flex flex-wrap items-center gap-1.5">
          <span className="chip chip-dark"><MapPin size={10} /> Seluruh dunia</span>
          <span className="chip chip-dark"><Clock size={10} /> {freshness ? `${freshness} lalu` : 'sinkronisasi…'}</span>
          <span className="chip chip-dark">{num(visible.length)} marker</span>
        </div>
      </div>
    </Panel>
  )
}

function LivePanel({ flights }) {
  const sorted = useMemo(
    () => [...flights]
      .sort((a, b) => Number(b.altitude_m || 0) - Number(a.altitude_m || 0))
      .slice(0, 12),
    [flights],
  )
  const avgSpeed = useMemo(() => {
    const values = flights.map((f) => Number(f.velocity_kmh)).filter((v) => Number.isFinite(v))
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0
  }, [flights])
  const avgAlt = useMemo(() => {
    const values = flights.map((f) => Number(f.altitude_m)).filter((v) => Number.isFinite(v))
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0
  }, [flights])

  return (
    <Panel className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-5 py-3.5">
        <div>
          <span className="eyebrow">Live track</span>
          <h2 className="mt-1.5 text-[15px] font-semibold leading-tight text-[#e8eff8]">Pesawat terpantau</h2>
        </div>
        <span className="text-[10px] text-[#5f7189]">urut ketinggian</span>
      </div>

      <div className="grid grid-cols-2 gap-px border-b border-[var(--line)] bg-[var(--line)]">
        <div className="bg-[#0b121c] px-5 py-3">
          <p className="flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-[#5f7189]">
            <Wind size={10} /> Kecepatan
          </p>
          <p className="num mt-1.5 text-[15px] font-semibold text-[#e8eff8]">{num(avgSpeed)} <span className="text-[10px] font-medium text-[#66788f]">km/jam</span></p>
        </div>
        <div className="bg-[#0b121c] px-5 py-3">
          <p className="flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-[#5f7189]">
            <ArrowUp size={10} /> Ketinggian
          </p>
          <p className="num mt-1.5 text-[15px] font-semibold text-[#e8eff8]">{num(avgAlt)} <span className="text-[10px] font-medium text-[#66788f]">m</span></p>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {sorted.map((f) => (
          <div key={f.icao24} className="border-b border-[var(--line-soft)] px-5 py-2.5 transition hover:bg-[#0f1a27]">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="num truncate text-[12px] font-semibold text-[#e8eff8]">{f.callsign?.trim() || f.icao24}</p>
                <p className="truncate text-[10px] text-[#5f7189]">{f.origin_country || 'asal tidak diketahui'}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="num text-[11px] text-[#c3d0e0]">{num(f.altitude_m)} m</p>
                <p className="num text-[10px] text-[#5f7189]">{num(f.velocity_kmh)} km/j</p>
              </div>
            </div>
            <div className="mt-2 h-[2px] w-full overflow-hidden rounded-full bg-[#131d2a]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#8a5b12] to-[#f5b942]"
                style={{ width: `${Math.min(100, (Number(f.altitude_m) / 14000) * 100)}%` }}
              />
            </div>
          </div>
        ))}
        {!sorted.length && (
          <p className="px-5 py-10 text-center text-[11px] text-[#5f7189]">Belum ada pesawat yang dilacak.</p>
        )}
      </div>
    </Panel>
  )
}

export default function App() {
  const [tab, setTab] = useState('live')
  const [flights, setFlights] = useState([])
  const [liveFlights, setLiveFlights] = useState([])
  const [experiments, setExperiments] = useState([])
  const [champion, setChampion] = useState(null)
  const [freshness, setFreshness] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [hourMax, setHourMax] = useState(23)
  const [destination, setDestination] = useState('ALL')
  const [dateStart, setDateStart] = useState('2024-01-01')
  const [dateEnd, setDateEnd] = useState('2024-01-14')
  const [reconciliation, setReconciliation] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [prediction, setPrediction] = useState(null)
  const [predictionError, setPredictionError] = useState(null)
  const [form, setForm] = useState({
    input_record_id: 'FL_2024_00001', distance_km: 820.5, hour_of_day: 14,
    day_of_week: 2, month: 1, dep_delay_min: 5, taxi_out_min: 18, crs_elapsed_min: 140,
  })

  const fetchData = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true)
    try {
      const [mart, live, exp, health] = await Promise.all([
        fetch(`${API_BASE}/flights/date-range?start=${dateStart}&end=${dateEnd}&limit=200`, { headers }),
        fetch(`${API_BASE}/flights/active?limit=20000`, { headers }),
        fetch(`${API_BASE}/ml/experiments`, { headers }),
        fetch(`${API_BASE}/health`),
      ])
      if (mart.ok) {
        const json = await mart.json()
        setFlights(json.data || [])
        setReconciliation(json)
      }
      if (live.ok) {
        const json = await live.json()
        setLiveFlights(json.data || [])
        setFreshness(json.freshness || null)
      }
      if (exp.ok) {
        const json = await exp.json()
        setExperiments(json.experiments || [])
        setChampion(json.champion || null)
      }
      if (health.ok) {
        const json = await health.json()
        setFreshness((prev) => prev || `model ${json.model_version}`)
      }
    } catch (error) {
      console.warn('Backend API not available:', error)
    } finally {
      setRefreshing(false)
    }
  }, [dateStart, dateEnd])

  useEffect(() => {
    fetchData()
    const timer = setInterval(fetchData, 15000)
    return () => clearInterval(timer)
  }, [fetchData])

  const liveTracks = useMemo(
    () => liveFlights.filter((f) => Number.isFinite(f.latitude) && Number.isFinite(f.longitude)),
    [liveFlights],
  )

  const airports = useMemo(() => {
    const values = new Set(flights.map((f) => f.dest_airport || f.dest).filter(Boolean))
    return ['ALL', ...Array.from(values).slice(0, 40).sort()]
  }, [flights])

  const filteredFlights = useMemo(() => flights.filter((f) => {
    const hour = Number(f.hour_of_day ?? 0)
    const code = String(f.dest_airport || f.dest || '')
    const term = searchTerm.toLowerCase()
    return hour <= hourMax
      && (destination === 'ALL' || code === destination)
      && (!term || String(f.flight_record_id || '').toLowerCase().includes(term) || code.toLowerCase().includes(term))
  }), [flights, hourMax, destination, searchTerm])

  const stats = useMemo(() => {
    const values = (key) => filteredFlights
      .map((row) => Number(row[key]))
      .filter((v) => Number.isFinite(v))
    const delays = values('arr_delay_min')
    const distances = values('distance_km')
    const mean = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0
    return {
      total: filteredFlights.length,
      avgDelay: mean(delays).toFixed(1),
      avgDistance: mean(distances).toFixed(0),
      onTime: delays.length ? `${Math.round((delays.filter((d) => d <= 15).length / delays.length) * 100)}%` : '—',
    }
  }, [filteredFlights])

  const buckets = useMemo(() => {
    const groups = [
      { label: '≤ -15 mnt', tone: '#5ad1e6', test: (d) => d <= -15 },
      { label: '-15 – 15 mnt', tone: '#4ade80', test: (d) => d > -15 && d <= 15 },
      { label: '15 – 60 mnt', tone: '#f5b942', test: (d) => d > 15 && d <= 60 },
      { label: '60 – 120 mnt', tone: '#fb923c', test: (d) => d > 60 && d <= 120 },
      { label: '> 120 mnt', tone: '#f87171', test: (d) => d > 120 },
    ]
    const delays = filteredFlights.map((f) => Number(f.arr_delay_min)).filter((v) => Number.isFinite(v))
    const total = delays.length || 1
    return groups.map((group) => {
      const count = delays.filter(group.test).length
      return { ...group, count, pct: Math.round((count / total) * 100) }
    })
  }, [filteredFlights])

  const hourly = useMemo(() => {
    const counts = Array(24).fill(0)
    filteredFlights.forEach((f) => {
      const hour = Number(f.hour_of_day)
      if (Number.isInteger(hour) && hour >= 0 && hour <= 23) counts[hour] += 1
    })
    const max = Math.max(...counts, 1)
    const peak = counts.indexOf(Math.max(...counts))
    return { counts, max, peak }
  }, [filteredFlights])

  const topRoutes = useMemo(() => {
    const map = new Map()
    filteredFlights.forEach((f) => {
      const code = f.dest_airport || f.dest
      if (!code) return
      const entry = map.get(code) || { code, count: 0, delaySum: 0, delayN: 0 }
      entry.count += 1
      const delay = Number(f.arr_delay_min)
      if (Number.isFinite(delay)) { entry.delaySum += delay; entry.delayN += 1 }
      map.set(code, entry)
    })
    return [...map.values()]
      .sort((a, b) => b.count - a.count)
      .slice(0, 5)
      .map((entry) => ({ ...entry, avg: entry.delayN ? entry.delaySum / entry.delayN : NaN }))
  }, [filteredFlights])

  const handlePredict = async (event) => {
    event.preventDefault()
    setPredictionError(null)
    try {
      const response = await fetch(`${API_BASE}/ml/predict-delay`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Prediksi gagal')
      setPrediction(data)
    } catch (error) {
      setPredictionError(error.message || String(error))
      setPrediction(null)
    }
  }

  const championVersion = champion?.model_version || experiments[0]?.model_version
  const rmseValues = experiments.map((exp) => Number(exp.metrics?.RMSE || 0))
  const worstRmse = Math.max(...rmseValues, 1)

  const tabs = [
    { id: 'live', label: 'Live', icon: Activity },
    { id: 'batch', label: 'Data batch', icon: Database },
    { id: 'ml', label: 'Model', icon: Cpu },
    { id: 'architecture', label: 'Arsitektur', icon: Layers },
  ]

  const fieldLabels = {
    input_record_id: 'ID rekaman',
    distance_km: 'Jarak (km)',
    hour_of_day: 'Jam (0–23)',
    day_of_week: 'Hari (0–6)',
    month: 'Bulan (1–12)',
    dep_delay_min: 'Delay berangkat (mnt)',
    taxi_out_min: 'Taxi out (mnt)',
    crs_elapsed_min: 'Durasi terjadwal (mnt)',
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-[1000] border-b border-[var(--line)] bg-[#060a11]/90 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-3 px-4 sm:px-6">
          <button onClick={() => setTab('live')} className="flex shrink-0 items-center gap-2.5 text-left">
            <span className="grid h-8 w-8 place-items-center rounded-lg border border-[rgba(245,185,66,.35)] bg-[var(--amber-dim)] text-[var(--amber)]">
              <Radar size={16} />
            </span>
            <span>
              <span className="display block text-[15px] leading-tight text-[#eef4fb]">SkyPulse</span>
              <span className="block text-[8px] font-semibold uppercase tracking-[0.22em] text-[#5f7189]">Flight data platform</span>
            </span>
          </button>

          <nav className="hidden items-center gap-6 md:flex">
            {tabs.map((item) => (
              <button
                key={item.id}
                onClick={() => setTab(item.id)}
                className={`tab ${tab === item.id ? 'tab-active' : ''}`}
              >
                <item.icon size={13} /> {item.label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <span className="chip chip-live hidden sm:inline-flex"><LiveDot /> {num(liveTracks.length)} live</span>
            <span className="chip hidden lg:inline-flex"><Clock size={10} /> {freshness ? `${freshness} lalu` : '—'}</span>
            <button
              onClick={() => fetchData(true)}
              disabled={refreshing}
              className="btn-ghost btn-icon"
              title="Perbarui data"
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        <div className="mx-auto flex max-w-[1400px] gap-6 overflow-x-auto px-4 md:hidden">
          {tabs.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`tab ${tab === item.id ? 'tab-active' : ''}`}
            >
              <item.icon size={13} /> {item.label}
            </button>
          ))}
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1400px] space-y-5 px-4 pb-12 pt-5 sm:px-6">
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
            <span className="eyebrow">Ringkasan operasional</span>
            <div className="flex items-center gap-2">
              <span className="chip chip-cyan"><Clock size={10} /> {freshness ? `${freshness} lalu` : 'menunggu data'}</span>
              <span className="hidden text-[10px] text-[#5f7189] sm:inline">Gold mart · BTS Januari 2024</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-px border-t border-[var(--line)] bg-[var(--line)] lg:grid-cols-4">
            <Stat icon={Database} label="Penerbangan" value={num(stats.total)} unit="baris" hint="Gold mart · hasil filter" />
            <Stat icon={Timer} label="Rata-rata delay" value={num(stats.avgDelay, 1)} unit="mnt" hint="Label asli BTS" />
            <Stat icon={ShieldCheck} label="Tepat waktu" value={stats.onTime} hint="Delay tiba ≤ 15 menit" />
            <Stat icon={Route} label="Jarak rute" value={num(stats.avgDistance)} unit="km" hint="Haversine bandara" />
          </div>
        </Panel>

        {tab === 'live' && (
          <div className="grid gap-5 xl:grid-cols-[1.65fr_1fr]">
            <LiveMap flights={liveTracks} freshness={freshness} />
            <LivePanel flights={liveTracks} />
          </div>
        )}

        {tab === 'batch' && (
          <div className="space-y-5">
            <div className="grid gap-5 lg:grid-cols-3">
              <Panel>
                <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-5 py-3.5">
                  <div>
                    <span className="eyebrow">Ketepatan</span>
                    <h2 className="mt-1.5 text-[15px] font-semibold leading-tight text-[#e8eff8]">Distribusi delay tiba</h2>
                  </div>
                  <BarChart3 size={14} className="shrink-0 text-[#4e6076]" />
                </div>
                <div className="space-y-3 px-5 py-4">
                  {buckets.map((bucket) => (
                    <div key={bucket.label} className="flex items-center gap-3" title={`${bucket.count} penerbangan · ${bucket.pct}%`}>
                      <span className="num w-[84px] shrink-0 text-[10px] text-[#8ba0b8]">{bucket.label}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#131d2a]">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${Math.max(bucket.count ? 3 : 0, bucket.pct)}%`, background: bucket.tone }}
                        />
                      </div>
                      <span className="num w-8 shrink-0 text-right text-[10px] text-[#c3d0e0]">{bucket.count}</span>
                    </div>
                  ))}
                  <p className="pt-1 text-[10px] text-[#5f7189]">
                    {num(filteredFlights.length)} penerbangan terfilter · {stats.onTime} tepat waktu
                  </p>
                </div>
              </Panel>

              <Panel>
                <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-5 py-3.5">
                  <div>
                    <span className="eyebrow">Kepadatan</span>
                    <h2 className="mt-1.5 text-[15px] font-semibold leading-tight text-[#e8eff8]">Penerbangan per jam</h2>
                  </div>
                  <Clock size={14} className="shrink-0 text-[#4e6076]" />
                </div>
                <div className="px-5 py-4">
                  <div className="flex h-24 items-end gap-[3px]">
                    {hourly.counts.map((count, hour) => (
                      <div
                        key={hour}
                        className="flex-1 rounded-sm transition-all duration-300"
                        style={{
                          height: `${Math.max(count ? 4 : 1, (count / hourly.max) * 100)}%`,
                          background: hour === hourly.peak && count ? '#f5b942' : '#2b3d56',
                        }}
                        title={`${String(hour).padStart(2, '0')}.00 · ${count} penerbangan`}
                      />
                    ))}
                  </div>
                  <div className="mt-2 flex justify-between">
                    {['00', '06', '12', '18', '23'].map((label) => (
                      <span key={label} className="tick-label">{label}</span>
                    ))}
                  </div>
                  <p className="mt-3 text-[10px] text-[#5f7189]">
                    {filteredFlights.length
                      ? `Puncak ${String(hourly.peak).padStart(2, '0')}.00 · ${hourly.counts[hourly.peak]} penerbangan`
                      : 'Belum ada data pada filter ini'}
                  </p>
                </div>
              </Panel>

              <Panel>
                <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-5 py-3.5">
                  <div>
                    <span className="eyebrow">Tujuan</span>
                    <h2 className="mt-1.5 text-[15px] font-semibold leading-tight text-[#e8eff8]">Rute tersibuk</h2>
                  </div>
                  <MapPin size={14} className="shrink-0 text-[#4e6076]" />
                </div>
                <div className="space-y-3 px-5 py-4">
                  {topRoutes.map((route) => (
                    <div key={route.code} className="flex items-center gap-3">
                      <span className="num w-9 shrink-0 text-[12px] font-semibold text-[#e8eff8]">{route.code}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between gap-2 text-[10px]">
                          <span className="text-[#7d90a8]">{route.count} penerbangan</span>
                          <span className="num" style={{ color: route.avg > 15 ? '#f7cd75' : '#86efac' }}>
                            {num(route.avg, 1)} mnt
                          </span>
                        </div>
                        <div className="mt-1 h-1 overflow-hidden rounded-full bg-[#131d2a]">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-[#8a5b12] to-[#f5b942]"
                            style={{ width: `${(route.count / (topRoutes[0]?.count || 1)) * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                  {!topRoutes.length && <p className="py-8 text-center text-[11px] text-[#5f7189]">Belum ada rute pada filter ini.</p>}
                </div>
              </Panel>
            </div>

            <Panel>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] px-5 py-3.5">
                <div>
                  <span className="eyebrow">Eksplorasi</span>
                  <h2 className="mt-1.5 text-[15px] font-semibold leading-tight text-[#e8eff8]">Penerbangan historis BTS</h2>
                </div>
                <span className="chip chip-amber">{num(filteredFlights.length)} baris</span>
              </div>

              <div className="grid gap-3 border-b border-[var(--line)] px-5 py-4 md:grid-cols-2 xl:grid-cols-4">
                <label className="relative block">
                  <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#4e6076]" />
                  <input
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Cari penerbangan atau bandara"
                    className="input input-search"
                  />
                </label>

                <label className="flex items-center gap-3 rounded-[9px] border border-[var(--line)] bg-[#090f18] px-3 py-2">
                  <span className="num shrink-0 text-[10px] text-[#8ba0b8]">Jam ≤ {String(hourMax).padStart(2, '0')}</span>
                  <input
                    type="range"
                    min="0"
                    max="23"
                    value={hourMax}
                    onChange={(e) => setHourMax(Number(e.target.value))}
                    className="w-full"
                  />
                </label>

                <label className="flex items-center gap-2 rounded-[9px] border border-[var(--line)] bg-[#090f18] px-3 py-2">
                  <span className="shrink-0 text-[10px] text-[#8ba0b8]">Tujuan</span>
                  <select
                    value={destination}
                    onChange={(e) => setDestination(e.target.value)}
                    className="input input-flat"
                  >
                    {airports.map((code) => <option key={code}>{code}</option>)}
                  </select>
                </label>

                <div className="flex items-center gap-1.5 rounded-[9px] border border-[var(--line)] bg-[#090f18] px-2 py-1.5">
                  <input type="date" value={dateStart} onChange={(e) => setDateStart(e.target.value)}
                    className="input input-flat input-flat-sm" />
                  <ArrowRight size={11} className="shrink-0 text-[#4e6076]" />
                  <input type="date" value={dateEnd} onChange={(e) => setDateEnd(e.target.value)}
                    className="input input-flat input-flat-sm" />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] px-5 py-2 text-[10px] text-[#7d90a8]">
                <Globe size={11} className="text-[#5ad1e6]" />
                Rekonsiliasi {dateStart} → {dateEnd} · {num(reconciliation?.count)} baris · rata-rata delay {num(reconciliation?.avg_arr_delay_min, 2)} mnt · SQL config/serving_queries.sql#Q10
              </div>

              <div className="max-h-[420px] overflow-auto">
                <table className="ops-table">
                  <thead>
                    <tr>
                      {['Penerbangan', 'Rute', 'Jarak', 'Jam', 'Delay berangkat', 'Delay tiba'].map((heading) => (
                        <th key={heading}>{heading}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredFlights.slice(0, 80).map((f) => {
                      const late = Number(f.arr_delay_min) > 15
                      return (
                        <tr key={f.flight_record_id}>
                          <td className="num cell-mono">{f.flight_record_id}</td>
                          <td>
                            <span className="font-medium text-[#c3d0e0]">{f.origin}</span>
                            <ArrowRight size={11} className="mx-1 inline text-[#3d4f66]" />
                            <span className="font-semibold text-[#e8eff8]">{f.dest_airport || f.dest}</span>
                          </td>
                          <td className="num">{num(f.distance_km)} km</td>
                          <td className="num">{num(f.hour_of_day)}</td>
                          <td className="num">{num(f.dep_delay_min, 1)} mnt</td>
                          <td>
                            <span className={`delay-pill ${late ? 'delay-late' : 'delay-ok'}`}>
                              {Number(f.arr_delay_min) > 0 ? '+' : ''}{num(f.arr_delay_min, 1)} mnt
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {!filteredFlights.length && (
                  <p className="px-5 py-12 text-center text-[11px] text-[#5f7189]">
                    Tidak ada baris yang cocok. Ubah filter atau jalankan pipeline batch.
                  </p>
                )}
              </div>
            </Panel>
          </div>
        )}

        {tab === 'ml' && (
          <div className="grid gap-5 lg:grid-cols-2">
            <Panel>
              <div className="flex items-start justify-between gap-3 border-b border-[var(--line)] px-5 py-3.5">
                <div>
                  <span className="eyebrow">Model juara</span>
                  <h2 className="mt-1.5 text-[15px] font-semibold leading-tight text-[#e8eff8]">Perbandingan eksperimen</h2>
                  <p className="mt-1 text-[10px] text-[#5f7189]">Dataset BTS asli · split 80/20 · seed 42</p>
                </div>
                <span className="chip chip-amber"><Cpu size={10} /> {championVersion || '—'}</span>
              </div>

              <div className="space-y-2.5 px-5 py-4">
                {experiments.map((exp) => {
                  const rmse = Number(exp.metrics?.RMSE || 0)
                  const isChampion = exp.model_version === championVersion
                  return (
                    <div
                      key={exp.run_id || exp.model_version}
                      className={`rounded-xl border px-4 py-3 ${
                        isChampion
                          ? 'border-[rgba(245,185,66,.32)] bg-[rgba(245,185,66,.06)]'
                          : 'border-[var(--line)] bg-[#0a121c]'
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="num text-[12px] font-semibold text-[#e8eff8]">{exp.model_version}</span>
                          <span className="text-[11px] text-[#7d90a8]">{exp.model_type}</span>
                          {isChampion && <span className="chip chip-amber chip-sm"><Sparkles size={10} /> juara</span>}
                        </div>
                        <div className="num flex gap-4 text-[10px] text-[#66788f]">
                          <span>RMSE <b className="text-[#e8eff8]">{num(rmse, 2)}</b></span>
                          <span>MAE <b className="text-[#c3d0e0]">{num(exp.metrics?.MAE, 2)}</b></span>
                          <span>R² <b className="text-[#c3d0e0]">{num(exp.metrics?.R2_Score, 3)}</b></span>
                        </div>
                      </div>
                      <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-[#131d2a]">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.max(6, (rmse / worstRmse) * 100)}%`,
                            background: isChampion ? '#f5b942' : '#2c3e57',
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
                {!experiments.length && (
                  <p className="rounded-xl border border-dashed border-[var(--line)] px-4 py-8 text-center text-[11px] text-[#5f7189]">
                    Belum ada hasil eksperimen. Jalankan retraining lebih dulu.
                  </p>
                )}
                <p className="pt-1 text-[10px] text-[#5f7189]">
                  Juara dipilih otomatis dari RMSE terkecil, dicatat di data/gold/model_registry.json.
                </p>
              </div>
            </Panel>

            <Panel>
              <div className="border-b border-[var(--line)] px-5 py-3.5">
                <span className="eyebrow">Inference</span>
                <h2 className="mt-1.5 text-[15px] font-semibold leading-tight text-[#e8eff8]">Coba prediksi delay</h2>
                <p className="mt-1 text-[10px] text-[#5f7189]">Model juara dipanggil lewat API ber-otorisasi.</p>
              </div>

              <form onSubmit={handlePredict} className="grid grid-cols-2 gap-3 px-5 py-4">
                {Object.entries(form).map(([key, value]) => (
                  <label key={key} className={`text-[10px] font-medium text-[#7d90a8] ${key === 'input_record_id' ? 'col-span-2' : ''}`}>
                    {fieldLabels[key] || key.replaceAll('_', ' ')}
                    <input
                      type={typeof value === 'number' ? 'number' : 'text'}
                      step="any"
                      value={value}
                      onChange={(e) => setForm((prev) => ({
                        ...prev,
                        [key]: typeof value === 'number' ? Number(e.target.value) : e.target.value,
                      }))}
                      className="input mt-1"
                    />
                  </label>
                ))}
                <button type="submit" className="btn-primary col-span-2 mt-1">
                  <Sparkles size={13} /> Prediksi delay
                </button>
              </form>

              <div className="px-5 pb-4">
                {prediction && (() => {
                  const value = Number(prediction.predicted_delay_min)
                  const late = value > 15
                  return (
                    <div className={`rounded-xl border px-4 py-3 ${
                      late
                        ? 'border-[rgba(245,185,66,.32)] bg-[rgba(245,185,66,.06)]'
                        : 'border-[rgba(74,222,128,.26)] bg-[rgba(74,222,128,.06)]'
                    }`}>
                      <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#7d90a8]">Perkiraan keterlambatan</p>
                      <div className="mt-1.5 flex flex-wrap items-baseline gap-2">
                        <span className="num text-[26px] font-semibold leading-none text-[#f2f7fd]">{num(value, 1)}</span>
                        <span className="text-[11px] text-[#7d90a8]">menit</span>
                        <span className={`chip ${late ? 'chip-amber' : 'chip-live'}`}>{late ? 'terlambat' : 'tepat waktu'}</span>
                      </div>
                      <p className="mt-1.5 text-[10px] text-[#5f7189]">model {prediction.model_version}</p>
                    </div>
                  )
                })()}
                {predictionError && (
                  <div className="rounded-xl border border-[rgba(248,113,113,.3)] bg-[rgba(248,113,113,.07)] px-4 py-3 text-[11px] text-[#fca5a5]">
                    {predictionError}
                  </div>
                )}
              </div>
            </Panel>
          </div>
        )}

        {tab === 'architecture' && (
          <div className="space-y-5">
            <Panel>
              <div className="border-b border-[var(--line)] px-5 py-3.5">
                <span className="eyebrow">Alur data</span>
                <h2 className="mt-1.5 text-[15px] font-semibold leading-tight text-[#e8eff8]">Dari sumber ke dashboard</h2>
                <p className="mt-1 max-w-2xl text-[10px] leading-relaxed text-[#5f7189]">
                  Batch dan stream bertemu di mart Gold, lalu disajikan lewat API, peta live, dan dashboard ini.
                </p>
              </div>
              <div className="grid gap-4 px-5 py-5 md:grid-cols-2 xl:grid-cols-4">
                {[
                  { icon: Database, title: 'Sumber', text: 'OurAirports dan BTS untuk batch, OpenSky untuk stream live.', meta: '5.282 bandara · 4.160 penerbangan' },
                  { icon: Activity, title: 'Ingest', text: 'Redpanda, Bronze JSONL, quality gate, dan DLQ.', meta: 'event-time · dedup · lateness' },
                  { icon: Layers, title: 'Lakehouse', text: 'Silver dedup lalu Gold mart dan feature store.', meta: 'parquet berversi · lineage' },
                  { icon: Gauge, title: 'Serving', text: 'FastAPI, peta live, prediksi ML, dan observability.', meta: 'RBAC · metrics · alert' },
                ].map((step, index) => (
                  <div key={step.title} className="rounded-xl border border-[var(--line)] bg-[#0a121c] px-4 py-4">
                    <div className="flex items-center justify-between gap-2">
                      <step.icon size={17} className="text-[var(--amber)]" />
                      <span className="num text-[10px] text-[#3d4f66]">0{index + 1}</span>
                    </div>
                    <h3 className="mt-3 text-[13px] font-semibold text-[#e8eff8]">{step.title}</h3>
                    <p className="mt-1 text-[10px] leading-relaxed text-[#7d90a8]">{step.text}</p>
                    <p className="mt-2.5 border-t border-[var(--line-soft)] pt-2 text-[9px] uppercase tracking-[0.1em] text-[#4e6076]">{step.meta}</p>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel>
              <div className="flex flex-wrap items-center gap-2 px-5 py-4">
                <span className="eyebrow mr-1">Bukti</span>
                <span className="chip chip-amber">27 pengujian</span>
                <span className="chip">coverage 55%</span>
                <span className="chip">10 query SQL</span>
                <span className="chip chip-live">3 alert resolved</span>
                <span className="chip">backup + restore checksum</span>
              </div>
            </Panel>
          </div>
        )}
      </main>

      <footer className="border-t border-[var(--line)]">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-5 text-[10px] text-[#5f7189] sm:px-6">
          <div className="flex items-center gap-2">
            <Plane size={12} className="-rotate-45 text-[var(--amber)]" />
            <span>SkyPulse · TBP Advanced Data Platform · local/on-premise</span>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="transition hover:text-[#e8eff8]">Dokumentasi API</a>
            <a href="http://localhost:3000" target="_blank" rel="noreferrer" className="transition hover:text-[#e8eff8]">Grafana</a>
            <a href="http://localhost:9090" target="_blank" rel="noreferrer" className="transition hover:text-[#e8eff8]">Prometheus</a>
            <span>F-01–F-20 · docs/EVIDENCE_INDEX.md</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
