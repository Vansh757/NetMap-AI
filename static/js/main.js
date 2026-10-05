document.addEventListener('DOMContentLoaded', () => {
    function createOsmMap(element, center = [20.5937, 78.9629], zoom = 5) {
        const map = L.map(element).setView(center, zoom);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);
        return map;
    }

    const mapElement = document.getElementById('map');
    if (mapElement && window.L) createOsmMap(mapElement);

    initializeMeasurementMap(createOsmMap);

    const app = document.getElementById('measurement-app');
    if (!app) return;

    const button = document.getElementById('run-test');
    const progressPanel = document.getElementById('test-progress');
    const progressBar = document.getElementById('progress-bar');
    const progressTrack = progressBar.parentElement;
    const progressLabel = document.getElementById('progress-label');
    const progressPercent = document.getElementById('progress-percent');
    const errorBox = document.getElementById('test-error');
    const results = document.getElementById('measurement-results');
    const mib = 1024 * 1024;
    const chosenLocation = { latitude: null, longitude: null, accuracy: null };
    const locationStatus = document.getElementById('location-status');
    const clearLocationButton = document.getElementById('clear-location');
    let pickerMap = null;
    let selectedMarker = null;

    function setChosenLocation(latitude, longitude, accuracy = null, source = 'manual map selection') {
        chosenLocation.latitude = latitude;
        chosenLocation.longitude = longitude;
        chosenLocation.accuracy = accuracy;
        const accuracyText = accuracy === null ? 'Accuracy not available for a manual selection.' : `Reported accuracy: about ${Math.round(accuracy)} m.`;
        locationStatus.textContent = `Location selected by ${source} (${latitude.toFixed(5)}, ${longitude.toFixed(5)}). ${accuracyText}`;
        clearLocationButton.hidden = false;
        if (pickerMap) {
            const point = [latitude, longitude];
            if (!selectedMarker) selectedMarker = L.marker(point).addTo(pickerMap);
            else selectedMarker.setLatLng(point);
            pickerMap.setView(point, Math.max(pickerMap.getZoom(), 13));
        }
    }

    function clearChosenLocation() {
        chosenLocation.latitude = null;
        chosenLocation.longitude = null;
        chosenLocation.accuracy = null;
        locationStatus.textContent = 'No location selected. The test can be saved without coordinates.';
        clearLocationButton.hidden = true;
        if (selectedMarker && pickerMap) pickerMap.removeLayer(selectedMarker);
        selectedMarker = null;
    }

    
    const useCurrentLocationButton = document.getElementById('use-current-location');

if (useCurrentLocationButton) {
    useCurrentLocationButton.addEventListener('click', () => {
        if (!navigator.geolocation) {
            locationStatus.textContent = 'This browser does not support location. You can choose a point manually on the map.';
            return;
        }
        locationStatus.textContent = 'Requesting location permission from your browser...';
        navigator.geolocation.getCurrentPosition(
            position => setChosenLocation(
                position.coords.latitude,
                position.coords.longitude,
                position.coords.accuracy,
                'browser location'
            ),
            error => {
                const message = error.code === error.PERMISSION_DENIED
                    ? 'Location permission was denied. You can choose a point manually or continue without location.'
                    : error.code === error.TIMEOUT
                        ? 'Location request timed out. Try again or choose a point manually.'
                        : 'Location is unavailable. You can choose a point manually or continue without location.';
                locationStatus.textContent = message;
            },
                        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
        );
    });
}

if (clearLocationButton) {
    clearLocationButton.addEventListener('click', clearChosenLocation);
}
    const locationMapDetails = document.querySelector('#location-picker-map')?.closest('details');
    if (locationMapDetails) {
        locationMapDetails.addEventListener('toggle', () => {
            if (!locationMapDetails.open || pickerMap) return;
            pickerMap = createOsmMap(document.getElementById('location-picker-map'));
            pickerMap.on('click', event => {
                setChosenLocation(event.latlng.lat, event.latlng.lng, null, 'manual map selection');
            });
            if (chosenLocation.latitude !== null) {
                const point = [chosenLocation.latitude, chosenLocation.longitude];
                selectedMarker = L.marker(point).addTo(pickerMap);
                pickerMap.setView(point, 13);
            }
            window.setTimeout(() => pickerMap.invalidateSize(), 0);
        });
    }

    function setProgress(percent, label) {
        const value = Math.max(0, Math.min(100, Math.round(percent)));
        progressBar.style.width = `${value}%`;
        progressTrack.setAttribute('aria-valuenow', String(value));
        progressPercent.textContent = `${value}%`;
        progressLabel.textContent = label;
    }

    function showValue(id, value, unit) {
        document.getElementById(id).textContent = value === null ? 'Unavailable' : `${value.toFixed(2)} ${unit}`;
    }

    async function timedProbe() {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 8000);
        const started = performance.now();
        try {
            const response = await fetch(app.dataset.pingUrl, {
                cache: 'no-store',
                credentials: 'same-origin',
                signal: controller.signal
            });
            if (!response.ok) throw new Error(`Probe returned ${response.status}`);
            await response.arrayBuffer();
            return performance.now() - started;
        } finally {
            window.clearTimeout(timeout);
        }
    }

    async function measureDownload() {
        const bytesRequested = 4 * mib;
        const url = `${app.dataset.downloadUrl}?bytes=${bytesRequested}&t=${Date.now()}`;
        const started = performance.now();
        const response = await fetch(url, { cache: 'no-store', credentials: 'same-origin' });
        if (!response.ok) throw new Error(`Download probe returned ${response.status}`);

        let received = 0;
        if (response.body && response.body.getReader) {
            const reader = response.body.getReader();
            while (true) {
                const part = await reader.read();
                if (part.done) break;
                received += part.value.byteLength;
                setProgress(36 + 24 * Math.min(received / bytesRequested, 1), 'Measuring download speed...');
            }
        } else {
            const body = await response.arrayBuffer();
            received = body.byteLength;
        }
        const elapsedSeconds = (performance.now() - started) / 1000;
        if (!received || elapsedSeconds <= 0) throw new Error('The download probe returned no data.');
        return (received * 8) / elapsedSeconds / 1_000_000;
    }

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    function measureUpload() {
        const byteCount = 1 * mib;
        const payload = new Uint8Array(byteCount);
        for (let offset = 0; offset < byteCount; offset += 65536) {
            crypto.getRandomValues(payload.subarray(offset, Math.min(offset + 65536, byteCount)));
        }

        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const started = performance.now();
         
            xhr.open('POST', app.dataset.uploadUrl);
            xhr.setRequestHeader('Content-Type', 'application/octet-stream');
            const csrfToken = getCsrfToken();
            if (csrfToken) xhr.setRequestHeader('X-CSRFToken', csrfToken);
            xhr.timeout = 20000;
            xhr.upload.addEventListener('progress', event => {
                if (event.lengthComputable) {
                    setProgress(60 + 22 * Math.min(event.loaded / event.total, 1), 'Measuring upload speed...');
                }
            });
            xhr.addEventListener('load', () => {
                if (xhr.status < 200 || xhr.status >= 300) {
                    reject(new Error(`Upload probe returned ${xhr.status}.`));
                    return;
                }
                const elapsedSeconds = (performance.now() - started) / 1000;
                if (elapsedSeconds <= 0) {
                    reject(new Error('Upload timing was unavailable.'));
                    return;
                }
                resolve((byteCount * 8) / elapsedSeconds / 1_000_000);
            });
            xhr.addEventListener('error', () => reject(new Error('The upload probe could not reach this server.')));
            xhr.addEventListener('timeout', () => reject(new Error('The upload probe timed out.')));
            xhr.send(payload);
        });
    }

    function browserNetworkInfo() {
        const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        const info = { online: navigator.onLine };
        if (connection) {
            if (typeof connection.effectiveType === 'string') info.effectiveType = connection.effectiveType;
            if (typeof connection.type === 'string') info.type = connection.type;
            if (Number.isFinite(connection.downlink)) info.downlink = connection.downlink;
            if (Number.isFinite(connection.rtt)) info.rtt = connection.rtt;
            if (typeof connection.saveData === 'boolean') info.saveData = connection.saveData;
        }
        return info;
    }

    function renderNetworkInfo(info) {
        const labels = {
            effectiveType: 'Browser connection type estimate',
            type: 'Browser-reported network type',
            downlink: 'Browser downlink estimate',
            rtt: 'Browser RTT estimate',
            saveData: 'Data saver enabled',
            online: 'Browser reports online'
        };
        const units = { downlink: ' Mbps', rtt: ' ms' };
        const details = document.getElementById('network-details');
        details.replaceChildren();
        for (const [key, label] of Object.entries(labels)) {
            const term = document.createElement('dt');
            const value = document.createElement('dd');
            term.textContent = label;
            value.textContent = Object.prototype.hasOwnProperty.call(info, key)
                ? `${info[key]}${units[key] || ''}`
                : 'Unavailable in this browser';
            details.append(term, value);
        }
    }

    async function runTest() {
        button.disabled = true;
        progressPanel.hidden = false;
        results.hidden = true;
        errorBox.textContent = '';
        document.getElementById('saved-status').textContent = '';

        try {
            const samples = [];
            let failures = 0;
            for (let index = 0; index < 8; index += 1) {
                setProgress(5 + (index / 8) * 29, `Measuring HTTP latency... probe ${index + 1} of 8`);
                try {
                    samples.push(await timedProbe());
                } catch (error) {
                    failures += 1;
                }
            }
            if (!samples.length) throw new Error('No latency probes succeeded. Check your connection and try again.');
            const ping = samples.reduce((sum, value) => sum + value, 0) / samples.length;
            const jitter = samples.length > 1
                ? samples.slice(1).reduce((sum, value, index) => sum + Math.abs(value - samples[index]), 0) / (samples.length - 1)
                : null;

            setProgress(36, 'Preparing download test...');
            const download = await measureDownload();
            setProgress(60, 'Preparing upload test...');
            const upload = await measureUpload();
            const browserNetwork = browserNetworkInfo();

            setProgress(88, 'Saving your measurement...');
            const csrfToken = getCsrfToken();
            const headers = { 'Content-Type': 'application/json' };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken;
            const response = await fetch(app.dataset.saveUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers,
                body: JSON.stringify({
                    download_mbps: download,
                    upload_mbps: upload,
                    ping_ms: ping,
                    jitter_ms: jitter,
                    browser_network: browserNetwork,
                    latitude: chosenLocation.latitude,
                    longitude: chosenLocation.longitude,
                    location_accuracy_m: chosenLocation.accuracy
                })
            });
            const saved = await response.json();
            if (!response.ok) throw new Error(saved.error || 'Could not save this measurement.');

            showValue('result-download', download, 'Mbps');
            showValue('result-upload', upload, 'Mbps');
            showValue('result-ping', ping, 'ms');
            showValue('result-jitter', jitter, 'ms');
            renderNetworkInfo(browserNetwork);
            document.getElementById('result-timestamp').textContent = `${saved.created_at} (server time)`;
            document.getElementById('result-id').textContent = saved.id;
           const score = Number(saved.connectivity_score);
document.getElementById('result-score').textContent =
    Number.isFinite(score) ? `${score.toFixed(1)} / 100` : 'Unavailable';
            document.getElementById('result-classification').textContent = saved.connectivity_classification;
            document.getElementById('result-classification').className = `classification-text ${saved.connectivity_classification.toLowerCase().replaceAll(' ', '-')}`;
            const hasLocation =
    Number.isFinite(Number(saved.latitude)) &&
    Number.isFinite(Number(saved.longitude));

const resultLocation = document.getElementById('result-location');

if (resultLocation) {
    resultLocation.textContent = !hasLocation
        ? 'Not attached'
        : `${Number(saved.latitude).toFixed(5)}, ${Number(saved.longitude).toFixed(5)}${
            Number.isFinite(Number(saved.location_accuracy_m))
                ? ` (±${Math.round(Number(saved.location_accuracy_m))} m)`
                : ' (accuracy unavailable)'
          }`;
}
            document.getElementById('saved-status').textContent = 'Saved to your measurement history';
            results.hidden = false;
            setProgress(100, failures ? `Complete (${failures} HTTP probe(s) failed)` : 'Test complete');
        } catch (error) {
            console.error(error);
            errorBox.textContent = error.message || 'The test could not be completed.';
            progressLabel.textContent = 'Test stopped';
        } finally {
            button.disabled = false;
        }
    }

    button.addEventListener('click', runTest);
});

