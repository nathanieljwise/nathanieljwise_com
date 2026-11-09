(() => {
    "use strict";

    const API = "/api/weather/";
    const MPS_TO_MPH = 2.23694;   // the API's wind speed is in m/s
    const REFRESH_MS = 5 * 60 * 1000;
    const STALE_MIN = 30;

    const COLORS = ["#33ccff", "#ff6b6b", "#ffd166", "#06d6a0", "#c792ea",
                    "#ff9f43", "#a3e635", "#f472b6", "#94a3b8", "#60a5fa"];
    const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

    const METRICS = {
        temp_f:      { label: "Temperature (°F)", unit: "°F",  dec: 1, conv: v => v },
        wind_speed:  { label: "Wind speed (mph)", unit: " mph", dec: 1, conv: v => v * MPS_TO_MPH },
        pressure_mb: { label: "Pressure (mb)",    unit: " mb", dec: 0, conv: v => v },
        humidity:    { label: "Humidity (%)",     unit: "%",   dec: 0, conv: v => v },
    };
    const RANGES = { "24h": "series_24h", "7d": "series_7d", "30d": "series_30d" };

    const state = { range: "24h", metric: "temp_f", selected: new Set(), cities: [], dailyCity: null };
    const seriesCache = {};
    let latest = null, daily = null;
    let seriesChart = null, dailyChart = null, seriesTimes = [];

    const $ = id => document.getElementById(id);
    const pretty = n => n.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
    const colorFor = n => COLORS[state.cities.indexOf(n) % COLORS.length];
    const compass = deg => (deg == null ? "" : COMPASS[Math.round(deg / 22.5) % 16]);
    const fmt = (v, d) => (v == null ? "–" : Number(v).toFixed(d));
    const mph = v => (v == null ? null : v * MPS_TO_MPH);

    function el(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    }

    function ago(ms) {
        const min = Math.max(0, Math.round(ms / 60000));
        if (min < 1) return "just now";
        if (min < 90) return `${min} min ago`;
        return `${Math.round(min / 60)} h ago`;
    }

    async function getJSON(name) {
        const r = await fetch(API + name + ".json", { cache: "no-cache" });
        if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
        return r.json();
    }

    /* ---------- current conditions ---------- */

    function renderCurrent() {
        const box = $("wx-current");
        box.replaceChildren();
        const now = Date.now();
        let newest = 0;

        state.cities.forEach(name => {
            const c = latest.cities[name];
            if (!c) return;
            const obs = Date.parse(c.observed_at);
            newest = Math.max(newest, obs);
            const stale = (now - obs) / 60000 > STALE_MIN;

            const card = el("div", "wx-card" + (stale ? " wx-stale" : ""));
            card.style.borderTopColor = colorFor(name);
            card.append(
                el("h3", null, pretty(name)),
                el("div", "wx-temp", `${fmt(c.temp_f, 1)}°F`),
                el("div", "wx-line", `Wind ${fmt(mph(c.wind_speed), 1)} mph ${compass(c.wind_dir)}`.trim()),
                el("div", "wx-line", `${fmt(c.pressure_mb, 0)} mb · ${fmt(c.humidity, 0)}% humidity`),
                el("div", "wx-line", stale ? `No recent data (${ago(now - obs)})` : ago(now - obs))
            );
            box.append(card);
        });

        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        $("wx-updated").textContent = newest
            ? `Latest reading ${ago(now - newest)}. Times are shown in your local time zone (${tz}).`
            : "No readings available.";
    }

    /* ---------- controls ---------- */

    function renderChips() {
        const box = $("wx-chips");
        box.replaceChildren();
        state.cities.forEach(name => {
            const b = el("button", "wx-chip", pretty(name));
            b.type = "button";
            b.style.setProperty("--chip", colorFor(name));
            b.setAttribute("aria-pressed", String(state.selected.has(name)));
            b.addEventListener("click", () => {
                if (state.selected.has(name)) {
                    if (state.selected.size === 1) return;  // keep at least one city
                    state.selected.delete(name);
                } else {
                    state.selected.add(name);
                }
                renderChips();
                loadSeries();
            });
            box.append(b);
        });
    }

    function buildControls() {
        const metric = $("wx-metric");
        Object.entries(METRICS).forEach(([key, m]) => {
            const o = el("option", null, m.label);
            o.value = key;
            metric.append(o);
        });
        metric.value = state.metric;
        metric.addEventListener("change", e => { state.metric = e.target.value; loadSeries(); });

        document.querySelectorAll("[data-range]").forEach(b => {
            b.addEventListener("click", () => {
                state.range = b.dataset.range;
                markRange();
                loadSeries();
            });
        });
        markRange();

        const sel = $("wx-daily-city");
        state.cities.forEach(name => {
            const o = el("option", null, pretty(name));
            o.value = name;
            sel.append(o);
        });
        sel.value = state.dailyCity;
        sel.addEventListener("change", e => { state.dailyCity = e.target.value; drawDaily(); });
        const roseSel = $("wx-rose-city");
        state.cities.forEach(name => {
            const o = el("option", null, pretty(name));
            o.value = name;
            roseSel.append(o);
        });
        roseSel.value = state.roseCity;
        roseSel.addEventListener("change", e => { state.roseCity = e.target.value; drawRose(); });
    }

    function markRange() {
        document.querySelectorAll("[data-range]").forEach(b => {
            b.classList.toggle("active", b.dataset.range === state.range);
        });
        drawRose();
    }

    /* ---------- history chart ---------- */

    function tickLabel(d) {
        if (state.range === "24h") {
            return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
        }
        if (state.range === "7d") {
            return d.toLocaleDateString([], { weekday: "short" }) + " " +
                   d.toLocaleTimeString([], { hour: "numeric" });
        }
        return d.toLocaleDateString([], { month: "short", day: "numeric" });
    }

    async function loadSeries() {
        const file = RANGES[state.range];
        try {
            if (!seriesCache[file]) seriesCache[file] = await getJSON(file);
            drawSeries(seriesCache[file]);
        } catch (e) {
            console.error(e);
        }
    }

    function drawSeries(data) {
        const m = METRICS[state.metric];
        const start = Date.parse(data.start);
        seriesTimes = Array.from({ length: data.n },
            (_, i) => new Date(start + i * data.step_min * 60000));
        const labels = seriesTimes.map(tickLabel);

        const datasets = state.cities
            .filter(n => state.selected.has(n) && data.cities[n] && data.cities[n][state.metric])
            .map(n => ({
                label: pretty(n),
                data: data.cities[n][state.metric].map(v => (v == null ? null : m.conv(v))),
                borderColor: colorFor(n),
                backgroundColor: colorFor(n),
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                spanGaps: false,   // missing data shows as a break in the line
                tension: 0.15,
            }));

        if (!seriesChart) {
            seriesChart = new Chart($("wx-series"), {
                type: "line",
                data: { labels, datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: { mode: "index", intersect: false },
                    plugins: {
                        legend: { labels: { usePointStyle: true } },
                        tooltip: {
                            callbacks: {
                                title: items => seriesTimes[items[0].dataIndex].toLocaleString([], {
                                    weekday: "short", month: "short", day: "numeric",
                                    hour: "numeric", minute: "2-digit",
                                }),
                                label: c => {
                                    const mm = METRICS[state.metric];
                                    return `${c.dataset.label}: ${fmt(c.parsed.y, mm.dec)}${mm.unit}`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: { grid: { display: false },
                             ticks: { autoSkip: true, maxTicksLimit: 8, maxRotation: 0 } },
                        y: { title: { display: true, text: m.label } },
                    },
                },
            });
        } else {
            seriesChart.data.labels = labels;
            seriesChart.data.datasets = datasets;
            seriesChart.options.scales.y.title.text = m.label;
            seriesChart.update();
        }
    }

    /* ---------- daily high/low chart ---------- */

    async function loadDaily() {
        try {
            daily = await getJSON("daily");
            drawDaily();
        } catch (e) {
            console.error(e);
        }
    }

    function drawDaily() {
        const rows = (daily && daily.cities[state.dailyCity]) || [];
        const labels = rows.map(r => {
            const [y, mo, d] = r.d.split("-").map(Number);
            return new Date(y, mo - 1, d).toLocaleDateString([], { month: "short", day: "numeric" });
        });
        const data = rows.map(r => [r.lo, r.hi]);
        const color = colorFor(state.dailyCity);

        if (!dailyChart) {
            dailyChart = new Chart($("wx-daily"), {
                type: "bar",
                data: { labels, datasets: [{ label: "Low to high (°F)", data,
                                             backgroundColor: color, borderRadius: 3 }] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: c => `Low ${fmt(c.raw[0], 1)}°F, high ${fmt(c.raw[1], 1)}°F`,
                            },
                        },
                    },
                    scales: {
                        x: { grid: { display: false },
                             ticks: { autoSkip: true, maxTicksLimit: 10, maxRotation: 0 } },
                        y: { beginAtZero: false, grace: "5%",
                             title: { display: true, text: "Temperature (°F)" } },
                    },
                },
            });
        } else {
            dailyChart.data.labels = labels;
            dailyChart.data.datasets[0].data = data;
            dailyChart.data.datasets[0].backgroundColor = color;
            dailyChart.update();
        }
    }
    /* ---------- wind rose ---------- */

    const ROSE_COLORS = ["#1f6f8b", "#2aa3c9", "#33ccff", "#9be7ff", "#ffffff"];  // one per speed band
    const PERIOD_NAMES = { "24h": "24 hours", "7d": "7 days", "30d": "30 days" };
    const SVG_NS = "http://www.w3.org/2000/svg";
    const ROSE = { cx: 220, cy: 220, r0: 26, r: 150 };   // centre, inner hole, outer radius
    let rose = null;

    function svg(tag, attrs, text) {
        const e = document.createElementNS(SVG_NS, tag);
        for (const k in attrs) e.setAttribute(k, attrs[k]);
        if (text != null) e.textContent = text;
        return e;
    }

    // Point at radius r on compass bearing deg (0 = north, clockwise)
    function polar(r, deg) {
        const a = deg * Math.PI / 180;
        return [ROSE.cx + r * Math.sin(a), ROSE.cy - r * Math.cos(a)];
    }

    function wedge(r0, r1, a0, a1) {
        const p = (r, a) => polar(r, a).map(n => n.toFixed(1)).join(" ");
        return `M ${p(r0, a0)} L ${p(r1, a0)} A ${r1} ${r1} 0 0 1 ${p(r1, a1)} ` +
               `L ${p(r0, a1)} A ${r0} ${r0} 0 0 0 ${p(r0, a0)} Z`;
    }

    async function loadRose() {
        try {
            rose = await getJSON("wind_rose");
            drawRose();
        } catch (e) {
            console.error(e);
        }
    }

    function drawRose() {
        if (!rose) return;
        const box = $("wx-rose");
        const city = state.roseCity;
        const data = rose.periods[state.range] && rose.periods[state.range][city];
        $("wx-rose-title").textContent = `Wind rose, last ${PERIOD_NAMES[state.range]}`;
        box.replaceChildren();
        if (!data || !data.n) {
            box.append(el("p", "wx-note", "No wind data for this period."));
            return;
        }

        const edges = rose.edges_mph;
        const bands = edges.map((e, i) => `${i ? edges[i - 1] : 0}–${e}`).concat(`${edges[edges.length - 1]}+`);
        const maxPct = Math.max(...data.bins.map(b => b.reduce((a, c) => a + c, 0))) / data.n * 100;
        const step = [1, 2, 5, 10, 20, 25, 50].find(s => s >= maxPct / 4) || 50;   // ring spacing, in %
        const rings = Math.max(1, Math.ceil(maxPct / step));
        const rad = pct => ROSE.r0 + pct / (rings * step) * (ROSE.r - ROSE.r0);

        const s = svg("svg", { viewBox: "0 0 440 440", role: "img",
                               "aria-label": `Wind rose for ${pretty(city)}` });

        // grid: rings with % labels, and a spoke every 45 degrees
        for (let i = 1; i <= rings; i++) {
            s.append(svg("circle", { cx: ROSE.cx, cy: ROSE.cy, r: rad(i * step), class: "wx-ring" }));
            const [lx, ly] = polar(rad(i * step), 191.25);
            for (const cls of ["wx-ring-halo", "wx-ring-label"]) {   // halo first, so the label stays legible over bars
                s.append(svg("text", { x: lx, y: ly + 4, class: cls }, `${i * step}%`));
            }
        }
        for (let d = 0; d < 360; d += 45) {
            const [x, y] = polar(ROSE.r, d), [x0, y0] = polar(ROSE.r0, d);
            s.append(svg("line", { x1: x0, y1: y0, x2: x, y2: y, class: "wx-ring" }));
        }

        // stacked wedges: one per direction, one segment per speed band (calm to strong, inward to outward)
        data.bins.forEach((counts, i) => {
            let cum = 0;
            counts.forEach((c, j) => {
                if (!c) return;
                const pct = c / data.n * 100;
                const path = svg("path", {
                    d: wedge(rad(cum), rad(cum + pct), i * 22.5 - 10.5, i * 22.5 + 10.5),
                    fill: ROSE_COLORS[j], class: "wx-wedge",
                });
                path.append(svg("title", {}, `${COMPASS[i]}, ${bands[j]} mph: ${pct.toFixed(1)}%`));
                s.append(path);
                cum += pct;
            });
        });

        // compass labels
        for (let d = 0; d < 360; d += 45) {
            const [x, y] = polar(186, d);
            s.append(svg("text", { x, y: y + 5, class: d % 90 ? "wx-dir" : "wx-dir wx-dir-main" },
                         COMPASS[d / 22.5]));
        }

        // marker for the wind direction right now (where it is blowing from)
        const cur = latest && latest.cities[city];
        if (cur && cur.wind_dir != null) {
            const pts = [polar(ROSE.r + 6, cur.wind_dir), polar(ROSE.r + 20, cur.wind_dir - 4),
                         polar(ROSE.r + 20, cur.wind_dir + 4)].map(p => p.map(n => n.toFixed(1)).join(",")).join(" ");
            const marker = svg("polygon", { points: pts, class: "wx-now" });
            marker.append(svg("title", {}, `Now: ${cur.wind_dir}° ${compass(cur.wind_dir)}`));
            s.append(marker);
        }

        // centre: share of readings with no measurable wind
        s.append(svg("text", { x: ROSE.cx, y: ROSE.cy - 2, class: "wx-calm" }, "Calm"));
        s.append(svg("text", { x: ROSE.cx, y: ROSE.cy + 11, class: "wx-calm" },
                     `${(data.calm / data.n * 100).toFixed(0)}%`));

        const legend = el("div", "wx-legend");
        bands.forEach((b, i) => {
            const item = el("span", "wx-legend-item", `${b} mph`);
            item.style.setProperty("--sw", ROSE_COLORS[i]);
            legend.append(item);
        });
        box.append(s, legend, el("p", "wx-note",
            `Based on ${data.n} readings. A longer bar means the wind blew from that direction more often. ` +
            `The yellow marker shows the direction it is blowing from now. The period follows the History buttons.`));
    }
    /* ---------- startup and refresh ---------- */

    async function refresh() {
        try {
            latest = await getJSON("latest");
            renderCurrent();
            Object.keys(seriesCache).forEach(k => delete seriesCache[k]);
            await loadSeries();
            await loadDaily();
            await loadRose();
        } catch (e) {
            console.error(e);
        }
    }

    async function init() {
        if (typeof Chart === "undefined") {
            $("wx-updated").textContent = "Chart library failed to load.";
            return;
        }
        Chart.defaults.color = "#d3d3d3";
        Chart.defaults.borderColor = "rgba(255, 255, 255, 0.1)";
        Chart.defaults.font.family = "'Open Sans', Helvetica, Arial, sans-serif";

        try {
            latest = await getJSON("latest");
        } catch (e) {
            console.error(e);
            $("wx-updated").textContent = "Weather data is unavailable right now.";
            return;
        }
        state.cities = Object.keys(latest.cities).sort();
        const first = state.cities.includes("dundalk") ? "dundalk" : state.cities[0];
        state.selected.add(first);
        state.dailyCity = first;
        state.roseCity = first;

        buildControls();
        renderCurrent();
        renderChips();
        await Promise.all([loadSeries(), loadDaily(), loadRose()]);
        setInterval(refresh, REFRESH_MS);
    }

    init();
})();
