-- SkyPulse Data Platform database bootstrap (F-01, F-07, F-16)
-- Local/on-premise PostgreSQL. ACID tables are the transactional counterpart
-- to versioned Parquet snapshots; see docs/adr/ADR-002.md for the trade-off.

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS bronze.ingestion_batch (
    batch_id VARCHAR(64) PRIMARY KEY,
    source TEXT NOT NULL,
    source_checksum VARCHAR(128),
    row_count INTEGER,
    ingest_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(16) NOT NULL DEFAULT 'SUCCESS'
);

CREATE TABLE IF NOT EXISTS silver.flight_states (
    event_id VARCHAR(64) PRIMARY KEY,
    icao24 VARCHAR(10) NOT NULL,
    callsign VARCHAR(16),
    origin_country VARCHAR(64),
    time_position BIGINT,
    last_contact BIGINT,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    baro_altitude DOUBLE PRECISION,
    on_ground BOOLEAN,
    velocity DOUBLE PRECISION,
    true_track DOUBLE PRECISION,
    vertical_rate DOUBLE PRECISION,
    geo_altitude DOUBLE PRECISION,
    event_time TIMESTAMPTZ,
    ingest_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_silver_flight_time ON silver.flight_states(event_time DESC);

CREATE TABLE IF NOT EXISTS silver.airports_clean (
    icao_code VARCHAR(8) PRIMARY KEY,
    iata_code VARCHAR(8),
    name TEXT,
    country VARCHAR(8),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    elevation_ft DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver.dlq_events (
    event_id VARCHAR(64),
    dataset VARCHAR(64),
    reasons TEXT,
    raw_payload JSONB,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gold.active_flights_mart (
    icao24 VARCHAR(10) PRIMARY KEY,
    callsign VARCHAR(16),
    origin_country VARCHAR(64),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude_m DOUBLE PRECISION,
    velocity_kmh DOUBLE PRECISION,
    vertical_rate_ms DOUBLE PRECISION,
    flight_phase VARCHAR(32),
    predicted_delay_min DOUBLE PRECISION,
    last_updated TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS gold.airspace_density_mart (
    origin_country VARCHAR(64) PRIMARY KEY,
    total_active_flights INT,
    avg_altitude_m DOUBLE PRECISION,
    avg_velocity_kmh DOUBLE PRECISION,
    last_aggregated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS gold.flight_delay_features (
    flight_record_id VARCHAR(128) PRIMARY KEY,
    flight_date DATE,
    carrier VARCHAR(8),
    origin VARCHAR(8),
    dest VARCHAR(8),
    distance_km DOUBLE PRECISION,
    hour_of_day INT,
    day_of_week INT,
    month INT,
    dep_delay_min DOUBLE PRECISION,
    taxi_out_min DOUBLE PRECISION,
    crs_elapsed_min DOUBLE PRECISION,
    arr_delay_min DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gold.predictions (
    input_record_id VARCHAR(128) PRIMARY KEY,
    model_version VARCHAR(32) NOT NULL,
    predicted_at TIMESTAMPTZ NOT NULL,
    predicted_delay_min DOUBLE PRECISION,
    score DOUBLE PRECISION,
    status VARCHAR(16)
);

CREATE TABLE IF NOT EXISTS ops.audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor VARCHAR(32),
    role VARCHAR(16),
    endpoint TEXT,
    status_code INT,
    client INET
);

CREATE TABLE IF NOT EXISTS ops.job_run (
    run_id VARCHAR(64) PRIMARY KEY,
    job VARCHAR(64),
    status VARCHAR(16),
    rows BIGINT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ops.lineage (
    run_id VARCHAR(64) PRIMARY KEY,
    job VARCHAR(64),
    inputs JSONB,
    outputs JSONB,
    consumers JSONB,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Role separation (F-16): viewer is read-only, operator can write predictions,
-- admin owns schema and audit access.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'fdp_viewer') THEN
        CREATE ROLE fdp_viewer LOGIN PASSWORD 'viewer_local_only';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'fdp_operator') THEN
        CREATE ROLE fdp_operator LOGIN PASSWORD 'operator_local_only';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'fdp_admin') THEN
        CREATE ROLE fdp_admin LOGIN PASSWORD 'admin_local_only';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA silver, gold, bronze, ops TO fdp_viewer, fdp_operator, fdp_admin;
GRANT SELECT ON ALL TABLES IN SCHEMA silver, gold, bronze TO fdp_viewer, fdp_operator, fdp_admin;
GRANT SELECT, INSERT, UPDATE ON gold.predictions, silver.flight_states, silver.dlq_events TO fdp_operator, fdp_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA silver, gold, bronze, ops TO fdp_admin;
GRANT SELECT ON ops.audit_log TO fdp_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT TO fdp_viewer;
