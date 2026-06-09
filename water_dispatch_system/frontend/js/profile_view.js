var ProfileView = (function () {
    var profileSensorsCache = null;
    var profileCacheCanal = -1;
    var profileRenderPending = false;
    var trendRenderPending = false;

    function downsampleData(points, maxPoints) {
        if (!points || points.length <= maxPoints) return points;
        var step = Math.ceil(points.length / maxPoints);
        var result = [points[0]];
        for (var i = step; i < points.length - 1; i += step) {
            var minIdx = i, maxIdx = i;
            var minVal = points[i].value, maxVal = points[i].value;
            var end = Math.min(i + step, points.length - 1);
            for (var j = i; j < end; j++) {
                var v = points[j].value;
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
        var xMin = -50, xMax = W + 50;
        var yMin = -50, yMax = H + 50;
        var result = [];
        for (var i = 0; i < points.length; i++) {
            var px = xFn(i);
            var py = yFn(points[i].value);
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

    function drawProfile(currentCanal) {
        if (profileRenderPending) return;
        profileRenderPending = true;
        requestAnimationFrame(function () {
            profileRenderPending = false;
            _drawProfileImpl(currentCanal);
        });
    }

    function _drawProfileImpl(currentCanal) {
        var canvas = document.getElementById("profile-canvas");
        if (!canvas) return;
        var ctx = canvas.getContext("2d");
        var W = canvas.width;
        var H = canvas.height;
        ctx.clearRect(0, 0, W, H);

        ctx.fillStyle = "#0a1628";
        ctx.fillRect(0, 0, W, H);

        var canalNames = { 1: "中线总干渠", 2: "东线干渠", 3: "引江济汉渠" };
        var profiles = {
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

        var p = profiles[currentCanal] || profiles[1];
        var canalName = canalNames[currentCanal] || "";

        var margin = { top: 30, right: 40, bottom: 40, left: 60 };
        var plotW = W - margin.left - margin.right;
        var plotH = H - margin.top - margin.bottom;

        var minElev = Math.min.apply(null, p.map(function (d) { return d.wl; })) - 5;
        var maxElev = Math.max.apply(null, p.map(function (d) { return d.elev; })) + 10;
        var maxKm = p[p.length - 1].km;

        function x(km) { return margin.left + (km / maxKm) * plotW; }
        function y(elev) { return margin.top + plotH - ((elev - minElev) / (maxElev - minElev)) * plotH; }

        ctx.strokeStyle = "#1e3a5f";
        ctx.lineWidth = 0.5;
        for (var i = 0; i <= 5; i++) {
            var elev = minElev + (maxElev - minElev) * i / 5;
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
        var visibleSensors = sensors.filter(function (s) {
            var px = xFn(s.km);
            return px >= margin.left - 10 && px <= W - margin.right + 10;
        });

        var lod = Math.max(1, Math.ceil(visibleSensors.length / Math.floor(plotW / 16)));
        var displayed = [];
        for (var i = 0; i < visibleSensors.length; i += lod) {
            displayed.push(visibleSensors[i]);
            if (lod > 1 && i + 1 < visibleSensors.length) {
                var worst = visibleSensors[i];
                for (var j = i + 1; j < Math.min(i + lod, visibleSensors.length); j++) {
                    if (visibleSensors[j].status_color === "red") { worst = visibleSensors[j]; break; }
                    if (visibleSensors[j].status_color === "yellow" && worst.status_color !== "red") { worst = visibleSensors[j]; }
                }
                if (displayed[displayed.length - 1] !== worst) displayed.push(worst);
            }
        }

        displayed.forEach(function (s) {
            var px = xFn(s.km);
            var py = yFn(s.wl);
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

    function updateSensorCache(sensors, currentCanal) {
        var profileKmMap = {
            1: { 0: 0, 120: 120, 300: 300, 450: 450, 620: 620, 780: 780, 960: 960, 1100: 1100, 1432: 1432 },
            2: { 0: 0, 150: 150, 350: 350, 550: 550, 750: 750, 1156: 1156 },
            3: { 0: 0, 35: 35, 67: 67 },
        };
        var filtered = sensors.filter(function (s) { return s.canal_id === currentCanal; });

        profileSensorsCache = filtered.map(function (s) {
            var sectionKm = profileKmMap[currentCanal] || {};
            var km = 0;
            var keys = Object.keys(sectionKm).map(Number).sort(function (a, b) { return a - b; });
            for (var i = 0; i < keys.length; i++) {
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
        var canvas = document.getElementById("trend-canvas");
        if (!canvas) return;
        var ctx = canvas.getContext("2d");
        var W = canvas.width;
        var H = canvas.height;
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

        var margin = { top: 20, right: 20, bottom: 30, left: 60 };
        var plotW = W - margin.left - margin.right;
        var plotH = H - margin.top - margin.bottom;

        var maxPixels = Math.floor(plotW);
        var sampled = data.length > maxPixels ? downsampleData(data, maxPixels) : data;

        var values = sampled.map(function (d) { return parseFloat(d.value); });
        var minV = Math.min.apply(null, values) * 0.95;
        var maxV = Math.max.apply(null, values) * 1.05;
        var designVal = sensor ? parseFloat(sensor.design_value) : 0;

        function x(i) { return margin.left + (i / (sampled.length - 1)) * plotW; }
        function y(v) { return margin.top + plotH - ((v - minV) / (maxV - minV)) * plotH; }

        var culled = viewportCull(
            sampled.map(function (d, i) { return { value: parseFloat(d.value), index: i }; }),
            function (idx) { return x(idx); },
            function (v) { return y(v); },
            margin, W, H
        );

        ctx.strokeStyle = "#1e3a5f";
        ctx.lineWidth = 0.5;
        for (var i = 0; i <= 4; i++) {
            var v = minV + (maxV - minV) * i / 4;
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

        var culledValues = culled.map(function (d) { return d.value; });
        var gradient = ctx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
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
            var lastIdx = sampled.length - 1;
            ctx.fillStyle = "#2196f3";
            ctx.beginPath();
            ctx.arc(x(lastIdx), y(values[lastIdx]), 4, 0, Math.PI * 2);
            ctx.fill();
        }

        ctx.fillStyle = "#8899aa";
        ctx.font = "9px sans-serif";
        ctx.textAlign = "center";
        var step = Math.max(1, Math.floor(sampled.length / 6));
        sampled.forEach(function (d, i) {
            if (i % step === 0) {
                var t = new Date(d.recorded_at);
                ctx.fillText(t.getHours() + ":" + String(t.getMinutes()).padStart(2, "0"), x(i), H - 8);
            }
        });
    }

    function drawPopupTrend(data, device, label) {
        var canvas = document.getElementById("popup-trend-canvas");
        if (!canvas) return;
        var ctx = canvas.getContext("2d");
        var W = canvas.width;
        var H = canvas.height;
        ctx.clearRect(0, 0, W, H);
        ctx.fillStyle = "#0a1628";
        ctx.fillRect(0, 0, W, H);

        if (!data || data.length === 0) return;

        var margin = { top: 15, right: 15, bottom: 25, left: 50 };
        var plotW = W - margin.left - margin.right;
        var plotH = H - margin.top - margin.bottom;

        var maxPixels = Math.floor(plotW);
        var sampled = data.length > maxPixels ? downsampleData(data, maxPixels) : data;

        var values = sampled.map(function (d) { return parseFloat(d.value || d.opening || d.total_power || 0); });
        var minV = Math.min.apply(null, values) * 0.95;
        var maxV = Math.max.apply(null, values) * 1.05;

        function x(i) { return margin.left + (i / (sampled.length - 1)) * plotW; }
        function y(v) { return margin.top + plotH - ((v - minV) / (maxV - minV)) * plotH; }

        ctx.strokeStyle = "#1e3a5f";
        ctx.lineWidth = 0.5;
        for (var i = 0; i <= 4; i++) {
            var v = minV + (maxV - minV) * i / 4;
            ctx.beginPath();
            ctx.moveTo(margin.left, y(v));
            ctx.lineTo(W - margin.right, y(v));
            ctx.stroke();
            ctx.fillStyle = "#8899aa";
            ctx.font = "9px sans-serif";
            ctx.textAlign = "right";
            ctx.fillText(v.toFixed(1), margin.left - 4, y(v) + 3);
        }

        var gradient = ctx.createLinearGradient(0, margin.top, 0, margin.top + plotH);
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
        var step = Math.max(1, Math.floor(sampled.length / 6));
        sampled.forEach(function (d, i) {
            if (i % step === 0) {
                var t = new Date(d.recorded_at);
                ctx.fillText(t.getHours() + ":" + String(t.getMinutes()).padStart(2, "0"), x(i), H - 5);
            }
        });
    }

    return {
        drawProfile: drawProfile,
        drawTrend: drawTrend,
        drawPopupTrend: drawPopupTrend,
        updateSensorCache: updateSensorCache,
    };
})();
