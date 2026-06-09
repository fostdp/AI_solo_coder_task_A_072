ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '768MB';
ALTER SYSTEM SET work_mem = '16MB';
ALTER SYSTEM SET maintenance_work_mem = '128MB';
ALTER SYSTEM SET autovacuum = on;
ALTER SYSTEM SET autovacuum_max_workers = 4;
ALTER SYSTEM SET autovacuum_naptime = '30s';
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.05;
ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.02;
ALTER SYSTEM SET autovacuum_vacuum_cost_limit = 2000;

SELECT set_config('work_mem', '64MB', false);

ALTER TABLE sensor_data SET (autovacuum_vacuum_scale_factor = 0.01);
ALTER TABLE sensor_data SET (autovacuum_analyze_scale_factor = 0.005);
ALTER TABLE sensor_data SET (autovacuum_vacuum_cost_delay = 10);
ALTER TABLE gate_status SET (autovacuum_vacuum_scale_factor = 0.01);
ALTER TABLE gate_status SET (autovacuum_analyze_scale_factor = 0.005);
ALTER TABLE pump_status SET (autovacuum_vacuum_scale_factor = 0.01);
ALTER TABLE pump_status SET (autovacuum_analyze_scale_factor = 0.005);
ALTER TABLE alarms SET (autovacuum_vacuum_scale_factor = 0.02);
ALTER TABLE dispatch_commands SET (autovacuum_vacuum_scale_factor = 0.02);

CREATE INDEX IF NOT EXISTS idx_sensor_data_sensor_id_time ON sensor_data (sensor_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_sensor_data_recorded_at ON sensor_data (recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_gate_status_gate_id_time ON gate_status (gate_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_pump_status_station_id_time ON pump_status (pump_station_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_dispatch_commands_status ON dispatch_commands (status);
CREATE INDEX IF NOT EXISTS idx_dispatch_commands_plan_id ON dispatch_commands (plan_id);
CREATE INDEX IF NOT EXISTS idx_alarms_status ON alarms (status);
CREATE INDEX IF NOT EXISTS idx_alarms_level ON alarms (level);

CREATE INDEX IF NOT EXISTS idx_canals_geom ON canals USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_canal_sections_geom ON canal_sections USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sensors_geom ON sensors USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_gates_geom ON gates USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_pump_stations_geom ON pump_stations USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_sensors_canal_id ON sensors (canal_id);
CREATE INDEX IF NOT EXISTS idx_sensors_section_id ON sensors (section_id);
CREATE INDEX IF NOT EXISTS idx_sensors_code ON sensors (code);
CREATE INDEX IF NOT EXISTS idx_gates_canal_id ON gates (canal_id);
CREATE INDEX IF NOT EXISTS idx_gates_section_id ON gates (section_id);
CREATE INDEX IF NOT EXISTS idx_pump_stations_canal_id ON pump_stations (canal_id);
CREATE INDEX IF NOT EXISTS idx_pump_stations_section_id ON pump_stations (section_id);

VACUUM ANALYZE canals;
VACUUM ANALYZE canal_sections;
VACUUM ANALYZE sensors;
VACUUM ANALYZE gates;
VACUUM ANALYZE pump_stations;
