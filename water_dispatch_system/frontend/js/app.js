const API_BASE = "/api";
let map = null;
let markers = { sensors: [], gates: [], pumps: [] };
let ws = null;
let currentCanal = 1;
let selectedDevice = null;
let profileData = null;
let profileSensorsCache = null;
let profileCacheCanal = -1;
let profileRenderPending = false;
let trendRenderPending = false;
let cachedTrendData = null;
let cachedTrendSensor = null;

function init() {
    initMap();
    initWebSocket();
    initEventListeners();
    updateDateTime();
    setInterval(updateDateTime, 1000);
    loadInitialData();
    setInterval(refreshData, 30000);
    drawProfile();
    drawTrend();
}

function initMap() {
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

function initWebSocket() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws`);
    ws.onmessage = function (event) {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "alarm") {
                loadAlarms();
                updateAlarmIndicator();
            } else if (msg.type === "sensor_data") {
                refreshData();
            }
        } catch (e) {}
    };
    ws.onclose = function () {
        setTimeout(initWebSocket, 5000);
    };
}

function initEventListeners() {
    document.getElementById("canal-select").addEventListener("change", function () {
        currentCanal = parseInt(this.value);
        loadCanalData();
    });

    document.getElementById("alarm-filter").addEventListener("change", function () {
        loadAlarms();
    });

    document.getElementById("popup-close").addEventListener("click", closePopup);
    document.getElementById("popup-overlay").addEventListener("click", function (e) {
        if (e.target === this) closePopup();
    });

    document.getElementById("dispatch-fab").addEventListener("click", function () {
        const panel = document.getElementById("dispatch-panel");
        panel.style.display = panel.style.display === "none" ? "block" : "none";
    });

    document.getElementById("dispatch-close").addEventListener("click", function () {
        document.getElementById("dispatch-panel").style.display = "none";
    });

    document.getElementById("dispatch-execute").addEventListener("click", executeDispatch);

    document.getElementById("alarm-indicator").addEventListener("click", function () {
        document.querySelector(".alarm-section").scrollIntoView({ behavior: "smooth" });
    });
}

async function loadInitialData() {
    await Promise.all([
        loadCanalData(),
        loadKPIs(),
        loadAlarms(),
        loadDispatchCanalOptions(),
    ]);
}

async function refreshData() {
    await Promise.all([loadKPIs(), loadAlarms(), loadCanalData()]);
}

async function loadCanalData() {
    await Promise.all([
        loadCanals(),
        loadSensors(),
        loadGates(),
        loadPumpStations(),
    ]);
    drawProfile();
}

async function apiGet(path) {
    try {
        const resp = await fetch(`${API_BASE}${path}`);
        if (resp.ok) return await resp.json();
    } catch (e) {}
    return null;
}

async function apiPost(path, body) {
    try {
        const resp = await fetch(`${API_BASE}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (resp.ok) return await resp.json();
    } catch (e) {}
    return null;
}

