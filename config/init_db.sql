-- Inisialisasi Database Schema untuk Flight Data Platform (Medallion: Silver & Gold)

-- Schema Silver: Data cleaned & validated
CREATE SCHEMA IF NOT EXISTS silver;

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
    ingest_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    event_time TIMESTAMP WITH TIME ZONE
);

-- Schema Gold: Marts siap saji (F-10)
CREATE SCHEMA IF NOT EXISTS gold;

-- Mart 1: State terkini penerbangan aktif (dengan metadata & enrichment)
CREATE TABLE IF NOT EXISTS gold.active_flights_mart (
    icao24 VARCHAR(10) PRIMARY KEY,
    callsign VARCHAR(16),
    origin_country VARCHAR(64),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude_m DOUBLE PRECISION,
    velocity_kmh DOUBLE PRECISION,
    vertical_rate_ms DOUBLE PRECISION,
    flight_phase VARCHAR(32), -- climbing, cruising, descending, on_ground
    predicted_delay_min DOUBLE PRECISION,
    last_updated TIMESTAMP WITH TIME ZONE
);

-- Mart 2: Agregasi per negara / zona penerbangan
CREATE TABLE IF NOT EXISTS gold.airspace_density_mart (
    origin_country VARCHAR(64) PRIMARY KEY,
    total_active_flights INT,
    avg_altitude_m DOUBLE PRECISION,
    avg_velocity_kmh DOUBLE PRECISION,
    last_aggregated_at TIMESTAMP WITH TIME ZONE
);
