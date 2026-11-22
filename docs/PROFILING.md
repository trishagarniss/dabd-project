# Profiling & Trade-off (F-19)

## Metode pengukuran
Skrip: `scripts/profile_pipeline.py`. Warm-up = 3 panggilan, sampel = 30 panggilan,
input sama (`data/gold/flight_delay_features.parquet`, 124 event Bronze, request API
`/api/v1/flights/active?limit=20`), seed = 42. Perangkat dan data mentah:
`evidence/profiling/summary.json`, `evidence/profiling/raw_metrics.csv`, log
`evidence/profiling/profile_run.txt`.

## Hasil (pengukuran sebenarnya)
| Metrik | p50 | p95 | Unit |
|---|---:|---:|---|
| Throughput tulis batch (Parquet upsert) | 43,381 | — | rows/s |
| Freshness event stream (umur event Bronze) | 571.4 | 813.4 | s |
| Latensi serving | 8.28 | 10.13 | ms |
| CPU proses | 23.1 | — | % |
| Memory proses | 219.2 | — | MB |
| Disk free | 395,054 | — | MB |

## Analisis
- **Sebelum vs sesudah:** sebelum perbaikan, consumer hanya `log.info` (0 baris ditulis
  ke Silver), tidak ada metrik, dan 4 unit test dengan coverage tidak dicatat. Sesudah:
  124 event di-replay → 116 diterima ke Silver/Gold + 8 DLQ, metrik dan log terstruktur,
  27 test lulus dengan coverage 55% (`evidence/test_output.txt`).
- **Bottleneck:** freshness p50 ~571s karena sampel Bronze adalah *snapshot statis* yang
  diambil sekitar 9 menit sebelum profiling, bukan aliran langsung. Producer sebenarnya
  polling tiap 30 detik; pada mode live freshness diperkirakan < 60s. Ini perlu diuji ulang
  dengan producer berjalan (rujuk alert B).
- **Serving:** p95 ~10 ms — jauh di bawah budget 200 ms; API membaca Parquet langsung.
- **Storage:** throughput ~43k rows/s memadai untuk 5k baris BTS per batch harian. Biaya
  utama adalah penulisan `version=*` tiap snapshot; retensi dibatasi 5 versi per dataset
  (`FDP_MAX_SNAPSHOT_VERSIONS`) dan perlu dipantau bila data bertambah.
- **Resource budget Docker:** Redpanda 768 MB, Postgres 512 MB, API 1 GB, consumer &
  producer 512 MB masing-masing, Prometheus 512 MB, Alertmanager 256 MB, Grafana 512 MB.
  Total nominal ~4.1 GB RAM; cocok untuk satu mesin demo.

## Trade-off utama
1. Parquet + Postgres (ADR-002): analitik cepat vs perlu sinkronisasi dua storage.
2. Redpanda lokal (ADR-001): replay/offset benar vs operasi broker perlu dipantau.
3. Tracking JSONL (ADR-004): ringan & dapat diaudit vs tidak ada UI MLflow.
4. Quality gate peringatan untuk kode bandara lama (ADR-003): data sah tidak dibuang vs
   perlu peninjauan manual pemetaan IATA.