async function loadCanals() {
    const data = await apiGet("/monitoring/canals");
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

async function loadSensors() {
    const data = await apiGet("/monitoring/sensors");
    if (!data) return;
    markers.sensors.forEach(function (m) { map.removeLayer(m); });
    markers.sensors = [];
    const filtered = data.filter(function (s) { return s.canal_id === currentCanal; });

    const profileKmMap = {
        1: { 0: 0, 120: 120, 300: 300, 450: 450, 620: 620, 780: 780, 960: 960, 1100: 1100, 1432: 1432 },
        2: { 0: 0, 150: 150, 350: 350, 550: 550, 750: 750, 1156: 1156 },
        3: { 0: 0, 35: 35, 67: 67 },
    };

    profileSensorsCache = filtered.map(function (s) {
        const sectionKm = profileKmMap[currentCanal] || {};
        let km = 0;
        const keys = Object.keys(sectionKm).map(Number).sort(function (a, b) { return a - b; });
        for (let i = 0; i < keys.length; i++) {
            km = keys[i] + (i + 1) * (keys[i + 1] - keys[i]) / (keys.length + 1);
            if (km > 0) break;
        }
        return {
            km: km,
            wl: parseFloat(s.latest_value || s.design_value),
            sensor_type: s.sensor_type,
            status_color: s.status_color || "green",
            name: s.name,
        };
    });
    profileCacheCanal = currentCanal;

    filtered.forEach(function (sensor) {
        if (sensor.lng == null || sensor.lat == null) return;
        const color = sensor.status_color || "green";
        const icon = L.divIcon({
            className: "",
            html: `<div class="sensor-marker ${color}" title="${sensor.name}">${sensor.sensor_type === "water_level" ? "W" : "F"}</div>`,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
        });
        const marker = L.marker([sensor.lat, sensor.lng], { icon: icon });
        marker.on("click", function () {
            showSensorPopup(sensor);
        });
        marker.addTo(map);
        markers.sensors.push(marker);
    });
}

async function loadGates() {
    const data = await apiGet("/monitoring/gates");
    if (!data) return;
    markers.gates.forEach(function (m) { map.removeLayer(m); });
    markers.gates = [];
    const filtered = data.filter(function (g) { return g.canal_id === currentCanal; });
    filtered.forEach(function (gate) {
        if (gate.lng == null || gate.lat == null) return;
        let color = "green";
        if (gate.latest_status) {
            const opening = parseFloat(gate.latest_status.opening);
            if (opening < 30 || opening > 95) color = "yellow";
            if (opening < 10 || opening > 100) color = "red";
        }
        const icon = L.divIcon({
            className: "",
            html: `<div class="gate-marker ${color}" title="${gate.name}">闸</div>`,
            iconSize: [26, 26],
            iconAnchor: [13, 13],
        });
        const marker = L.marker([gate.lat, gate.lng], { icon: icon });
        marker.on("click", function () {
            showGatePopup(gate);
        });
        marker.addTo(map);
        markers.gates.push(marker);
    });
}

async function loadPumpStations() {
    const data = await apiGet("/monitoring/pump-stations");
    if (!data) return;
    markers.pumps.forEach(function (m) { map.removeLayer(m); });
    markers.pumps = [];
    const filtered = data.filter(function (p) { return p.canal_id === currentCanal; });
    filtered.forEach(function (pump) {
        if (pump.lng == null || pump.lat == null) return;
        let color = "green";
        if (pump.latest_status) {
            const load = parseFloat(pump.latest_status.running_count) / pump.pump_count;
            if (load > 0.9) color = "yellow";
            if (load >= 1.0) color = "red";
        }
        const icon = L.divIcon({
            className: "",
            html: `<div class="pump-marker ${color}" title="${pump.name}">泵</div>`,
            iconSize: [30, 30],
            iconAnchor: [15, 15],
        });
        const marker = L.marker([pump.lat, pump.lng], { icon: icon });
        marker.on("click", function () {
            showPumpPopup(pump);
        });
        marker.addTo(map);
        markers.pumps.push(marker);
    });
}

async function loadKPIs() {
    const [balance, levels, power] = await Promise.all([
        apiGet("/monitoring/kpi/water-balance"),
        apiGet("/monitoring/kpi/water-levels"),
        apiGet("/monitoring/kpi/pump-power"),
    ]);

    if (balance) {
        const totalInflow = parseFloat(balance.total_inflow || 0);
        const totalOutflow = parseFloat(balance.total_outflow || 0);
        const netBalance = totalInflow - totalOutflow;
        const el = document.getElementById("kpi-balance-value");
        el.textContent = netBalance.toFixed(1);
        const card = document.getElementById("kpi-balance");
        card.className = "kpi-card";
        const errorPct = parseFloat(balance.total_inflow || 0) > 0
            ? Math.abs(netBalance / totalInflow * 100)
            : 0;
        if (errorPct > 20) card.classList.add("danger");
        else if (errorPct > 10) card.classList.add("warning");
    }

    if (levels) {
        let green = 0, yellow = 0, red = 0;
        levels.forEach(function (l) {
            if (l.status_color === "green") green++;
            else if (l.status_color === "yellow") yellow++;
            else if (l.status_color === "red") red++;
        });
        document.getElementById("kpi-level-value").textContent = `${green}/${yellow}/${red}`;
        const card = document.getElementById("kpi-level");
        card.className = "kpi-card";
        if (red > 0) card.classList.add("danger");
        else if (yellow > 0) card.classList.add("warning");
    }

    if (power) {
        let totalPower = 0;
        power.forEach(function (p) { totalPower += parseFloat(p.total_power || 0); });
        document.getElementById("kpi-power-value").textContent = (totalPower / 1000).toFixed(2);
    }
}

async function loadAlarms() {
    const filter = document.getElementById("alarm-filter").value;
    const data = await apiGet(`/alarm/?status=${filter}`);
    if (!data) return;
    const list = document.getElementById("alarm-list");
    list.innerHTML = "";
    data.slice(0, 50).forEach(function (alarm) {
        const item = document.createElement("div");
        item.className = `alarm-item level-${alarm.level} ${alarm.status}`;
        item.innerHTML = `
            <span class="alarm-level level-${alarm.level}">${alarm.level === 1 ? "一级" : "二级"}</span>
            <span class="alarm-time">${formatTime(alarm.created_at)}</span>
            <span class="alarm-message">${alarm.message}</span>
            <span class="alarm-actions">
                ${alarm.status === "active" ? `<button onclick="acknowledgeAlarm(${alarm.id})">确认</button>` : ""}
            </span>
        `;
        list.appendChild(item);
    });
    updateAlarmIndicator();
}

async function updateAlarmIndicator() {
    const data = await apiGet("/alarm/?status=active");
    const count = data ? data.length : 0;
    document.getElementById("alarm-count").textContent = count;
    const indicator = document.getElementById("alarm-indicator");
    if (count > 0) {
        indicator.classList.add("active");
    } else {
        indicator.classList.remove("active");
    }
}

async function acknowledgeAlarm(alarmId) {
    await apiPost("/alarm/acknowledge", { alarm_ids: [alarmId] });
    loadAlarms();
}

async function showSensorPopup(sensor) {
    selectedDevice = { type: "sensor", id: sensor.id, data: sensor };
    const data = await apiGet(`/monitoring/sensors/${sensor.id}/history?hours=24`);
    const popup = document.getElementById("popup-overlay");
    document.getElementById("popup-title").textContent = sensor.name;

    let html = '<div class="popup-info-grid">';
    html += infoItem("类型", sensor.sensor_type === "water_level" ? "水位计" : "流量计");
    html += infoItem("编码", sensor.code);
    html += infoItem("设计值", sensor.design_value, "green");
    html += infoItem("当前值", sensor.latest_value || "--", sensor.status_color);
    html += infoItem("偏差", sensor.deviation_percent ? sensor.deviation_percent.toFixed(1) + "%" : "--", sensor.status_color);
    html += infoItem("预警上限", sensor.warning_upper);
    html += infoItem("预警下限", sensor.warning_lower);
    html += "</div>";

    html += '<div class="popup-canvas-container"><canvas id="popup-trend-canvas" width="560" height="200"></canvas></div>';

    if (data && data.dispatch_history && data.dispatch_history.length > 0) {
        html += '<div class="popup-dispatch-title">调度指令历史</div>';
        data.dispatch_history.slice(0, 10).forEach(function (cmd) {
            html += `<div class="popup-dispatch-item">
                <span class="dispatch-status ${cmd.status}">${cmd.status}</span>
                <span>${cmd.command_type}: ${cmd.command_value}</span>
                <span style="color:var(--text-secondary)">${formatTime(cmd.created_at)}</span>
            </div>`;
        });
    }

    document.getElementById("popup-body").innerHTML = html;
    popup.style.display = "flex";

    if (data && data.data && data.data.length > 0) {
        setTimeout(function () {
            drawPopupTrend(data.data, sensor);
        }, 100);
    }

    drawTrendForSensor(sensor.id, sensor);
}

async function showGatePopup(gate) {
    selectedDevice = { type: "gate", id: gate.id, data: gate };
    const data = await apiGet(`/monitoring/gates/${gate.id}/history?hours=24`);
    const popup = document.getElementById("popup-overlay");
    document.getElementById("popup-title").textContent = gate.name;

    let html = '<div class="popup-info-grid">';
    html += infoItem("类型", gate.gate_type === "regulating" ? "调节闸" : gate.gate_type === "emergency" ? "应急闸" : "检修闸");
    html += infoItem("编码", gate.code);
    html += infoItem("设计流量", gate.design_flow + " m³/s");
    const opening = gate.latest_status ? gate.latest_status.opening : "--";
    const flow = gate.latest_status ? gate.latest_status.flow : "--";
    html += infoItem("当前开度", opening + "%");
    html += infoItem("当前流量", flow + " m³/s");
    html += "</div>";

    html += '<div class="popup-canvas-container"><canvas id="popup-trend-canvas" width="560" height="200"></canvas></div>';

    document.getElementById("popup-body").innerHTML = html;
    popup.style.display = "flex";

    if (data && data.length > 0) {
        setTimeout(function () {
            drawPopupTrend(data.map(function (d) {
                return { recorded_at: d.recorded_at, value: d.opening };
            }), gate, "开度(%)");
        }, 100);
    }
}

async function showPumpPopup(pump) {
    selectedDevice = { type: "pump", id: pump.id, data: pump };
    const data = await apiGet(`/monitoring/pump-stations/${pump.id}/history?hours=24`);
    const popup = document.getElementById("popup-overlay");
    document.getElementById("popup-title").textContent = pump.name;

    let html = '<div class="popup-info-grid">';
    html += infoItem("编码", pump.code);
    html += infoItem("机组数", pump.pump_count);
    html += infoItem("单泵功率", pump.single_pump_power + " kW");
    html += infoItem("设计流量", pump.design_flow + " m³/s");
    const running = pump.latest_status ? pump.latest_status.running_count : "--";
    const power = pump.latest_status ? pump.latest_status.total_power : "--";
    const flow = pump.latest_status ? pump.latest_status.total_flow : "--";
    html += infoItem("运行台数", running);
    html += infoItem("总功率", power + " kW");
    html += infoItem("总流量", flow + " m³/s");
    html += "</div>";

    html += '<div class="popup-canvas-container"><canvas id="popup-trend-canvas" width="560" height="200"></canvas></div>';

    document.getElementById("popup-body").innerHTML = html;
    popup.style.display = "flex";

    if (data && data.length > 0) {
        setTimeout(function () {
            drawPopupTrend(data.map(function (d) {
                return { recorded_at: d.recorded_at, value: d.total_power };
            }), pump, "功率(kW)");
        }, 100);
    }
}

function infoItem(label, value, colorClass) {
    return `<div class="popup-info-item">
        <span class="popup-info-label">${label}</span>
        <span class="popup-info-value ${colorClass || ""}">${value}</span>
    </div>`;
}

function closePopup() {
    document.getElementById("popup-overlay").style.display = "none";
}

async function drawTrendForSensor(sensorId, sensor) {
    const data = await apiGet(`/monitoring/sensors/${sensorId}/history?hours=24`);
    if (!data || !data.data) return;
    document.getElementById("trend-title").textContent = sensor.name + " - 近24小时趋势";
    drawTrend(data.data, sensor);
}

function downsampleData(points, maxPoints) {
    if (!points || points.length <= maxPoints) return points;
    const step = Math.ceil(points.length / maxPoints);
    const result = [points[0]];
    for (let i = step; i < points.length - 1; i += step) {
        let minIdx = i, maxIdx = i;
        let minVal = points[i].value, maxVal = points[i].value;
        const end = Math.min(i + step, points.length - 1);
        for (let j = i; j < end; j++) {
            const v = points[j].value;
            if (v < minVal) { minVal = v; minIdx = j; }
            if (v > maxVal) { maxVal = v; maxIdx = j; }
        }
        if (minIdx < maxIdx) {
            result.push(points[minIdx]);
            result.push(points[maxIdx]);
        } else if (maxIdx < minIdx) {
            result.push(points[maxIdx]);
            result.push(points[minIdx]);
        } else {
            result.push(points[i]);
        }
    }
    result.push(points[points.length - 1]);
    return result;
}

function viewportCull(points, xFn, yFn, margin, W, H) {
    if (!points || points.length === 0) return points;
    const xMin = -50, xMax = W + 50;
    const yMin = -50, yMax = H + 50;
    const result = [];
    for (let i = 0; i < points.length; i++) {
        const px = xFn(i);
        const py = yFn(points[i].value);
        if (px >= xMin && px <= xMax && py >= yMin && py <= yMax) {
            result.push(points[i]);
        } else if (result.length === 0 || result[result.length - 1] !== points[i]) {
            if (i > 0) result.push(points[i - 1]);
            result.push(points[i]);
            if (i < points.length - 1) result.push(points[i + 1]);
        }
    }
    return result.length > 0 ? result : points;
}

function drawProfile() {
    if (profileRenderPending) return;
    profileRenderPending = true;
    requestAnimationFrame(function () {
        profileRenderPending = false;
        _drawProfileImpl();
    });
}

function _drawProfileImpl() {
    const canvas = document.getElementById("profile-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    ctx.fillStyle = "#0a1628";
    ctx.fillRect(0, 0, W, H);

    const canalNames = { 1: "中线总干渠", 2: "东线干渠", 3: "引江济汉渠" };
    const profiles = {
        1: [
            { km: 0, elev: 147, wl: 147 },
            { km: 120, elev: 135, wl: 132 },
            { km: 300, elev: 110, wl: 108 },
            { km: 450, elev: 95, wl: 92 },
            { km: 620, elev: 87, wl: 85 },
            { km: 780, elev: 78, wl: 76 },
            { km: 960, elev: 70, wl: 68 },
            { km: 1100, elev: 60, wl: 58 },
            { km: 1432, elev: 50, wl: 48 },
        ],
        2: [
            { km: 0, elev: 7, wl: 6 },
            { km: 150, elev: 13, wl: 12 },
            { km: 350, elev: 19, wl: 18 },
            { km: 550, elev: 26, wl: 25 },
            { km: 750, elev: 32, wl: 30 },
            { km: 1156, elev: 38, wl: 35 },
        ],
        3: [
            { km: 0, elev: 29, wl: 28 },
            { km: 35, elev: 26, wl: 25 },
            { km: 67, elev: 23, wl: 22 },
        ],
    };

    const p = profiles[currentCanal] || profiles[1];
    const canalName = canalNames[currentCanal] || "";

    const margin = { top: 30, right: 40, bottom: 40, left: 60 };
    const plotW = W - margin.left - margin.right;
    const plotH = H - margin.top - margin.bottom;

    const minElev = Math.min.apply(null, p.map(function (d) { return d.wl; })) - 5;
    const maxElev = Math.max.apply(null, p.map(function (d) { return d.elev; })) + 10;
    const maxKm = p[p.length - 1].km;

    function x(km) { return margin.left + (km / maxKm) * plotW; }
    function y(elev) { return margin.top + plotH - ((elev - minElev) / (maxElev - minElev)) * plotH; }

    ctx.strokeStyle = "#1e3a5f";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 5; i++) {
        const elev = minElev + (maxElev - minElev) * i / 5;
        ctx.beginPath();
        ctx.moveTo(margin.left, y(elev));
        ctx.lineTo(W - margin.right, y(elev));
        ctx.stroke();
        ctx.fillStyle = "#8899aa";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "right";
        ctx.fillText(elev.toFixed(0) + "m", margin.left - 5, y(elev) + 3);
    }

    ctx.strokeStyle = "#5d4037";
    ctx.lineWidth = 2;
    ctx.beginPath();
    p.forEach(function (d, i) {
        if (i === 0) ctx.moveTo(x(d.km), y(d.elev));
        else ctx.lineTo(x(d.km), y(d.elev));
    });
    ctx.stroke();

    ctx.fillStyle = "rgba(33, 150, 243, 0.3)";
    ctx.beginPath();
    ctx.moveTo(x(p[0].km), y(p[0].wl));
    p.forEach(function (d) { ctx.lineTo(x(d.km), y(d.wl)); });
    ctx.lineTo(x(p[p.length - 1].km), y(minElev));
    ctx.lineTo(x(p[0].km), y(minElev));
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "#2196f3";
    ctx.lineWidth = 2;
    ctx.beginPath();
    p.forEach(function (d, i) {
        if (i === 0) ctx.moveTo(x(d.km), y(d.wl));
        else ctx.lineTo(x(d.km), y(d.wl));
    });
    ctx.stroke();

    ctx.fillStyle = "#00bcd4";
    ctx.font = "bold 12px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(canalName + " 纵剖面", margin.left, 18);

    ctx.fillStyle = "#8899aa";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    p.forEach(function (d) {
        ctx.fillText(d.km + "km", x(d.km), H - margin.bottom + 15);
        ctx.fillStyle = "#4caf50";
        ctx.beginPath();
        ctx.arc(x(d.km), y(d.wl), 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#8899aa";
    });

    ctx.save();
    ctx.translate(12, margin.top + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = "#8899aa";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("高程 (m)", 0, 0);
    ctx.restore();

    ctx.fillStyle = "#5d4037";
    ctx.fillRect(margin.left, H - 18, 12, 4);
    ctx.fillStyle = "#8899aa";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("渠底", margin.left + 16, H - 14);

    ctx.fillStyle = "#2196f3";
    ctx.fillRect(margin.left + 60, H - 18, 12, 4);
    ctx.fillStyle = "#8899aa";
    ctx.fillText("水位", margin.left + 76, H - 14);

    if (profileSensorsCache && profileCacheCanal === currentCanal) {
        _drawProfileSensors(ctx, profileSensorsCache, x, y, margin, W, H, maxKm, plotW);
    }
}

function _drawProfileSensors(ctx, sensors, xFn, yFn, margin, W, H, maxKm, plotW) {
    const visibleSensors = sensors.filter(function (s) {
        const px = xFn(s.km);
        return px >= margin.left - 10 && px <= W - margin.right + 10;
    });

    const lod = Math.max(1, Math.ceil(visibleSensors.length / Math.floor(plotW / 16)));
    const displayed = [];
    for (let i = 0; i < visibleSensors.length; i += lod) {
        displayed.push(visibleSensors[i]);
        if (lod > 1 && i + 1 < visibleSensors.length) {
            let worst = visibleSensors[i];
            for (let j = i + 1; j < Math.min(i + lod, visibleSensors.length); j++) {
                if (visibleSensors[j].status_color === "red") { worst = visibleSensors[j]; break; }
                if (visibleSensors[j].status_color === "yellow" && worst.status_color !== "red") { worst = visibleSensors[j]; }
            }
            if (displayed[displayed.length - 1] !== worst) displayed.push(worst);
        }
    }

    displayed.forEach(function (s) {
        const px = xFn(s.km);
        const py = yFn(s.wl);
        if (px < margin.left || px > W - margin.right) return;
        ctx.fillStyle = s.status_color === "red" ? "#f44336" : s.status_color === "yellow" ? "#ff9800" : "#4caf50";
        ctx.beginPath();
        if (s.sensor_type === "water_level") {
            ctx.arc(px, py, 3, 0, Math.PI * 2);
        } else {
            ctx.rect(px - 2, py - 2, 4, 4);
        }
        ctx.fill();
    });
}

function drawTrend(data, sensor) {
    if (trendRenderPending) return;
    trendRenderPending = true;
    requestAnimationFrame(function () {
        trendRenderPending = false;
        _drawTrendImpl(data, sensor);
    });
}

function _drawTrendImpl(data, sensor) {
    const canvas = document.getElementById("trend-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#0a1628";
    ctx.fillRect(0, 0, W, H);

    if (!data || data.length === 0) {
        ctx.fillStyle = "#8899aa";
        ctx.font = "14px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("暂无趋势数据 - 点击设备图标查看", W / 2, H / 2);
        return;
    }

    const margin = { top: 20, right: 20, bottom: 30, left: 60 };
    const plotW = W - margin.left - margin.right;
    const plotH = H - margin.top - margin.bottom;

    const maxPixels = Math.floor(plotW);
    const sampled = data.length > maxPixels ? downsampleData(data, maxPixels) : data;

    const values = sampled.map(function (d) { return parseFloat(d.value); });
    const minV = Math.min.apply(null, values) * 0.95;
    const maxV = Math.max.apply(null, values) * 1.05;
    const designVal = sensor ? parseFloat(sensor.design_value) : 0;

    function x(i) { return margin.left + (i / (sampled.length - 1)) * plotW; }
    function y(v) { return margin.top + plotH - ((v - minV) / (maxV - minV)) * plotH; }

    const culled = viewportCull(
        sampled.map(function (d, i) { return { value: parseFloat(d.value), index: i }; }),
        function (idx) { return x(idx); },
        function (v) { return y(v); },
        margin, W, H
    );

    ctx.strokeStyle = "#1e3a5f";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const v = minV + (maxV - minV) * i / 4;
        ctx.beginPath();
        ctx.moveTo(margin.left, y(v));
        ctx.lineTo(W - margin.right, y(v));
        ctx.stroke();
        ctx.fillStyle = "#8899aa";
        ctx.font = "9px sans-serif";
        ctx.textAlign = "right";
        ctx.fillText(v.toFixed(2), margin.left - 5, y(v) + 3);
    }

    if (designVal > 0) {
        ctx.strokeStyle = "#4caf50";
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(margin.left, y(designVal));
        ctx.lineTo(W - margin.right, y(designVal));
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "#4caf50";
        ctx.font = "9px sans-serif";
        ctx.textAlign = "left";
        ctx.fillText("设计值", W - margin.right + 2, y(designVal) + 3);
    }

    const culledValues = culled.map(function (d) { return d.value; });
    const gradient = ctx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
    gradient.addColorStop(0, "rgba(33, 150, 243, 0.3)");
    gradient.addColorStop(1, "rgba(33, 150, 243, 0.0)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(x(culled[0].index), y(culledValues[0]));
    culled.forEach(function (d) { ctx.lineTo(x(d.index), y(d.value)); });
    ctx.lineTo(x(culled[culled.length - 1].index), margin.top + plotH);
    ctx.lineTo(x(culled[0].index), margin.top + plotH);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "#2196f3";
    ctx.lineWidth = 2;
    ctx.beginPath();
    culled.forEach(function (d, i) {
        if (i === 0) ctx.moveTo(x(d.index), y(d.value));
        else ctx.lineTo(x(d.index), y(d.value));
    });
    ctx.stroke();

    if (sampled.length > 0) {
        const lastIdx = sampled.length - 1;
        ctx.fillStyle = "#2196f3";
        ctx.beginPath();
        ctx.arc(x(lastIdx), y(values[lastIdx]), 4, 0, Math.PI * 2);
        ctx.fill();
    }

    ctx.fillStyle = "#8899aa";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "center";
    const step = Math.max(1, Math.floor(sampled.length / 6));
    sampled.forEach(function (d, i) {
        if (i % step === 0) {
            const t = new Date(d.recorded_at);
            ctx.fillText(t.getHours() + ":" + String(t.getMinutes()).padStart(2, "0"), x(i), H - 8);
        }
    });
}

function drawPopupTrend(data, device, label) {
    const canvas = document.getElementById("popup-trend-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#0a1628";
    ctx.fillRect(0, 0, W, H);

    if (!data || data.length === 0) return;

    const margin = { top: 15, right: 15, bottom: 25, left: 50 };
    const plotW = W - margin.left - margin.right;
    const plotH = H - margin.top - margin.bottom;

    const maxPixels = Math.floor(plotW);
    const sampled = data.length > maxPixels ? downsampleData(data, maxPixels) : data;

    const values = sampled.map(function (d) { return parseFloat(d.value || d.opening || d.total_power || 0); });
    const minV = Math.min.apply(null, values) * 0.95;
    const maxV = Math.max.apply(null, values) * 1.05;

    function x(i) { return margin.left + (i / (sampled.length - 1)) * plotW; }
    function y(v) { return margin.top + plotH - ((v - minV) / (maxV - minV)) * plotH; }

    ctx.strokeStyle = "#1e3a5f";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const v = minV + (maxV - minV) * i / 4;
        ctx.beginPath();
        ctx.moveTo(margin.left, y(v));
        ctx.lineTo(W - margin.right, y(v));
        ctx.stroke();
        ctx.fillStyle = "#8899aa";
        ctx.font = "9px sans-serif";
        ctx.textAlign = "right";
        ctx.fillText(v.toFixed(1), margin.left - 4, y(v) + 3);
    }

    const gradient = ctx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
    gradient.addColorStop(0, "rgba(0, 188, 212, 0.3)");
    gradient.addColorStop(1, "rgba(0, 188, 212, 0.0)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(x(0), y(values[0]));
    values.forEach(function (v, i) { ctx.lineTo(x(i), y(v)); });
    ctx.lineTo(x(values.length - 1), margin.top + plotH);
    ctx.lineTo(x(0), margin.top + plotH);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "#00bcd4";
    ctx.lineWidth = 2;
    ctx.beginPath();
    values.forEach(function (v, i) {
        if (i === 0) ctx.moveTo(x(i), y(v));
        else ctx.lineTo(x(i), y(v));
    });
    ctx.stroke();

    if (label) {
        ctx.fillStyle = "#00bcd4";
        ctx.font = "bold 10px sans-serif";
        ctx.textAlign = "left";
        ctx.fillText(label, margin.left, 12);
    }

    ctx.fillStyle = "#8899aa";
    ctx.font = "8px sans-serif";
    ctx.textAlign = "center";
    const step = Math.max(1, Math.floor(sampled.length / 6));
    sampled.forEach(function (d, i) {
        if (i % step === 0) {
            const t = new Date(d.recorded_at);
            ctx.fillText(t.getHours() + ":" + String(t.getMinutes()).padStart(2, "0"), x(i), H - 5);
        }
    });
}

async function executeDispatch() {
    const canalId = parseInt(document.getElementById("dispatch-canal").value);
    const demand = parseFloat(document.getElementById("dispatch-demand").value);
    const resultDiv = document.getElementById("dispatch-result");
    resultDiv.innerHTML = "<div style='color:var(--text-secondary)'>正在计算调度方案...</div>";

    const result = await apiPost("/dispatch/plan", {
        canal_id: canalId,
        downstream_demand: demand,
    });

    if (!result) {
        resultDiv.innerHTML = "<div style='color:var(--accent-red)'>调度计算失败</div>";
        return;
    }

    let html = "";
    if (result.commands && result.commands.length > 0) {
        result.commands.forEach(function (cmd) {
            html += `<div class="dispatch-command-item">
                <span class="dispatch-status ${cmd.status}">${cmd.status}</span>
                <span>${cmd.target_name || cmd.target_type + "-" + cmd.target_id}</span>
                <span>${cmd.command_type}: ${cmd.command_value}</span>
            </div>`;
        });
    } else {
        html = "<div style='color:var(--text-secondary)'>无需调整</div>";
    }

    if (result.water_balance) {
        const wb = result.water_balance;
        html += `<div style="margin-top:8px;padding:8px;background:var(--bg-card);border-radius:4px;font-size:11px;">
            水量平衡 - 入流: ${wb.total_inflow} | 出流: ${wb.total_outflow} | 储量变化: ${wb.total_storage_change} | 误差: ${wb.balance_error_percent}%
        </div>`;
    }

    resultDiv.innerHTML = html;
}

async function loadDispatchCanalOptions() {
    const canals = await apiGet("/monitoring/canals");
    if (!canals) return;
    const select = document.getElementById("dispatch-canal");
    select.innerHTML = "";
    canals.forEach(function (c) {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = c.name;
        select.appendChild(opt);
    });
}

function formatTime(ts) {
    if (!ts) return "--";
    const d = new Date(ts);
    return d.getHours() + ":" + String(d.getMinutes()).padStart(2, "0");
}

function updateDateTime() {
    const now = new Date();
    const str = now.getFullYear() + "-" +
        String(now.getMonth() + 1).padStart(2, "0") + "-" +
        String(now.getDate()).padStart(2, "0") + " " +
        String(now.getHours()).padStart(2, "0") + ":" +
        String(now.getMinutes()).padStart(2, "0") + ":" +
        String(now.getSeconds()).padStart(2, "0");
    document.getElementById("datetime").textContent = str;
}

document.addEventListener("DOMContentLoaded", init);