function initializeMeasurementMap(createOsmMap) {
    const app = document.getElementById('measurement-map-app');
    const element = document.getElementById('measurement-map');
    if (!app || !element || !window.L) return;

    const map = createOsmMap(element, [20, 0], 2);
    const markerLayer = L.featureGroup().addTo(map);
    const count = document.getElementById('map-result-count');
    const errorBox = document.getElementById('map-error');
    const colors = {
        Excellent: '#16845b',
        Good: '#3788c2',
        Weak: '#e5a51b',
        'Dead Zone': '#d94b50'
    };
    let heatLayer = null;
    let displayMode = 'markers';
    let trendChart = null;
    let classificationChart = null;

    function addPopupLine(container, label, value) {
        const line = document.createElement('div');
        const strong = document.createElement('strong');
        strong.textContent = `${label}: `;
        line.append(strong, document.createTextNode(value));
        container.append(line);
    }

    function updateCharts(data) {
        if (!window.Chart) return;
        const labels = data.timeline.map(row => row.day);
        const trend = {
            labels,
            datasets: [
                {
                    label: 'Average download (Mbps)',
                    data: data.timeline.map(row => row.average_download_mbps),
                    borderColor: '#2878d0',
                    backgroundColor: '#2878d022',
                    yAxisID: 'y',
                    tension: 0.3
                },
                {
                    label: 'Average HTTP latency (ms)',
                    data: data.timeline.map(row => row.average_ping_ms),
                    borderColor: '#e49a1c',
                    backgroundColor: '#e49a1c22',
                    yAxisID: 'y1',
                    tension: 0.3
                }
            ]
        };
        if (!trendChart) {
            trendChart = new Chart(document.getElementById('trend-chart'), {
                type: 'line',
                data: trend,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { type: 'linear', position: 'left', title: { display: true, text: 'Mbps' } },
                        y1: { type: 'linear', position: 'right', title: { display: true, text: 'ms' }, grid: { drawOnChartArea: false } }
                    }
                }
            });
        } else {
            trendChart.data = trend;
            trendChart.update();
        }

        const classNames = ['Excellent', 'Good', 'Weak', 'Dead Zone'];
        const classificationData = {
            labels: classNames,
            datasets: [{
                data: classNames.map(name => data.classification_counts[name] || 0),
                backgroundColor: classNames.map(name => colors[name]),
                borderWidth: 0
            }]
        };
        if (!classificationChart) {
            classificationChart = new Chart(document.getElementById('classification-chart'), {
                type: 'doughnut',
                data: classificationData,
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
            });
        } else {
            classificationChart.data = classificationData;
            classificationChart.update();
        }
    }

    function updateStats(stats) {
        const formatted = value => value === null ? '—' : Number(value).toFixed(2);
        document.getElementById('stat-total').textContent = stats.total_measurements;
        document.getElementById('stat-download').textContent = formatted(stats.average_download_mbps);
        document.getElementById('stat-upload').textContent = formatted(stats.average_upload_mbps);
        document.getElementById('stat-latency').textContent = formatted(stats.average_ping_ms);
        document.getElementById('stat-weak').textContent = stats.weak_locations;
        document.getElementById('stat-dead').textContent = stats.dead_zone_measurements;
    }

    function setDisplayMode(mode) {
        displayMode = mode;
        if (mode === 'heatmap') {
            if (!window.L.heatLayer) {
                errorBox.textContent = 'The heatmap library did not load. Classified markers are still available.';
                return;
            }
            if (map.hasLayer(markerLayer)) map.removeLayer(markerLayer);
            if (heatLayer && !map.hasLayer(heatLayer)) heatLayer.addTo(map);
        } else {
            if (heatLayer && map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
            if (!map.hasLayer(markerLayer)) markerLayer.addTo(map);
        }
        document.getElementById('show-markers').classList.toggle('btn-primary', mode === 'markers');
        document.getElementById('show-markers').classList.toggle('btn-outline-primary', mode !== 'markers');
        document.getElementById('show-markers').setAttribute('aria-pressed', String(mode === 'markers'));
        document.getElementById('show-heatmap').classList.toggle('btn-primary', mode === 'heatmap');
        document.getElementById('show-heatmap').classList.toggle('btn-outline-primary', mode !== 'heatmap');
        document.getElementById('show-heatmap').setAttribute('aria-pressed', String(mode === 'heatmap'));
    }

    async function loadMeasurements() {
        const parameters = new URLSearchParams();
        const start = document.getElementById('map-start-date').value;
        const end = document.getElementById('map-end-date').value;
        const classification = document.getElementById('map-classification').value;
        if (start) parameters.set('start_date', start);
        if (end) parameters.set('end_date', end);
        if (classification) parameters.set('classification', classification);

        count.textContent = 'Loading your measurements...';
        errorBox.textContent = '';
        try {
            const response = await fetch(`${app.dataset.measurementsUrl}?${parameters}`, {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' }
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Could not load measurements.');

            markerLayer.clearLayers();
            const weakPoints = [];
            let skippedUnscored = 0;
            for (const item of result.measurements) {
                if (!Number.isFinite(item.score) || !item.classification) {
                    skippedUnscored += 1;
                    continue;
                }
                const color = colors[item.classification] || '#64748b';
                const marker = L.circleMarker([item.latitude, item.longitude], {
                    radius: 9,
                    color,
                    fillColor: color,
                    fillOpacity: 0.88,
                    weight: 2
                });
                const popup = document.createElement('div');
                popup.className = 'measurement-popup';
                const heading = document.createElement('strong');
                heading.textContent = `${item.classification} connectivity · score ${item.score.toFixed(1)}/100`;
                popup.append(heading);
                addPopupLine(popup, 'Download', `${item.download_mbps.toFixed(2)} Mbps`);
                addPopupLine(popup, 'Upload', `${item.upload_mbps.toFixed(2)} Mbps`);
                addPopupLine(popup, 'HTTP latency', `${item.ping_ms.toFixed(2)} ms`);
                addPopupLine(popup, 'Date/time', `${item.created_at} (server time)`);
                marker.bindPopup(popup).addTo(markerLayer);
                if (item.classification === 'Weak' || item.classification === 'Dead Zone') {
                    weakPoints.push([item.latitude, item.longitude, Math.max(0.12, (100 - item.score) / 100)]);
                }
            }

            if (window.L.heatLayer) {
                if (heatLayer && map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
                heatLayer = L.heatLayer(weakPoints, {
                    radius: 30,
                    blur: 22,
                    maxZoom: 14,
                    max: 1,
                    gradient: { 0.2: '#f4d35e', 0.55: '#f08c32', 1: '#d63939' }
                });
            }
            if (displayMode === 'heatmap') setDisplayMode('heatmap');
            else setDisplayMode('markers');

            const markers = markerLayer.getLayers();
            count.textContent = `${markers.length} of ${result.stats.total_measurements} filtered measurement(s) have locations`;
            if (!weakPoints.length) count.textContent += '; no Weak or Dead Zone points are in this filter, so the poor-area heatmap is empty';
            if (skippedUnscored) count.textContent += `; ${skippedUnscored} older measurement(s) still need scoring`;
            if (markers.length) map.fitBounds(markerLayer.getBounds().pad(0.18), { maxZoom: 13 });
            updateStats(result.stats);
            updateCharts(result);
        } catch (error) {
            count.textContent = 'Measurements unavailable';
            errorBox.textContent = error.message || 'Could not load measurements.';
        }
    }

    document.getElementById('apply-map-filters').addEventListener('click', loadMeasurements);
    document.getElementById('reset-map-filters').addEventListener('click', () => {
        document.getElementById('map-start-date').value = '';
        document.getElementById('map-end-date').value = '';
        document.getElementById('map-classification').value = '';
        loadMeasurements();
    });
    document.getElementById('show-markers').addEventListener('click', () => setDisplayMode('markers'));
    document.getElementById('show-heatmap').addEventListener('click', () => setDisplayMode('heatmap'));
    loadMeasurements();
    window.setTimeout(() => map.invalidateSize(), 0);
}
