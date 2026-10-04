(() => {
    const root = document.getElementById('adminDashboard');
    if (!root || !window.L || !window.Chart) return;

    const form = document.getElementById('adminFilters');
    const status = document.getElementById('adminStatus');
    const errorBox = document.getElementById('adminError');
    const map = L.map('adminMap').setView([20, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18, attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    const markerLayer = L.featureGroup().addTo(map);
    let heatLayer = null;
    let displayMode = 'markers';
    const charts = {};
    const classColors = { Excellent: '#16845b', Good: '#3788c2', Weak: '#e5a51b', 'Dead Zone': '#d94b50' };
    const classNames = ['Excellent', 'Good', 'Weak', 'Dead Zone'];
    const fmt = (value, decimals = 2) => value === null || value === undefined || !Number.isFinite(Number(value))
        ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: decimals });
    Chart.defaults.font.family = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif';
    Chart.defaults.color = '#718096';

    function put(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    }

    function filters() {
        const params = new URLSearchParams(new FormData(form));
        for (const [key, value] of [...params.entries()]) if (!value) params.delete(key);
        return params;
    }

    function chart(id, config) {
        const canvas = document.getElementById(id);
        if (charts[id]) charts[id].destroy();
        charts[id] = new Chart(canvas, config);
    }

    function renderSummary(data) {
        const s = data.summary;
        put('admUsers', fmt(s.total_users, 0));
        put('admMeasurements', fmt(s.total_measurements, 0));
        put('admDownload', fmt(s.average_download_mbps));
        put('admUpload', fmt(s.average_upload_mbps));
        put('admLatency', fmt(s.average_latency_ms));
        put('admScore', fmt(s.average_score));
        put('admWeak', fmt(s.weak_measurements, 0));
        put('admDead', fmt(s.dead_zone_measurements, 0));
        put('admGoodCells', fmt(s.good_location_cells, 0));
    }

    function renderCharts(data) {
        const trend = data.trend;
        chart('adminTrendChart', {
            type: 'line',
            data: { labels: trend.map(row => row.day), datasets: [
                { label: 'Score / 100', data: trend.map(row => row.average_score), borderColor: '#2869cf', backgroundColor: '#2869cf1b', yAxisID: 'score', fill: true, tension: .3, pointRadius: 2, spanGaps: true },
                { label: 'Download Mbps', data: trend.map(row => row.average_download_mbps), borderColor: '#13a581', yAxisID: 'speed', tension: .3, pointRadius: 2, spanGaps: true },
                { label: 'Upload Mbps', data: trend.map(row => row.average_upload_mbps), borderColor: '#e0a52d', yAxisID: 'speed', tension: .3, pointRadius: 2, spanGaps: true }
            ]},
            options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'bottom' } }, scales: {
                score: { min: 0, max: 100, position: 'left', title: { display: true, text: 'Score' }, grid: { color: '#edf1f6' } },
                speed: { beginAtZero: true, position: 'right', title: { display: true, text: 'Mbps' }, grid: { drawOnChartArea: false } }
            }}
        });
        chart('adminClassChart', {
            type: 'doughnut',
            data: { labels: classNames, datasets: [{ data: classNames.map(name => data.classifications[name] || 0), backgroundColor: classNames.map(name => classColors[name]), borderWidth: 0 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: { position: 'bottom' } } }
        });
        const locationRows = [...data.locations].sort((a, b) => b.poor_rate - a.poor_rate).slice(0, 10);
        chart('adminLocationChart', {
            type: 'bar',
            data: { labels: locationRows.map(row => `${row.latitude.toFixed(3)}, ${row.longitude.toFixed(3)}`), datasets: [{ label: 'Poor measurement share (%)', data: locationRows.map(row => row.poor_rate * 100), backgroundColor: locationRows.map(row => classColors[row.classification] || '#3788c2'), borderRadius: 6 }] },
            options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: context => `${context.raw.toFixed(1)}%` } } }, scales: { x: { min: 0, max: 100, grid: { color: '#edf1f6' } }, y: { grid: { display: false } } } }
        });
    }

    function addLine(container, text, className = '') {
        const line = document.createElement('div');
        line.className = className;
        line.textContent = text;
        container.appendChild(line);
    }

    function renderMap(locations) {
        markerLayer.clearLayers();
        if (heatLayer && map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
        const heatPoints = [];
        for (const item of locations) {
            const color = classColors[item.classification] || classColors.Good;
            const marker = L.circleMarker([item.latitude, item.longitude], { radius: 8, color, fillColor: color, fillOpacity: .84, weight: 2 });
            const popup = document.createElement('div');
            popup.className = 'measurement-popup';
            addLine(popup, `${item.classification} · approximate cell`);
            addLine(popup, `${item.total} measurements`);
            addLine(popup, `${item.weak_measurements} Weak · ${item.dead_zone_measurements} Dead Zone`);
            addLine(popup, `Average download: ${fmt(item.average_download_mbps)} Mbps`);
            addLine(popup, `Average latency: ${fmt(item.average_latency_ms)} ms`);
            marker.bindPopup(popup).addTo(markerLayer);
            if (item.poor_rate > 0) heatPoints.push([item.latitude, item.longitude, item.poor_rate]);
        }
        if (window.L.heatLayer) {
            heatLayer = L.heatLayer(heatPoints, { radius: 32, blur: 24, maxZoom: 14, max: 1, gradient: { .2: '#f4d35e', .55: '#f08c32', 1: '#d63939' } });
        }
        setDisplayMode(displayMode);
        if (markerLayer.getLayers().length) map.fitBounds(markerLayer.getBounds().pad(.18), { maxZoom: 13 });
    }

    function setDisplayMode(mode) {
        displayMode = mode;
        if (mode === 'heatmap' && heatLayer) {
            if (map.hasLayer(markerLayer)) map.removeLayer(markerLayer);
            heatLayer.addTo(map);
        } else {
            mode = 'markers';
            displayMode = mode;
            if (heatLayer && map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
            if (!map.hasLayer(markerLayer)) markerLayer.addTo(map);
        }
        document.getElementById('adminMarkers').classList.toggle('btn-primary', mode === 'markers');
        document.getElementById('adminMarkers').classList.toggle('btn-outline-primary', mode !== 'markers');
        document.getElementById('adminMarkers').setAttribute('aria-pressed', String(mode === 'markers'));
        document.getElementById('adminHeat').classList.toggle('btn-primary', mode === 'heatmap');
        document.getElementById('adminHeat').classList.toggle('btn-outline-primary', mode !== 'heatmap');
        document.getElementById('adminHeat').setAttribute('aria-pressed', String(mode === 'heatmap'));
    }

    function renderLocationList(containerId, locations, selected) {
        const container = document.getElementById(containerId);
        container.replaceChildren();
        const rows = locations.filter(row => row.classification === selected).slice(0, 12);
        if (!rows.length) {
            addLine(container, 'No qualifying anonymized cells in this filter.', 'admin-empty-line');
            return;
        }
        for (const row of rows) {
            const card = document.createElement('div');
            card.className = 'admin-location-row';
            const heading = document.createElement('strong');
            heading.textContent = `${row.latitude.toFixed(3)}, ${row.longitude.toFixed(3)}`;
            const detail = document.createElement('span');
            detail.textContent = `${row.total} measurements · ${Math.round(row.poor_rate * 100)}% weak/dead · score ${fmt(row.average_score)}`;
            card.append(heading, detail);
            container.appendChild(card);
        }
    }

    function renderPrediction(data) {
        const container = document.getElementById('predictionStats');
        container.replaceChildren();
        const fields = [
            [`Model status`, data.model_ready ? `Trained · ${data.model_name}` : 'Not trained on sufficient representative data'],
            ['Prediction events recorded', fmt(data.total_predictions, 0)],
            ['Predicted poor', fmt(data.poor_predictions, 0)],
            ['Other predictions', fmt(data.other_predictions, 0)],
            ['Held-out balanced accuracy', data.test_metrics?.balanced_accuracy === undefined ? 'Unavailable' : fmt(data.test_metrics.balanced_accuracy, 3)],
            ['Last recorded prediction', data.last_prediction || 'None']
        ];
        for (const [label, value] of fields) {
            const row = document.createElement('div');
            row.className = 'admin-detail-row';
            addLine(row, label);
            addLine(row, value, 'admin-detail-value');
            container.appendChild(row);
        }
    }

    function renderRecommendations(items) {
        const container = document.getElementById('recommendationList');
        container.replaceChildren();
        if (!items.length) {
            addLine(container, 'No recommendation records are available yet.', 'admin-empty-line');
            return;
        }
        for (const item of items) {
            const row = document.createElement('div');
            row.className = `admin-rec-row severity-${String(item.severity).toLowerCase()}`;
            const title = document.createElement('strong');
            title.textContent = item.title;
            const detail = document.createElement('span');
            detail.textContent = `${item.recommendation} · ${item.total} ${item.status} · ${item.severity} · last seen ${item.last_seen || 'unknown'}`;
            row.append(title, detail);
            container.appendChild(row);
        }
    }

    async function loadDashboard() {
        status.textContent = 'Loading filtered aggregates…';
        errorBox.classList.add('d-none');
        try {
            const params = filters();
            const response = await fetch(`${root.dataset.dashboardUrl}?${params}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load the administrator dashboard.');
            renderSummary(data);
            renderCharts(data);
            renderMap(data.locations);
            renderLocationList('weakLocations', data.locations, 'Weak');
            renderLocationList('deadLocations', data.locations, 'Dead Zone');
            renderPrediction(data.prediction_statistics);
            renderRecommendations(data.recommendations);
            const privacy = data.privacy;
            status.textContent = `${fmt(data.summary.total_measurements, 0)} measurements · ${fmt(data.summary.anonymized_location_cells, 0)} location cells shown · minimum ${privacy.minimum_measurements_per_cell} samples per cell`;
            document.getElementById('reportLink').href = `${root.dataset.reportUrl}?${params}`;
        } catch (error) {
            errorBox.textContent = error.message || 'Could not load aggregate analytics.';
            errorBox.classList.remove('d-none');
            status.textContent = 'Dashboard data unavailable';
        }
    }

    form.addEventListener('submit', event => { event.preventDefault(); loadDashboard(); });
    form.addEventListener('reset', () => window.setTimeout(loadDashboard, 0));
    document.getElementById('adminMarkers').addEventListener('click', () => setDisplayMode('markers'));
    document.getElementById('adminHeat').addEventListener('click', () => setDisplayMode('heatmap'));
    document.getElementById('exportButton').addEventListener('click', () => {
        const params = filters();
        params.set('type', document.getElementById('exportType').value);
        window.location.assign(`${root.dataset.exportUrl}?${params}`);
    });
    loadDashboard();
    window.setTimeout(() => map.invalidateSize(), 0);
})();
