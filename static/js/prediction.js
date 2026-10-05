(() => {
    const root = document.getElementById('predictionDashboard');
    const form = document.getElementById('predictionForm');
    if (!root || !form || root.dataset.modelReady !== 'true') return;
    const result = document.getElementById('predictionResult');
    const button = document.getElementById('predictButton');
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const [latitude, longitude] = document.getElementById('predictionLocation').value.split(',').map(Number);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
        button.disabled = true;
        button.textContent = 'Analyzing…';
        result.className = 'prediction-result mt-4';
        result.textContent = 'Checking prior measurements for this location…';
        try {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            const headers = { 'Content-Type': 'application/json', 'Accept': 'application/json' };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken;
            const response = await fetch(root.dataset.apiUrl, {
                method: 'POST', credentials: 'same-origin',
                headers,
                body: JSON.stringify({ latitude, longitude })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Prediction is unavailable.');
            result.innerHTML = '';
            const title = document.createElement('strong');
            title.textContent = data.status;
            const detail = document.createElement('span');
            detail.textContent = `Based on ${data.historical_measurements} earlier measurements at this approximate location. No calibrated confidence is available.`;
            result.append(title, detail);
            result.classList.add(data.poor_connectivity_likely ? 'prediction-poor' : 'prediction-ok');
        } catch (error) {
            result.textContent = error.message || 'Prediction is unavailable.';
            result.classList.add('prediction-error');
        } finally {
            button.disabled = false;
            button.textContent = 'Predict next status';
        }
    });
})();
