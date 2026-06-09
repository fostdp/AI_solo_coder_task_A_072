var API_BASE = "/api";
var ws = null;
var selectedDevice = null;

function init() {
    PlainMap.init({
        onSensorClick: showSensorPopup,
        onGateClick: showGatePopup,
        onPumpClick: showPumpPopup,
    });
    initWebSocket();
    initEventListeners();
    updateDateTime();
    setInterval(updateDateTime, 1000);
    loadInitialData();
    setInterval(refreshData, 30000);
    ProfileView.drawProfile(PlainMap.getCanal());
}

function initWebSocket() {
    var protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(protocol + "//" + location.host + "/ws");
    ws.onmessage = function (event) {
        try {
            var msg = JSON.parse(event.data);
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
        var canalId = parseInt(this.value);
        PlainMap.setCanal(canalId);
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
        var panel = document.getElementById("dispatch-panel");
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
    ProfileView.drawProfile(PlainMap.getCanal());
}

async function apiGet(path) {
    try {
        var resp = await fetch(API_BASE + path);
        if (resp.ok) return await resp.json();
    } catch (e) {}
    return null;
}

async function apiPost(path, body) {
    try {
        var resp = await fetch(API_BASE + path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (resp.ok) return await resp.json();
    } catch (e) {}
    return null;
}

async function loadCanals() {
    var data = await apiGet("/water-balance/canals");
    PlainMap.loadCanals(data);
}

async function loadSensors() {
    var data = await apiGet("/dtu/sensors");
    if (!data) return;
    PlainMap.loadSensors(data);
    ProfileView.updateSensorCache(data, PlainMap.getCanal());
}

async function loadGates() {
    var data = await apiGet("/dispatch/gates");
    PlainMap.loadGates(data);
}

async function loadPumpStations() {
    var data = await apiGet("/dispatch/pump-stations");
    PlainMap.loadPumpStations(data);
}

async function loadKPIs() {
    var balance = await apiGet("/water-balance/kpi/water-balance");
    var levels = await apiGet("/water-balance/kpi/water-levels");
    var power = await apiGet("/dispatch/kpi/pump-power");

    if (balance) {
        var totalInflow = parseFloat(balance.total_inflow || 0);
        var totalOutflow = parseFloat(balance.total_outflow || 0);
        var netBalance = totalInflow - totalOutflow;
        var el = document.getElementById("kpi-balance-value");
        el.textContent = netBalance.toFixed(1);
        var card = document.getElementById("kpi-balance");
        card.className = "kpi-card";
        var errorPct = totalInflow > 0 ? Math.abs(netBalance / totalInflow * 100) : 0;
        if (errorPct > 20) card.classList.add("danger");
        else if (errorPct > 10) card.classList.add("warning");
    }

    if (levels) {
        var green = 0, yellow = 0, red = 0;
        levels.forEach(function (l) {
            if (l.status_color === "green") green++;
            else if (l.status_color === "yellow") yellow++;
            else if (l.status_color === "red") red++;
        });
        document.getElementById("kpi-level-value").textContent = green + "/" + yellow + "/" + red;
        var card2 = document.getElementById("kpi-level");
        card2.className = "kpi-card";
        if (red > 0) card2.classList.add("danger");
        else if (yellow > 0) card2.classList.add("warning");
    }

    if (power) {
        var totalPower = 0;
        power.forEach(function (p) { totalPower += parseFloat(p.total_power || 0); });
        document.getElementById("kpi-power-value").textContent = (totalPower / 1000).toFixed(2);
    }
}

async function loadAlarms() {
    var filter = document.getElementById("alarm-filter").value;
    var data = await apiGet("/alarm/?status=" + filter);
    if (!data) return;
    var list = document.getElementById("alarm-list");
    list.innerHTML = "";
    data.slice(0, 50).forEach(function (alarm) {
        var item = document.createElement("div");
        item.className = "alarm-item level-" + alarm.level + " " + alarm.status;
        item.innerHTML =
            '<span class="alarm-level level-' + alarm.level + '">' + (alarm.level === 1 ? "一级" : "二级") + '</span>' +
            '<span class="alarm-time">' + formatTime(alarm.created_at) + '</span>' +
            '<span class="alarm-message">' + alarm.message + '</span>' +
            '<span class="alarm-actions">' +
            (alarm.status === "active" ? '<button onclick="acknowledgeAlarm(' + alarm.id + ')">确认</button>' : "") +
            '</span>';
        list.appendChild(item);
    });
    updateAlarmIndicator();
}

async function updateAlarmIndicator() {
    var data = await apiGet("/alarm/?status=active");
    var count = data ? data.length : 0;
    document.getElementById("alarm-count").textContent = count;
    var indicator = document.getElementById("alarm-indicator");
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
    var data = await apiGet("/dtu/sensors/" + sensor.id + "/history?hours=24");
    var popup = document.getElementById("popup-overlay");
    document.getElementById("popup-title").textContent = sensor.name;

    var html = '<div class="popup-info-grid">';
    html += infoItem("类型", sensor.sensor_type === "water_level" ? "水位计" : "流量计");
    html += infoItem("编码", sensor.code);
    html += infoItem("设计值", sensor.design_value, "green");
    html += infoItem("当前值", sensor.latest_value || "--", sensor.status_color);
    html += infoItem("偏差", sensor.deviation_percent ? sensor.deviation_percent.toFixed(1) + "%" : "--", sensor.status_color);
    html += infoItem("预警上限", sensor.warning_upper);
    html += infoItem("预警下限", sensor.warning_lower);
    html += "</div>";

    html += '<div class="popup-canvas-container"><canvas id="popup-trend-canvas" width="560" height="200"></canvas></div>';

    document.getElementById("popup-body").innerHTML = html;
    popup.style.display = "flex";

    if (data && data.data && data.data.length > 0) {
        setTimeout(function () {
            ProfileView.drawPopupTrend(data.data, sensor);
        }, 100);
    }

    ProfileView.drawTrend(data ? data.data : [], sensor);
    document.getElementById("trend-title").textContent = sensor.name + " - 近24小时趋势";
}

async function showGatePopup(gate) {
    selectedDevice = { type: "gate", id: gate.id, data: gate };
    var data = await apiGet("/dispatch/gates/" + gate.id + "/history?hours=24");
    var popup = document.getElementById("popup-overlay");
    document.getElementById("popup-title").textContent = gate.name;

    var html = '<div class="popup-info-grid">';
    html += infoItem("类型", gate.gate_type === "regulating" ? "调节闸" : gate.gate_type === "emergency" ? "应急闸" : "检修闸");
    html += infoItem("编码", gate.code);
    html += infoItem("设计流量", gate.design_flow + " m³/s");
    var opening = gate.latest_status ? gate.latest_status.opening : "--";
    var flow = gate.latest_status ? gate.latest_status.flow : "--";
    html += infoItem("当前开度", opening + "%");
    html += infoItem("当前流量", flow + " m³/s");
    html += "</div>";

    html += '<div class="popup-canvas-container"><canvas id="popup-trend-canvas" width="560" height="200"></canvas></div>';

    document.getElementById("popup-body").innerHTML = html;
    popup.style.display = "flex";

    if (data && data.length > 0) {
        setTimeout(function () {
            ProfileView.drawPopupTrend(data.map(function (d) {
                return { recorded_at: d.recorded_at, value: d.opening };
            }), gate, "开度(%)");
        }, 100);
    }
}

async function showPumpPopup(pump) {
    selectedDevice = { type: "pump", id: pump.id, data: pump };
    var data = await apiGet("/dispatch/pump-stations/" + pump.id + "/history?hours=24");
    var popup = document.getElementById("popup-overlay");
    document.getElementById("popup-title").textContent = pump.name;

    var html = '<div class="popup-info-grid">';
    html += infoItem("编码", pump.code);
    html += infoItem("机组数", pump.pump_count);
    html += infoItem("单泵功率", pump.single_pump_power + " kW");
    html += infoItem("设计流量", pump.design_flow + " m³/s");
    var running = pump.latest_status ? pump.latest_status.running_count : "--";
    var power = pump.latest_status ? pump.latest_status.total_power : "--";
    var flow = pump.latest_status ? pump.latest_status.total_flow : "--";
    html += infoItem("运行台数", running);
    html += infoItem("总功率", power + " kW");
    html += infoItem("总流量", flow + " m³/s");
    html += "</div>";

    html += '<div class="popup-canvas-container"><canvas id="popup-trend-canvas" width="560" height="200"></canvas></div>';

    document.getElementById("popup-body").innerHTML = html;
    popup.style.display = "flex";

    if (data && data.length > 0) {
        setTimeout(function () {
            ProfileView.drawPopupTrend(data.map(function (d) {
                return { recorded_at: d.recorded_at, value: d.total_power };
            }), pump, "功率(kW)");
        }, 100);
    }
}

function infoItem(label, value, colorClass) {
    return '<div class="popup-info-item">' +
        '<span class="popup-info-label">' + label + '</span>' +
        '<span class="popup-info-value ' + (colorClass || "") + '">' + value + '</span>' +
        '</div>';
}

function closePopup() {
    document.getElementById("popup-overlay").style.display = "none";
}

async function executeDispatch() {
    var canalId = parseInt(document.getElementById("dispatch-canal").value);
    var demand = parseFloat(document.getElementById("dispatch-demand").value);
    var resultDiv = document.getElementById("dispatch-result");
    resultDiv.innerHTML = "<div style='color:var(--text-secondary)'>正在计算调度方案...</div>";

    var result = await apiPost("/water-balance/plan", {
        canal_id: canalId,
        downstream_demand: demand,
    });

    if (!result) {
        resultDiv.innerHTML = "<div style='color:var(--accent-red)'>调度计算失败</div>";
        return;
    }

    var html = "";
    if (result.commands && result.commands.length > 0) {
        result.commands.forEach(function (cmd) {
            html += '<div class="dispatch-command-item">' +
                '<span class="dispatch-status ' + cmd.status + '">' + cmd.status + '</span>' +
                '<span>' + (cmd.target_name || cmd.target_type + "-" + cmd.target_id) + '</span>' +
                '<span>' + cmd.command_type + ': ' + cmd.command_value + '</span>' +
                '</div>';
        });
    } else {
        html = "<div style='color:var(--text-secondary)'>无需调整</div>";
    }

    if (result.water_balance) {
        var wb = result.water_balance;
        html += '<div style="margin-top:8px;padding:8px;background:var(--bg-card);border-radius:4px;font-size:11px;">' +
            '水量平衡 - 入流: ' + wb.total_inflow + ' | 出流: ' + wb.total_outflow +
            ' | 储量变化: ' + wb.total_storage_change + ' | 误差: ' + wb.balance_error_percent + '%' +
            '</div>';
    }

    resultDiv.innerHTML = html;
}

async function loadDispatchCanalOptions() {
    var canals = await apiGet("/water-balance/canals");
    if (!canals) return;
    var select = document.getElementById("dispatch-canal");
    select.innerHTML = "";
    canals.forEach(function (c) {
        var opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = c.name;
        select.appendChild(opt);
    });
}

function formatTime(ts) {
    if (!ts) return "--";
    var d = new Date(ts);
    return d.getHours() + ":" + String(d.getMinutes()).padStart(2, "0");
}

function updateDateTime() {
    var now = new Date();
    var str = now.getFullYear() + "-" +
        String(now.getMonth() + 1).padStart(2, "0") + "-" +
        String(now.getDate()).padStart(2, "0") + " " +
        String(now.getHours()).padStart(2, "0") + ":" +
        String(now.getMinutes()).padStart(2, "0") + ":" +
        String(now.getSeconds()).padStart(2, "0");
    document.getElementById("datetime").textContent = str;
}

document.addEventListener("DOMContentLoaded", init);
