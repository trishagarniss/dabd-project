# Keamanan, akses dan risiko (F-16)

## Matriks akses
| Peran | Kunci (demo) | Dapat | Tidak dapat |
|---|---|---|---|
| viewer | `demo-viewer-key` | Semua GET query/mart, quality, lineage, experiments, metrics | Inference, perubahan skema/audit |
| operator | `demo-operator-key` | Semua viewer + `POST /api/v1/ml/predict-delay` | Akses `ops.audit_log`, DDL |
| admin | `demo-admin-key` | Semua + DDL / tabel audit | — (tetap tercatat di audit) |

Status kode teruji: 401 untuk kunci tidak ada/salah, 403 untuk viewer pada inference
(`tests/unit/test_api.py`, `logs/audit.jsonl`).

## Secret & jaringan
- Template: `.env.example` (placeholder). `.env` sebenarnya ada di `.gitignore`.
- Kunci API dibaca dari `.env`/env var; tidak ada kunci produksi yang dimasukkan ke repo.
- Docker: broker (19092) dan Postgres (5432) diekspos ke host hanya untuk demo lokal;
  layanan aplikasi berada di network `backend`, Grafana di `frontend`.
- Endpoint `/api/v1/metrics` dan `/api/v1/health` sengaja tanpa auth untuk scrape dan
  healthcheck, **hanya** dapat diakses melalui network internal/host lokal.

## Checklist ancaman
| Risiko | Kontrol | Status |
|---|---|---|
| Kunci terbuka di Git | `.gitignore`, `.env.example` placeholder | Mitigated |
| Viewer menjalankan aksi operator/admin | `ROLE_RANK`, 403, audit | Mitigated |
| Input inference berbahaya | Pydantic validation (422), model version dari registry | Mitigated |
| Eksposur port ke internet | Tidak ada TLS/SSO; demo localhost saja | **Open (demo-only)** |
| Audit dapat diubah | `logs/audit.jsonl` + `ops.audit_log` (admin only) | Mitigated |
| Secret statis demo | Rotasi kunci sebelum deployment non-lokal | Open (demo-only) |

Catatan: konfigurasi ini **tidak** cocok untuk eksposur publik; perlu TLS, secret manager,
dan reverse-proxy sebelum produksi.
