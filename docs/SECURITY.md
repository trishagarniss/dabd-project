# Keselamatan, akses dan risiko (F-16)

## Access matrix
| Peranan | Kunci (demo) | Boleh | Tidak boleh |
|---|---|---|---|
| viewer | `demo-viewer-key` | Semua GET query/mart, quality, lineage, experiments, metrics | Inference, perubahan skema/audit |
| operator | `demo-operator-key` | Semua viewer + `POST /api/v1/ml/predict-delay` | Akses `ops.audit_log`, DDL |
| admin | `demo-admin-key` | Semua + DDL / jadual audit | — (tertakluk audit) |

Status kod diuji: 401 untuk kunci tiada/salah, 403 untuk viewer pada inference
(`tests/unit/test_api.py`, `logs/audit.jsonl`).

## Secret & rangkaian
- Template: `.env.example` (placeholder). `.env` sebenar ada dalam `.gitignore`.
- Kunci API dibaca dari `.env`/env var; tiada kunci produksi dimasukkan ke repo.
- Docker: broker (19092) dan Postgres (5432) didedahkan ke host untuk demo tempatan
  sahaja; servis aplikasi berada di network `backend`, Grafana di `frontend`.
- Endpoint `/api/v1/metrics` dan `/api/v1/health` sengaja tanpa auth untuk scrape dan
  healthcheck, **hanya** boleh diakses melalui network dalaman/host tempatan.

## Threat checklist
| Risiko | Kawalan | Status |
|---|---|---|
| Kunci terbuka di Git | `.gitignore`, `.env.example` placeholder | Mitigated |
| Viewer menjalankan aksi operator/admin | `ROLE_RANK`, 403, audit | Mitigated |
| Input inference berniat jahat | Pydantic validation (422), model version dari registry | Mitigated |
| Pendedahan port ke internet | Tiada TLS/SSO; demo localhost sahaja | **Open (demo-only)** |
| Audit boleh diubah | `logs/audit.jsonl` + `ops.audit_log` (admin only) | Mitigated |
| Secret statik demo | Putar kunci sebelum sebarang deployment bukan lokal | Open (demo-only) |

Nota: konfigurasi ini **tidak** sesuai untuk pendedahan awam; perlu TLS, secret manager
dan reverse-proxy sebelum production.
