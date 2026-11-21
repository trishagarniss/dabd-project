# Profiling & Trade-off (F-19)

## Kaedah pengukuran
Skrip: `scripts/profile_pipeline.py`. Warm-up = 3 panggilan, sampel = 30 panggilan,
input sama (`data/gold/flight_delay_features.parquet`, 124 event Bronze, request API
`/api/v1/flights/active?limit=20`), seed = 42. Hardware dan mentah:
`evidence/profiling/summary.json`, `evidence/profiling/raw_metrics.csv`, log
`evidence/profiling/profile_run.txt`.

## Keputusan (ukuran sebenar)
| Metrik | p50 | p95 | Unit |
|---|---:|---:|---|
| Throughput tulis batch (Parquet upsert) | 43,381 | — | rows/s |
| Freshness event stream (umur event Bronze) | 571.4 | 813.4 | s |
| Latensi serving | 8.28 | 10.13 | ms |
| CPU proses | 23.1 | — | % |
| Memory proses | 219.2 | — | MB |
| Disk free | 395,054 | — | MB |

## Analisis
- **Sebelum vs selepas:** sebelum pembaikan, konsumer hanya `log.info` (0 baris ditulis
  ke Silver), tiada metrik, dan 4 unit test dengan coverage tidak direkod. Selepas:
  124 event di-replay → 116 diterima ke Silver/Gold + 8 DLQ, metrik dan log berstruktur,
  27 test lulus dengan coverage 55% (`evidence/test_output.txt`).
- **Bottleneck:** freshness p50 ~571s kerana sampel Bronze adalah *snapshot statik* yang
  diambil lebih kurang 9 min sebelum profiling, bukan aliran langsung. Producer sebenar
  polling setiap 15s; dalam mod live freshness dijangka < 60s. Ini perlu diuji semula
  dengan producer berjalan (rujuk alert B).
- **Serving:** p95 ~10 ms — jauh di bawah budget 200 ms; API membaca Parquet terus.
- **Storage:** throughput ~43k rows/s memadai untuk 5k baris BTS/batch harian. Kos utama
  ialah penulisan `version=*` setiap snapshot; retensi 90/180/365 hari perlu dipantau.
- **Resource budget Docker:** Redpanda 768 MB, Postgres 512 MB, API 1 GB, consumer &
  producer 512 MB setiap satu, Prometheus 512 MB, Alertmanager 256 MB, Grafana 512 MB.
  Jumlah nominal ~4.1 GB RAM; sesuai untuk satu mesin demo.

## Trade-off utama
1. Parquet + Postgres (ADR-002): analitik laju vs perlu sinkronisasi dua stor.
2. Redpanda tempatan (ADR-001): replay/offset benar vs operasi broker perlu dipantau.
3. Tracking JSONL (ADR-004): ringan & boleh diaudit vs tiada UI MLflow.
4. Quality gate amaran untuk kod lapangan terbang lama (ADR-003): data sah tidak
   dibuang vs perlu semakan manual pemetaan IATA.
