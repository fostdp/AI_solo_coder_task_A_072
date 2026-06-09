CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP TABLE IF EXISTS dispatch_commands CASCADE;
DROP TABLE IF EXISTS alarms CASCADE;
DROP TABLE IF EXISTS sensor_data CASCADE;
DROP TABLE IF EXISTS gate_status CASCADE;
DROP TABLE IF EXISTS pump_status CASCADE;
DROP TABLE IF EXISTS sensors CASCADE;
DROP TABLE IF EXISTS gates CASCADE;
DROP TABLE IF EXISTS pump_stations CASCADE;
DROP TABLE IF EXISTS canal_sections CASCADE;
DROP TABLE IF EXISTS canals CASCADE;

CREATE TABLE canals (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) NOT NULL UNIQUE,
    length_km NUMERIC(10,2) NOT NULL,
    design_flow NUMERIC(10,2) NOT NULL,
    geom LINESTRING NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE canal_sections (
    id SERIAL PRIMARY KEY,
    canal_id INTEGER REFERENCES canals(id),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) NOT NULL,
    start_km NUMERIC(10,2) NOT NULL,
    end_km NUMERIC(10,2) NOT NULL,
    design_water_level NUMERIC(8,2) NOT NULL,
    design_flow NUMERIC(10,2) NOT NULL,
    storage_capacity NUMERIC(12,2) NOT NULL,
    geom LINESTRING NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE pump_stations (
    id SERIAL PRIMARY KEY,
    canal_id INTEGER REFERENCES canals(id),
    section_id INTEGER REFERENCES canal_sections(id),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) NOT NULL,
    pump_count INTEGER NOT NULL DEFAULT 4,
    single_pump_power NUMERIC(8,2) NOT NULL,
    design_flow NUMERIC(10,2) NOT NULL,
    head NUMERIC(8,2) NOT NULL,
    geom POINT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE gates (
    id SERIAL PRIMARY KEY,
    canal_id INTEGER REFERENCES canals(id),
    section_id INTEGER REFERENCES canal_sections(id),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) NOT NULL,
    gate_type VARCHAR(20) NOT NULL DEFAULT 'regulating',
    max_opening NUMERIC(5,2) NOT NULL DEFAULT 100.00,
    design_flow NUMERIC(10,2) NOT NULL,
    geom POINT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sensors (
    id SERIAL PRIMARY KEY,
    canal_id INTEGER REFERENCES canals(id),
    section_id INTEGER REFERENCES canal_sections(id),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) NOT NULL,
    sensor_type VARCHAR(20) NOT NULL,
    design_value NUMERIC(10,2) NOT NULL,
    warning_upper NUMERIC(10,2) NOT NULL,
    warning_lower NUMERIC(10,2) NOT NULL,
    danger_upper NUMERIC(10,2) NOT NULL,
    danger_lower NUMERIC(10,2) NOT NULL,
    geom POINT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sensor_data (
    id BIGSERIAL PRIMARY KEY,
    sensor_id INTEGER REFERENCES sensors(id),
    value NUMERIC(10,4) NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE gate_status (
    id BIGSERIAL PRIMARY KEY,
    gate_id INTEGER REFERENCES gates(id),
    opening NUMERIC(5,2) NOT NULL,
    flow NUMERIC(10,2),
    recorded_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE pump_status (
    id BIGSERIAL PRIMARY KEY,
    pump_station_id INTEGER REFERENCES pump_stations(id),
    running_count INTEGER NOT NULL DEFAULT 0,
    total_power NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_flow NUMERIC(10,2) NOT NULL DEFAULT 0,
    recorded_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE alarms (
    id BIGSERIAL PRIMARY KEY,
    alarm_type VARCHAR(20) NOT NULL,
    level INTEGER NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    source_id INTEGER NOT NULL,
    source_name VARCHAR(100),
    message TEXT NOT NULL,
    value NUMERIC(10,4),
    threshold NUMERIC(10,4),
    duration_minutes INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE TABLE dispatch_commands (
    id BIGSERIAL PRIMARY KEY,
    plan_id VARCHAR(50),
    target_type VARCHAR(20) NOT NULL,
    target_id INTEGER NOT NULL,
    target_name VARCHAR(100),
    command_type VARCHAR(50) NOT NULL,
    command_value NUMERIC(10,2),
    mqtt_topic VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    sent_at TIMESTAMP,
    acked_at TIMESTAMP
);

CREATE INDEX idx_sensor_data_sensor_time ON sensor_data(sensor_id, recorded_at DESC);
CREATE INDEX idx_gate_status_gate_time ON gate_status(gate_id, recorded_at DESC);
CREATE INDEX idx_pump_status_station_time ON pump_status(pump_station_id, recorded_at DESC);
CREATE INDEX idx_alarms_status ON alarms(status, created_at DESC);
CREATE INDEX idx_dispatch_commands_status ON dispatch_commands(status, created_at DESC);
CREATE INDEX idx_sensors_geom ON sensors USING GIST(geom);
CREATE INDEX idx_gates_geom ON gates USING GIST(geom);
CREATE INDEX idx_pump_stations_geom ON pump_stations USING GIST(geom);

INSERT INTO canals (name, code, length_km, design_flow, geom) VALUES
('中线总干渠', 'ZX', 1432.00, 350.00,
 ST_GeomFromText('LINESTRING(111.47 32.68, 112.10 33.20, 112.90 33.80, 113.65 34.35, 114.30 34.75, 114.95 35.20, 115.50 35.70, 116.00 36.20, 116.30 36.70, 116.40 37.20, 116.50 37.70, 116.55 38.10, 116.58 38.50, 116.60 39.00, 116.50 39.50, 116.40 39.90)', 4326)),
('东线干渠', 'DX', 1156.00, 300.00,
 ST_GeomFromText('LINESTRING(118.30 32.30, 118.50 33.00, 118.60 33.60, 118.70 34.20, 118.80 34.80, 118.90 35.40, 119.00 36.00, 119.10 36.60, 119.20 37.20, 119.30 37.70)', 4326)),
('引江济汉渠', 'YJJH', 67.00, 200.00,
 ST_GeomFromText('LINESTRING(112.15 30.30, 112.30 30.45, 112.50 30.55, 112.70 30.60, 112.85 30.50)', 4326));

INSERT INTO canal_sections (canal_id, name, code, start_km, end_km, design_water_level, design_flow, storage_capacity, geom) VALUES
(1, '陶岔-沙河渡槽', 'ZX-S1', 0, 120, 147.38, 350, 120000, ST_GeomFromText('LINESTRING(111.47 32.68, 112.10 33.20)', 4326)),
(1, '沙河渡槽-郑州', 'ZX-S2', 120, 300, 132.00, 320, 180000, ST_GeomFromText('LINESTRING(112.10 33.20, 113.65 34.35)', 4326)),
(1, '郑州-新乡', 'ZX-S3', 300, 450, 108.00, 280, 150000, ST_GeomFromText('LINESTRING(113.65 34.35, 114.30 34.75, 114.95 35.20)', 4326)),
(1, '新乡-安阳', 'ZX-S4', 450, 620, 92.00, 250, 170000, ST_GeomFromText('LINESTRING(114.95 35.20, 115.50 35.70, 116.00 36.20)', 4326)),
(1, '安阳-邯郸', 'ZX-S5', 620, 780, 85.00, 230, 160000, ST_GeomFromText('LINESTRING(116.00 36.20, 116.30 36.70, 116.40 37.20)', 4326)),
(1, '邯郸-石家庄', 'ZX-S6', 780, 960, 76.00, 200, 180000, ST_GeomFromText('LINESTRING(116.40 37.20, 116.50 37.70, 116.55 38.10)', 4326)),
(1, '石家庄-保定', 'ZX-S7', 960, 1100, 68.00, 170, 140000, ST_GeomFromText('LINESTRING(116.55 38.10, 116.58 38.50, 116.60 39.00)', 4326)),
(1, '保定-北京', 'ZX-S8', 1100, 1432, 58.00, 135, 160000, ST_GeomFromText('LINESTRING(116.60 39.00, 116.50 39.50, 116.40 39.90)', 4326)),
(2, '扬州-淮安', 'DX-S1', 0, 150, 6.00, 300, 90000, ST_GeomFromText('LINESTRING(118.30 32.30, 118.60 33.60)', 4326)),
(2, '淮安-徐州', 'DX-S2', 150, 350, 12.00, 260, 120000, ST_GeomFromText('LINESTRING(118.60 33.60, 118.80 34.80)', 4326)),
(2, '徐州-济宁', 'DX-S3', 350, 550, 18.00, 220, 110000, ST_GeomFromText('LINESTRING(118.80 34.80, 119.00 36.00)', 4326)),
(2, '济宁-济南', 'DX-S4', 550, 750, 25.00, 180, 100000, ST_GeomFromText('LINESTRING(119.00 36.00, 119.20 37.20)', 4326)),
(2, '济南-天津', 'DX-S5', 750, 1156, 30.00, 140, 130000, ST_GeomFromText('LINESTRING(119.20 37.20, 119.30 37.70)', 4326)),
(3, '龙洲垸-拾桥河', 'YJJH-S1', 0, 35, 28.00, 200, 35000, ST_GeomFromText('LINESTRING(112.15 30.30, 112.50 30.55)', 4326)),
(3, '拾桥河-高石碑', 'YJJH-S2', 35, 67, 25.00, 180, 33000, ST_GeomFromText('LINESTRING(112.50 30.55, 112.85 30.50)', 4326));

INSERT INTO pump_stations (canal_id, section_id, name, code, pump_count, single_pump_power, design_flow, head, geom) VALUES
(1, 1, '陶岔泵站', 'PS-ZX-01', 6, 2800.00, 350.00, 8.50, ST_GeomFromText('POINT(111.50 32.70)', 4326)),
(1, 2, '沙河泵站', 'PS-ZX-02', 4, 2200.00, 320.00, 12.00, ST_GeomFromText('POINT(112.50 33.50)', 4326)),
(1, 3, '郑州泵站', 'PS-ZX-03', 4, 2500.00, 280.00, 10.50, ST_GeomFromText('POINT(113.65 34.35)', 4326)),
(1, 4, '新乡泵站', 'PS-ZX-04', 4, 2000.00, 250.00, 9.80, ST_GeomFromText('POINT(114.95 35.20)', 4326)),
(1, 5, '安阳泵站', 'PS-ZX-05', 4, 1800.00, 230.00, 8.20, ST_GeomFromText('POINT(116.00 36.20)', 4326)),
(1, 6, '邯郸泵站', 'PS-ZX-06', 4, 1600.00, 200.00, 7.50, ST_GeomFromText('POINT(116.40 37.20)', 4326)),
(1, 7, '石家庄泵站', 'PS-ZX-07', 3, 1500.00, 170.00, 6.80, ST_GeomFromText('POINT(116.55 38.10)', 4326)),
(1, 8, '保定泵站', 'PS-ZX-08', 3, 1400.00, 135.00, 5.50, ST_GeomFromText('POINT(116.60 39.00)', 4326)),
(2, 9, '扬州泵站', 'PS-DX-01', 6, 2600.00, 300.00, 7.00, ST_GeomFromText('POINT(118.30 32.30)', 4326)),
(2, 10, '淮安泵站', 'PS-DX-02', 4, 2200.00, 260.00, 9.50, ST_GeomFromText('POINT(118.60 33.60)', 4326)),
(2, 11, '徐州泵站', 'PS-DX-03', 4, 2000.00, 220.00, 8.80, ST_GeomFromText('POINT(118.80 34.80)', 4326)),
(2, 12, '济宁泵站', 'PS-DX-04', 3, 1800.00, 180.00, 7.50, ST_GeomFromText('POINT(119.00 36.00)', 4326)),
(2, 13, '济南泵站', 'PS-DX-05', 3, 1600.00, 140.00, 6.20, ST_GeomFromText('POINT(119.20 37.20)', 4326)),
(3, 14, '龙洲垸泵站', 'PS-YJJH-01', 4, 1500.00, 200.00, 5.80, ST_GeomFromText('POINT(112.15 30.30)', 4326)),
(3, 15, '拾桥河泵站', 'PS-YJJH-02', 4, 1400.00, 180.00, 4.50, ST_GeomFromText('POINT(112.50 30.55)', 4326)),
(1, 2, '颍河泵站', 'PS-ZX-09', 3, 1900.00, 300.00, 11.00, ST_GeomFromText('POINT(112.80 33.80)', 4326)),
(1, 4, '鹤壁泵站', 'PS-ZX-10', 3, 1700.00, 240.00, 9.00, ST_GeomFromText('POINT(115.50 35.70)', 4326)),
(1, 6, '邢台泵站', 'PS-ZX-11', 3, 1500.00, 190.00, 7.00, ST_GeomFromText('POINT(116.30 36.70)', 4326)),
(2, 10, '金湖泵站', 'PS-DX-06', 3, 2100.00, 250.00, 8.50, ST_GeomFromText('POINT(118.50 33.00)', 4326)),
(2, 12, '梁山泵站', 'PS-DX-07', 3, 1700.00, 170.00, 7.00, ST_GeomFromText('POINT(118.90 35.40)', 4326));

INSERT INTO gates (canal_id, section_id, name, code, gate_type, max_opening, design_flow, geom)
SELECT
    (ROW_NUMBER() OVER ())::int % 3 + 1 as canal_id_sim,
    s.id as section_id,
    '闸门-' || LPAD((ROW_NUMBER() OVER ())::text, 3, '0') as name,
    'GT-' || LPAD((ROW_NUMBER() OVER ())::text, 3, '0') as code,
    CASE WHEN (ROW_NUMBER() OVER ()) % 3 = 0 THEN 'emergency'
         WHEN (ROW_NUMBER() OVER ()) % 3 = 1 THEN 'regulating'
         ELSE 'check' END as gate_type,
    100.00 as max_opening,
    CASE WHEN (ROW_NUMBER() OVER ()) % 3 + 1 = 1 THEN 350.00
         WHEN (ROW_NUMBER() OVER ()) % 3 + 1 = 2 THEN 260.00
         ELSE 180.00 END as design_flow,
    ST_LineInterpolatePoint(
        (SELECT geom FROM canals WHERE id = (ROW_NUMBER() OVER ())::int % 3 + 1),
        (ROW_NUMBER() OVER ())::float / 55.0
    ) as geom
FROM generate_series(1, 50) as t(n)
CROSS JOIN (SELECT id FROM canal_sections LIMIT 1) s;

UPDATE gates SET section_id = (
    SELECT cs.id FROM canal_sections cs
    WHERE cs.canal_id = gates.canal_id
    ORDER BY ST_Distance(cs.geom, gates.geom) LIMIT 1
);

DO $$
DECLARE
    canal_geom GEOMETRY;
    frac FLOAT;
    canal_rec RECORD;
    sec_rec RECORD;
    sensor_idx INTEGER;
    sensor_lon FLOAT;
    sensor_lat FLOAT;
    sensor_design FLOAT;
    sensor_wupper FLOAT;
    sensor_wlower FLOAT;
    sensor_dupper FLOAT;
    sensor_dlower FLOAT;
    sensor_type TEXT;
BEGIN
    sensor_idx := 0;
    FOR canal_rec IN SELECT id, geom, design_flow FROM canals LOOP
        FOR sec_rec IN SELECT id, design_water_level, design_flow, start_km, end_km FROM canal_sections WHERE canal_id = canal_rec.id LOOP
            FOR frac IN SELECT generate_series(1, 4) / 5.0 LOOP
                sensor_idx := sensor_idx + 1;

                sensor_lon := ST_X(ST_LineInterpolatePoint(canal_rec.geom, frac * 0.8 + 0.1));
                sensor_lat := ST_Y(ST_LineInterpolatePoint(canal_rec.geom, frac * 0.8 + 0.1));

                sensor_design := sec_rec.design_water_level + (random() * 2 - 1);
                sensor_wupper := sensor_design * 1.10;
                sensor_wlower := sensor_design * 0.90;
                sensor_dupper := sensor_design * 1.20;
                sensor_dlower := sensor_design * 0.80;

                INSERT INTO sensors (canal_id, section_id, name, code, sensor_type, design_value, warning_upper, warning_lower, danger_upper, danger_lower, geom)
                VALUES (
                    canal_rec.id,
                    sec_rec.id,
                    '水位计-' || LPAD(sensor_idx::text, 3, '0'),
                    'WL-' || LPAD(sensor_idx::text, 3, '0'),
                    'water_level',
                    ROUND(sensor_design::numeric, 2),
                    ROUND(sensor_wupper::numeric, 2),
                    ROUND(sensor_wlower::numeric, 2),
                    ROUND(sensor_dupper::numeric, 2),
                    ROUND(sensor_dlower::numeric, 2),
                    ST_SetSRID(ST_MakePoint(sensor_lon, sensor_lat), 4326)
                );

                sensor_idx := sensor_idx + 1;

                INSERT INTO sensors (canal_id, section_id, name, code, sensor_type, design_value, warning_upper, warning_lower, danger_upper, danger_lower, geom)
                VALUES (
                    canal_rec.id,
                    sec_rec.id,
                    '流量计-' || LPAD(sensor_idx::text, 3, '0'),
                    'FL-' || LPAD(sensor_idx::text, 3, '0'),
                    'flow',
                    ROUND(sec_rec.design_flow::numeric, 2),
                    ROUND((sec_rec.design_flow * 1.10)::numeric, 2),
                    ROUND((sec_rec.design_flow * 0.90)::numeric, 2),
                    ROUND((sec_rec.design_flow * 1.20)::numeric, 2),
                    ROUND((sec_rec.design_flow * 0.80)::numeric, 2),
                    ST_SetSRID(ST_MakePoint(sensor_lon + 0.005, sensor_lat + 0.003), 4326)
                );
            END LOOP;
        END LOOP;
    END LOOP;
END $$;
