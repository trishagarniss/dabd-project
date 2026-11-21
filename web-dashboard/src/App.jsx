import React, { useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowRight, BarChart3, Compass, Database, Gauge, Layers,
  Plane, RefreshCw, Route, Search, ShieldCheck, Timer, TrendingUp,
} from 'lucide-react'
import { MapContainer, Marker, Popup, TileLayer, Tooltip } from 'react-leaflet'
import { divIcon } from 'leaflet'

const API_BASE = 'http://localhost:8000/api/v1'
const headers = { 'x-api-key': import.meta.env.VITE_FDP_API_KEY || 'demo-viewer-key' }

function planeIcon(trackDeg) {
  const heading = Number.isFinite(Number(trackDeg)) ? Number(trackDeg) : 0
  return divIcon({
    className: 'fdp-plane-marker',
    html: `<div class="plane-icon" style="transform:rotate(${heading}deg)">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5L21 16z"/></svg>
    </div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
}

const num = (value, digits = 0) => {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function Card({ icon: Icon, label, value, hint, accent = 'sky' }) {
  const accents = {
    sky: 'bg-sky-500/10 text-sky-400 ring-sky-400/20',
    emerald: 'bg-emerald-500/10 text-emerald-400 ring-emerald-400/20',
    amber: 'bg-amber-500/10 text-amber-400 ring-amber-400/20',
    violet: 'bg-violet-500/10 text-violet-400 ring-violet-400/20',
  }
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</span>
        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ring-1 ${accents[accent]}`}>
          <Icon size={16} />
        </span>
      </div>
      <div className="mt-3 text-2xl font-semibold tracking-tight text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{hint}</div>
    </div>
  )
}

