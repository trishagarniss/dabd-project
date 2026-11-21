-- Serving queries (F-10). Grain and business question are stated per query.
-- Tables are created by config/init_db.sql and loaded from data/gold/*.parquet.
-- Run with: psql "$DATABASE_URL" -f config/serving_queries.sql

-- Q01 [one row per active aircraft] Which aircraft are currently tracked?
SELECT icao24, callsign, origin_country, latitude, longitude, altitude_m,
       velocity_kmh, predicted_delay_min, last_updated
FROM gold.active_flights_mart
ORDER BY last_updated DESC
LIMIT 50;

-- Q02 [one row per origin country] Where is airspace density highest?
SELECT origin_country, total_active_flights, avg_altitude_m, avg_velocity_kmh,
       last_aggregated_at
FROM gold.airspace_density_mart
ORDER BY total_active_flights DESC;

-- Q03 [one row per airport] Airport dimension used as conformed dimension.
SELECT icao_code, iata_code, name, country, latitude, longitude
FROM gold.airport_dimension
ORDER BY country, icao_code;

-- Q04 [one row per flight] Arrival delay for a single date (reconciliation A).
SELECT flight_record_id, flight_date, carrier, origin, dest, distance_km,
       dep_delay_min, arr_delay_min
FROM gold.flight_delay_features
WHERE flight_date = DATE '2024-01-01'
ORDER BY flight_record_id;

-- Q05 [one row per carrier/date] Daily delay by carrier.
SELECT carrier, flight_date, COUNT(*) AS flights,
       ROUND(AVG(arr_delay_min)::numeric, 2) AS avg_arr_delay_min,
       MAX(arr_delay_min) AS worst_delay_min
FROM gold.flight_delay_features
GROUP BY carrier, flight_date
ORDER BY flight_date, avg_arr_delay_min DESC;

-- Q06 [one row per origin-destination] Busiest routes and their average delay.
SELECT origin, dest, COUNT(*) AS flights,
       ROUND(AVG(distance_km)::numeric, 1) AS avg_distance_km,
       ROUND(AVG(arr_delay_min)::numeric, 2) AS avg_arr_delay_min
FROM gold.flight_delay_features
GROUP BY origin, dest
ORDER BY flights DESC
LIMIT 25;

-- Q07 [one row per departure hour] Delay profile by hour of day.
SELECT hour_of_day, COUNT(*) AS flights,
       ROUND(AVG(dep_delay_min)::numeric, 2) AS avg_dep_delay_min,
       ROUND(AVG(arr_delay_min)::numeric, 2) AS avg_arr_delay_min
FROM gold.flight_delay_features
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- Q08 [one row per flight] Late arrivals above 15 minutes.
SELECT flight_record_id, origin, dest, dep_delay_min, arr_delay_min
FROM gold.flight_delay_features
WHERE arr_delay_min > 15
ORDER BY arr_delay_min DESC
LIMIT 100;

-- Q09 [one row per prediction] Inference audit with model version and status.
SELECT input_record_id, model_version, predicted_at, predicted_delay_min, score, status
FROM gold.predictions
ORDER BY predicted_at DESC
LIMIT 50;

-- Q10 [one row per date range] Reconciliation totals for two date ranges (F-13).
SELECT
    CASE WHEN flight_date BETWEEN DATE '2024-01-01' AND DATE '2024-01-07'
         THEN 'range_A' ELSE 'range_B' END AS date_range,
    COUNT(*) AS flights,
    ROUND(AVG(arr_delay_min)::numeric, 2) AS avg_arr_delay_min
FROM gold.flight_delay_features
WHERE flight_date BETWEEN DATE '2024-01-01' AND DATE '2024-01-14'
GROUP BY 1
ORDER BY 1;
