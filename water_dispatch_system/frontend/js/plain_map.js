var PlainMap = (function () {
    var map = null;
    var markers = { sensors: [], gates: [], pumps: [] };
    var currentCanal = 1;
    var onSensorClick = null;
    var onGateClick = null;
    var onPumpClick = null;

    function init(opts) {
        onSensorClick = opts.onSensorClick || function () {};
        onGateClick = opts.onGateClick || function () {};
        onPumpClick = opts.onPumpClick || function () {};

        map = L.map("map", {
            center: [34.5, 114.5],
            zoom: 7,
            zoomControl: true,
        });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap",
            maxZoom: 18,
        }).addTo(map);
    }

    function setCanal(canalId) {
        currentCanal = canalId;
    }

    function getCanal() {
        return currentCanal;
    }

    function loadCanals(data) {
        if (!data) return;
        map.eachLayer(function (layer) {
            if (layer instanceof L.GeoJSON) map.removeLayer(layer);
        });
        data.forEach(function (canal) {
            if (canal.geom_geojson) {
                L.geoJSON(canal.geom_geojson, {
                    style: {
                        color: canal.id === 1 ? "#2196f3" : canal.id === 2 ? "#00bcd4" : "#4caf50",
                        weight: 4,
                        opacity: 0.8,
                    },
                }).addTo(map);
            }
        });
    }

    function loadSensors(data) {
        if (!data) return;
        markers.sensors.forEach(function (m) { map.removeLayer(m); });
        markers.sensors = [];
        var filtered = data.filter(function (s) { return s.canal_id === currentCanal; });
        filtered.forEach(function (sensor) {
            if (sensor.lng == null || sensor.lat == null) return;
            var color = sensor.status_color || "green";
            var icon = L.divIcon({
                className: "",
                html: '<div class="sensor-marker ' + color + '" title="' + sensor.name + '">' + (sensor.sensor_type === "water_level" ? "W" : "F") + '</div>',
                iconSize: [24, 24],
                iconAnchor: [12, 12],
            });
            var marker = L.marker([sensor.lat, sensor.lng], { icon: icon });
            marker.on("click", function () { onSensorClick(sensor); });
            marker.addTo(map);
            markers.sensors.push(marker);
        });
    }

    function loadGates(data) {
        if (!data) return;
        markers.gates.forEach(function (m) { map.removeLayer(m); });
        markers.gates = [];
        var filtered = data.filter(function (g) { return g.canal_id === currentCanal; });
        filtered.forEach(function (gate) {
            if (gate.lng == null || gate.lat == null) return;
            var color = "green";
            if (gate.latest_status) {
                var opening = parseFloat(gate.latest_status.opening);
                if (opening < 30 || opening > 95) color = "yellow";
                if (opening < 10 || opening > 100) color = "red";
            }
            var icon = L.divIcon({
                className: "",
                html: '<div class="gate-marker ' + color + '" title="' + gate.name + '">闸</div>',
                iconSize: [26, 26],
                iconAnchor: [13, 13],
            });
            var marker = L.marker([gate.lat, gate.lng], { icon: icon });
            marker.on("click", function () { onGateClick(gate); });
            marker.addTo(map);
            markers.gates.push(marker);
        });
    }

    function loadPumpStations(data) {
        if (!data) return;
        markers.pumps.forEach(function (m) { map.removeLayer(m); });
        markers.pumps = [];
        var filtered = data.filter(function (p) { return p.canal_id === currentCanal; });
        filtered.forEach(function (pump) {
            if (pump.lng == null || pump.lat == null) return;
            var color = "green";
            if (pump.latest_status) {
                var load = parseFloat(pump.latest_status.running_count) / pump.pump_count;
                if (load > 0.9) color = "yellow";
                if (load >= 1.0) color = "red";
            }
            var icon = L.divIcon({
                className: "",
                html: '<div class="pump-marker ' + color + '" title="' + pump.name + '">泵</div>',
                iconSize: [30, 30],
                iconAnchor: [15, 15],
            });
            var marker = L.marker([pump.lat, pump.lng], { icon: icon });
            marker.on("click", function () { onPumpClick(pump); });
            marker.addTo(map);
            markers.pumps.push(marker);
        });
    }

    function invalidateSize() {
        if (map) map.invalidateSize();
    }

    return {
        init: init,
        setCanal: setCanal,
        getCanal: getCanal,
        loadCanals: loadCanals,
        loadSensors: loadSensors,
        loadGates: loadGates,
        loadPumpStations: loadPumpStations,
        invalidateSize: invalidateSize,
    };
})();
