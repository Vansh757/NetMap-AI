(() => {
    const root = document.getElementById('analyticsDashboard');
    if (!root || typeof Chart === 'undefined') return;

    const form = document.getElementById('analyticsFilters');
    const status = document.getElementById('analyticsStatus');
    const errorBox = document.getElementById('analyticsError');
    const apiUrl = root.dataset.apiUrl;
    const charts = {};
    const classOrder = ['Excellent', 'Good', 'Weak', 'Dead Zone'];
    const classColors = ['#16845b', '#3788c2', '#e5a51b', '#d94b50'];
    const number = (value, digits = 2) => value === null || value === undefined || !Number.isFinite(Number(value))
        ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
    const display = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };

    Chart.defaults.font.family = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif';
    Chart.defaults.color = '#718096';
    Chart.defaults.plugins.legend.labels.usePointStyle = true;

    function buildChart(id, config) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        if (charts[id]) charts[id].destroy();
        charts[id] = new Chart(canvas, config);
    }

    function updateSummary(data) {
        const s = data.summary;
        display('statTotal', number(s.total_measurements, 0));
        display('statDownload', number(s.average_download_mbps));
        display('statUpload', number(s.average_upload_mbps));
        display('statLatency', number(s.average_latency_ms));
        display('statScore', number(s.average_score));
        display('statGood', number(s.good_locations, 0));
        display('statWeak', number(s.weak_locations, 0));
        display('statDead', number(s.dead_zone_measurements, 0));

        for (const [prefix, place] of [['best', data.best_location], ['worst', data.worst_location]]) {
            display(`${prefix}Location`, place ? place.label : 'No location data');
            display(`${prefix}LocationDetail`, place
                ? `Score ${number(place.average_score)} · ${number(place.average_download_mbps)} Mbps down · ${number(place.total, 0)} tests`
                : 'Requires saved coordinates and a calculated score.');
        }
        const c = data.comparison;
        display('comparisonCaption', `${c.current_label} vs ${c.previous_label}`);
        display('comparisonNote', `Tests ${number(c.current.total_measurements, 0)} vs ${number(c.previous.total_measurements, 0)} · Download ${number(c.current.average_download_mbps)} vs ${number(c.previous.average_download_mbps)} Mbps · Upload ${number(c.current.average_upload_mbps)} vs ${number(c.previous.average_upload_mbps)} Mbps · Latency ${number(c.current.average_latency_ms)} vs ${number(c.previous.average_latency_ms)} ms`);
    }

    function updateCharts(data) {
        buildChart('trendChart', {
            type: 'line',
            data: { labels: data.trend.map(x => x.day), datasets: [
                { label: 'Score', data: data.trend.map(x => x.average_score), borderColor: '#2869cf', backgroundColor: '#2869cf1a', yAxisID: 'score', tension: .3, fill: true, pointRadius: 2, spanGaps: true },
                { label: 'Download Mbps', data: data.trend.map(x => x.average_download_mbps), borderColor: '#13a581', yAxisID: 'speed', tension: .3, pointRadius: 2, spanGaps: true },
                { label: 'Upload Mbps', data: data.trend.map(x => x.average_upload_mbps), borderColor: '#e0a52d', yAxisID: 'speed', tension: .3, pointRadius: 2, spanGaps: true }
            ]},
            options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'bottom' } }, scales: {
                score: { type: 'linear', position: 'left', min: 0, max: 100, title: { display: true, text: 'Score' }, grid: { color: '#edf1f6' } },
                speed: { type: 'linear', position: 'right', beginAtZero: true, title: { display: true, text: 'Mbps' }, grid: { drawOnChartArea: false } }
            }}
        });
        const classes = data.classifications || {};
        buildChart('classificationChart', { type: 'doughnut', data: { labels: classOrder, datasets: [{ data: classOrder.map(k => classes[k] || 0), backgroundColor: classColors, borderWidth: 0, hoverOffset: 5 }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '66%', plugins: { legend: { position: 'bottom' } } } });
        const barOptions = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { min: 0, max: 100, grid: { color: '#edf1f6' } }, x: { grid: { display: false } } } };
        buildChart('timeChart', { type: 'bar', data: { labels: data.by_time_of_day.map(x => x.period), datasets: [{ label: 'Average score', data: data.by_time_of_day.map(x => x.average_score), backgroundColor: '#5591e7', borderRadius: 7 }] }, options: barOptions });
        buildChart('weekdayChart', { type: 'bar', data: { labels: data.by_weekday.map(x => x.day), datasets: [{ label: 'Average score', data: data.by_weekday.map(x => x.average_score), backgroundColor: '#54b89c', borderRadius: 7 }] }, options: barOptions });
        const locations = data.locations || [];
        buildChart('locationChart', { type: 'bar', data: { labels: locations.map(x => x.label), datasets: [{ label: 'Average score', data: locations.map(x => x.average_score), backgroundColor: locations.map(x => Number(x.average_score) < 40 ? '#d94b50' : Number(x.average_score) < 65 ? '#e5a51b' : '#3788c2'), borderRadius: 6 }] }, options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { min: 0, max: 100, grid: { color: '#edf1f6' } }, y: { grid: { display: false } } } } });
        const cmp = data.comparison;
        buildChart('comparisonChart', { type: 'bar', data: { labels: ['Connectivity score'], datasets: [
            { label: `Current · ${cmp.current_label}`, data: [cmp.current.average_score], backgroundColor: '#2869cf', borderRadius: 6 },
            { label: `Previous · ${cmp.previous_label}`, data: [cmp.previous.average_score], backgroundColor: '#aab9cc', borderRadius: 6 }
        ] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { y: { min: 0, max: 100, grid: { color: '#edf1f6' } }, x: { grid: { display: false } } } } });
    }

    async function loadAnalytics() {
        errorBox.classList.add('d-none');
        status.textContent = 'Updating…';
        const params = new URLSearchParams(new FormData(form));
        for (const [key, value] of [...params.entries()]) if (!value) params.delete(key);
        try {
            const response = await fetch(`${apiUrl}?${params.toString()}`, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load analytics.');
            updateSummary(data);
            updateCharts(data);
            status.textContent = `${number(data.summary.total_measurements, 0)} measurements included`;
        } catch (error) {
            errorBox.textContent = error.message || 'Could not load analytics. Please try again.';
            errorBox.classList.remove('d-none');
            status.textContent = 'Data unavailable';
        }
    }

    form.addEventListener('submit', event => { event.preventDefault(); loadAnalytics(); });
    form.addEventListener('reset', () => window.setTimeout(() => {
        document.getElementById('filterStart').value = root.dataset.defaultStart;
        document.getElementById('filterEnd').value = root.dataset.defaultEnd;
        loadAnalytics();
    }, 0));
    loadAnalytics();
})();