function Pill({ children, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-800/70 text-slate-300',
    sky: 'bg-sky-500/10 text-sky-300 ring-1 ring-sky-400/20',
    emerald: 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-400/20',
  }
  return <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${tones[tone]}`}>{children}</span>
}

export default function App() {
  const [tab, setTab] = useState('radar')
  const [flights, setFlights] = useState([])
  const [liveFlights, setLiveFlights] = useState([])
  const [experiments, setExperiments] = useState([])
  const [champion, setChampion] = useState(null)
  const [freshness, setFreshness] = useState(null)
  const [stats, setStats] = useState({ total: 0, avgDelay: 0, avgDistance: 0 })
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

  const fetchData = async () => {
    setRefreshing(true)
    try {
      const [mart, live, exp, health] = await Promise.all([
        fetch(`${API_BASE}/flights/date-range?start=${dateStart}&end=${dateEnd}&limit=200`, { headers }),
        fetch(`${API_BASE}/flights/active?limit=100`, { headers }),
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
  }

  useEffect(() => {
    fetchData()
    const timer = setInterval(fetchData, 15000)
    return () => clearInterval(timer)
  }, [dateStart, dateEnd])

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

  useEffect(() => {
    const values = (key) => filteredFlights
      .map((row) => Number(row[key]))
      .filter((v) => Number.isFinite(v))
    const delays = values('arr_delay_min')
    const distances = values('distance_km')
    const mean = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0
    setStats({
      total: filteredFlights.length,
      avgDelay: mean(delays).toFixed(1),
      avgDistance: mean(distances).toFixed(0),
    })
  }, [filteredFlights])

  const insights = useMemo(() => {
    if (!filteredFlights.length) return null
    const delays = filteredFlights
      .map((f) => Number(f.arr_delay_min))
      .filter((v) => Number.isFinite(v))
    const onTime = delays.length ? delays.filter((d) => d <= 15).length / delays.length : 0
    const worst = filteredFlights.reduce((best, row) =>
      Number(row.arr_delay_min) > Number(best?.arr_delay_min ?? -Infinity) ? row : best, null)
    const destinations = {}
    filteredFlights.forEach((f) => {
      const code = f.dest_airport || f.dest
      if (code) destinations[code] = (destinations[code] || 0) + 1
    })
    const busiest = Object.entries(destinations).sort((a, b) => b[1] - a[1])[0]
    return {
      onTime: `${(onTime * 100).toFixed(0)}%`,
      worst: worst ? `${worst.dest_airport || worst.dest} +${num(worst.arr_delay_min)}m` : '—',
      busiest: busiest ? `${busiest[0]} · ${busiest[1]}` : '—',
    }
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
      if (!response.ok) throw new Error(data.detail || 'Inference failed')
      setPrediction(data)
    } catch (error) {
      setPredictionError(error.message || String(error))
      setPrediction(null)
    }
  }

  const tabs = [
    { id: 'radar', label: 'Radar & Mart', icon: RadarIcon },
    { id: 'ml', label: 'ML & Insight', icon: BarChart3 },
    { id: 'architecture', label: 'Arsitektur', icon: Layers },
  ]

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-200">
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-sky-500/10 text-sky-400 ring-1 ring-sky-400/25">
              <Plane size={22} />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-white">SkyPulse</h1>
              <p className="text-xs text-slate-400">Flight telemetry · batch + streaming · on-premise</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Pill tone="emerald"><span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />LIVE · {freshness || '—'}</Pill>
            <button
              onClick={fetchData}
              disabled={refreshing}
              className="inline-flex items-center gap-2 rounded-lg bg-sky-500 px-3 py-2 text-xs font-semibold text-slate-950 transition hover:bg-sky-400 disabled:opacity-50"
            >
              <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-5 py-6">
        <section className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Card icon={Database} label="Flight records" value={num(stats.total)} hint="Gold mart · hasil filter" />
          <Card icon={Timer} label="Avg arrival delay" value={`${num(stats.avgDelay, 1)} m`} hint="Label nyata BTS" accent="amber" />
          <Card icon={Route} label="Avg route distance" value={`${num(stats.avgDistance)} km`} hint="Haversine OurAirports" accent="violet" />
          <Card icon={Activity} label="Live tracks" value={num(liveTracks.length)} hint="OpenSky → Redpanda" accent="emerald" />
        </section>

        <nav className="mb-5 flex gap-1 rounded-xl border border-slate-800 bg-slate-900/60 p-1">
          {tabs.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`inline-flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition ${
                tab === item.id ? 'bg-slate-800 text-white shadow' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <item.icon size={15} /> {item.label}
            </button>
          ))}
        </nav>

        {tab === 'radar' && (
          <div className="space-y-4">
            <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
              <div className="flex items-center justify-between px-4 py-3">
                <div>
                  <h2 className="text-sm font-semibold text-white">Live ADS-B Radar</h2>
                  <p className="text-xs text-slate-500">Pesawat bergerak mengikut heading · data refresh tiap 15 detik</p>
                </div>
                <Pill tone="sky">{liveTracks.length} aircraft</Pill>
              </div>
              <MapContainer center={[5, 20]} zoom={2} minZoom={2} scrollWheelZoom={false} className="radar-map">
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                {liveTracks.map((f) => (
                  <Marker
                    key={`${f.icao24}-${f.last_updated || ''}`}
                    position={[Number(f.latitude), Number(f.longitude)]}
                    icon={planeIcon(f.true_track_deg)}
                  >
                    <Tooltip direction="top" offset={[0, -6]}>{f.callsign || f.icao24}</Tooltip>
                    <Popup>
                      <strong>{f.callsign || f.icao24}</strong><br />
                      {f.origin_country || 'unknown'}<br />
                      Alt: {num(f.altitude_m)} m · Speed: {num(f.velocity_kmh)} km/h<br />
                      Heading: {num(f.true_track_deg)}°
                    </Popup>
                  </Marker>
                ))}
              </MapContainer>
            </section>

            {insights && (
              <section className="grid gap-3 md:grid-cols-3">
                <Card icon={ShieldCheck} label="On-time ≤ 15m" value={insights.onTime} hint="Proporsi dari baris terfilter" accent="emerald" />
                <Card icon={TrendingUp} label="Worst delay" value={insights.worst} hint="Arrival delay terbesar" accent="amber" />
                <Card icon={Compass} label="Busiest destination" value={insights.busiest} hint="Kode IATA · jumlah flight" accent="violet" />
              </section>
            )}

            <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <div className="relative min-w-56 flex-1">
                  <Search size={15} className="absolute left-3 top-2.5 text-slate-500" />
                  <input
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Cari flight atau airport…"
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 py-2 pl-9 pr-3 text-xs outline-none focus:border-sky-500"
                  />
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-400">
                  Jam ≤ {hourMax}
                  <input type="range" min="0" max="23" value={hourMax}
                    onChange={(e) => setHourMax(Number(e.target.value))}
                    className="accent-sky-500" />
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-400">
                  Destinasi
                  <select value={destination} onChange={(e) => setDestination(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs outline-none focus:border-sky-500">
                    {airports.map((code) => <option key={code}>{code}</option>)}
                  </select>
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-400">
                  <input type="date" value={dateStart} onChange={(e) => setDateStart(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs" />
                  →
                  <input type="date" value={dateEnd} onChange={(e) => setDateEnd(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs" />
                </label>
              </div>

              <div className="mb-3 rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2 text-[11px] text-sky-200/80">
                Reconciliation · {dateStart} → {dateEnd} · {num(reconciliation?.count)} rows ·
                avg delay {num(reconciliation?.avg_arr_delay_min, 2)} min · SQL: config/serving_queries.sql#Q10
              </div>

              <div className="max-h-96 overflow-auto rounded-lg border border-slate-800">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-slate-800/80 text-slate-400 backdrop-blur">
                    <tr>
                      {['Flight', 'Rute', 'Jarak', 'Jam', 'Dep delay', 'Arr delay'].map((h) => (
                        <th key={h} className="px-3 py-2.5 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {filteredFlights.slice(0, 60).map((f) => (
                      <tr key={f.flight_record_id} className="hover:bg-slate-800/40">
                        <td className="px-3 py-2 font-mono text-[11px] text-slate-300">{f.flight_record_id}</td>
                        <td className="px-3 py-2">
                          <span className="text-slate-200">{f.origin}</span>
                          <ArrowRight size={12} className="mx-1 inline text-slate-600" />
                          <span className="text-sky-300">{f.dest_airport || f.dest}</span>
                        </td>
                        <td className="px-3 py-2">{num(f.distance_km)} km</td>
                        <td className="px-3 py-2">{num(f.hour_of_day)}</td>
                        <td className="px-3 py-2">{num(f.dep_delay_min, 1)} m</td>
                        <td className="px-3 py-2">
                          <span className={`rounded px-1.5 py-0.5 ${Number(f.arr_delay_min) > 15 ? 'bg-amber-500/10 text-amber-300' : 'bg-emerald-500/10 text-emerald-300'}`}>
                            {Number(f.arr_delay_min) > 0 ? '+' : ''}{num(f.arr_delay_min, 1)} m
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!filteredFlights.length && (
                  <div className="p-8 text-center text-xs text-slate-500">Tidak ada baris cocok. Ubah filter atau jalankan pipeline batch.</div>
                )}
              </div>
            </section>
          </div>
        )}

        {tab === 'ml' && (
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-white">Champion model</h2>
                  <p className="text-xs text-slate-500">Dataset BTS nyata · tanpa data sintetik</p>
                </div>
                <Pill tone="sky">{champion?.model_version || experiments[0]?.model_version || '—'}</Pill>
              </div>
              <div className="space-y-3">
                {experiments.map((exp) => {
                  const rmse = Number(exp.metrics?.RMSE || 0)
                  const worst = Math.max(...experiments.map((e) => Number(e.metrics?.RMSE || 0)), 1)
                  const isChampion = champion?.model_version === exp.model_version
                    || exp.model_version === experiments[0]?.model_version
                  return (
                    <div key={exp.run_id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                      <div className="mb-2 flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-200">{exp.model_version} · {exp.model_type}</span>
                        {isChampion && <Pill tone="emerald">champion</Pill>}
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                        <div className="h-full rounded-full bg-sky-500" style={{ width: `${Math.max(4, (rmse / worst) * 100)}%` }} />
                      </div>
                      <div className="mt-2 flex gap-4 text-[11px] text-slate-400">
                        <span>RMSE {num(rmse, 2)}</span>
                        <span>MAE {num(exp.metrics?.MAE, 2)}</span>
                        <span>R² {num(exp.metrics?.R2_Score, 3)}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="mb-4">
                <h2 className="text-sm font-semibold text-white">Coba inference</h2>
                <p className="text-xs text-slate-500">Model champion dipanggil lewat API ber-otorisasi</p>
              </div>
              <form onSubmit={handlePredict} className="grid grid-cols-2 gap-3">
                {Object.entries(form).map(([key, value]) => (
                  <label key={key} className="text-[11px] text-slate-400">
                    {key.replaceAll('_', ' ')}
                    <input
                      type={typeof value === 'number' ? 'number' : 'text'}
                      step="any"
                      value={value}
                      onChange={(e) => setForm((prev) => ({
                        ...prev,
                        [key]: typeof value === 'number' ? Number(e.target.value) : e.target.value,
                      }))}
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-slate-100 outline-none focus:border-sky-500"
                    />
                  </label>
                ))}
                <button type="submit"
                  className="col-span-2 mt-1 rounded-lg bg-sky-500 py-2 text-xs font-semibold text-slate-950 hover:bg-sky-400">
                  Prediksi delay
                </button>
              </form>
              {prediction && (
                <div className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-emerald-200">
                  Predicted delay: <strong>{num(prediction.predicted_delay_min, 2)} min</strong> · model {prediction.model_version}
                </div>
              )}
              {predictionError && (
                <div className="mt-4 rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-xs text-rose-300">{predictionError}</div>
              )}
            </section>
          </div>
        )}

        {tab === 'architecture' && (
          <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
            <h2 className="mb-1 text-sm font-semibold text-white">Alur data lokal</h2>
            <p className="mb-6 text-xs text-slate-500">Batch dan stream bertemu di mart Gold, lalu disajikan API + dashboard.</p>
            <div className="grid gap-3 md:grid-cols-4">
              {[
                { icon: Database, title: 'Sources', text: 'OurAirports + BTS (batch), OpenSky (stream)' },
                { icon: Activity, title: 'Ingest', text: 'Redpanda, Bronze JSONL, quality gate + DLQ' },
                { icon: Layers, title: 'Lakehouse', text: 'Silver dedup → Gold 3 mart + feature store' },
                { icon: Gauge, title: 'Serving', text: 'FastAPI 13 endpoint, peta live, ML inference' },
              ].map((step, index) => (
                <div key={step.title} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <step.icon size={18} className="text-sky-400" />
                    <span className="text-[11px] text-slate-600">0{index + 1}</span>
                  </div>
                  <div className="text-xs font-semibold text-slate-100">{step.title}</div>
                  <p className="mt-1 text-[11px] leading-relaxed text-slate-400">{step.text}</p>
                </div>
              ))}
            </div>
            <div className="mt-6 flex flex-wrap gap-2 text-[11px] text-slate-400">
              <Pill>27 tests · 55% coverage</Pill>
              <Pill>10 SQL queries</Pill>
              <Pill>3 alerts firing + resolved</Pill>
              <Pill>backup & restore checksum</Pill>
            </div>
          </section>
        )}
      </main>

      <footer className="border-t border-slate-800 bg-slate-950/70">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-5 py-5 text-[11px] text-slate-500">
          <div className="flex items-center gap-2">
            <Plane size={14} className="text-sky-400" />
            <span>SkyPulse · TBP Advanced Data Platform · local/on-premise</span>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="hover:text-sky-300">API docs</a>
            <a href="http://localhost:3000" target="_blank" rel="noreferrer" className="hover:text-sky-300">Grafana</a>
            <a href="http://localhost:9090" target="_blank" rel="noreferrer" className="hover:text-sky-300">Prometheus</a>
            <span>F-01–F-20 · docs/EVIDENCE_INDEX.md</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

function RadarIcon({ size = 15 }) {
  return <Compass size={size} />
}
