const map = L.map('map').setView([45.85, -122.95], 9);

L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
}).addTo(map);

const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

const results = L.layerGroup().addTo(map);

const drawControl = new L.Control.Draw({
    edit: { featureGroup: drawnItems },
    draw: { polygon: true, polyline: false, marker: false, circle: false, rectangle: false, circlemarker: false }
});
map.addControl(drawControl);

let currentShape = null;

map.on(L.Draw.Event.CREATED, function (e) {
    drawnItems.clearLayers();
    drawnItems.addLayer(e.layer);
    currentShape = e.layer;
    runSearch();
});

map.on(L.Draw.Event.EDITED, runSearch);

map.on(L.Draw.Event.DELETED, function () {
    currentShape = null;
    results.clearLayers();
    setStatus('Draw a shape to search inside it.');
});

function setStatus(text) {
    document.getElementById('status').textContent = text;
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

const SOURCE_LABELS = { usajobs: 'USAJOBS', lever: 'Lever', direct: 'Posted directly' };

function groupByPoint(jobs) {
    const groups = new Map();
    for (const job of jobs) {
        for (const location of job.locations) {
            const key = `${location.latitude},${location.longitude}`;
            if (!groups.has(key)) {
                groups.set(key, { location, jobs: [] });
            }
            groups.get(key).jobs.push(job);
        }
    }
    return [...groups.values()];
}

function popupHtml(group) {
    const place = escapeHtml(group.location.raw_location || 'Unknown location');
    const precision = group.location.precision === 'exact'
        ? 'exact address'
        : `${group.location.precision}-level location`;

    const items = group.jobs.map(job => `
        <li>
            <a href="${escapeHtml(job.url)}" target="_blank" rel="noopener">${escapeHtml(job.title)}</a>
            <span class="employer">${escapeHtml(job.employer || '')}</span>
            <span class="source">via ${escapeHtml(SOURCE_LABELS[job.source] || job.source)}</span>
        </li>
    `).join('');

    return `
        <div class="popup">
            <h3>${place}</h3>
            <p class="precision">${group.jobs.length} job${group.jobs.length === 1 ? '' : 's'} &middot; ${precision}</p>
            <ul>${items}</ul>
        </div>
    `;
}

function markerFor(group) {
    const count = group.jobs.length;
    const icon = L.divIcon({
        className: 'job-marker',
        html: `<span>${count}</span>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14]
    });
    return L.marker([group.location.latitude, group.location.longitude], { icon })
        .bindPopup(popupHtml(group), { maxHeight: 320 });
}

async function runSearch() {
    if (!currentShape) {
        setStatus('Draw a shape first.');
        return;
    }

    const button = document.getElementById('search-button');
    button.disabled = true;
    setStatus('Searching…');

    try {
        const polygon = currentShape.getLatLngs()[0].map(p => [p.lng, p.lat]);
        const what = document.getElementById('job-input').value;

        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ polygon, what })
        });

        if (!response.ok) {
            setStatus(`Search failed (${response.status}).`);
            return;
        }

        const jobs = await response.json();
        results.clearLayers();

        if (!jobs.length) {
            setStatus('No jobs in that shape. Try a wider area or clear the keyword.');
            return;
        }

        const groups = groupByPoint(jobs);
        for (const group of groups) {
            markerFor(group).addTo(results);
        }

        const places = groups.length === 1 ? '1 place' : `${groups.length} places`;
        setStatus(`${jobs.length} jobs across ${places}.`);
    } catch (error) {
        setStatus('Search failed. Is the server running?');
    } finally {
        button.disabled = false;
    }
}

document.getElementById('search-button').addEventListener('click', runSearch);
document.getElementById('job-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') runSearch();
});

fetch('/api/health')
    .then(r => r.json())
    .then(data => {
        document.getElementById('freshness').textContent =
            `${data.live_jobs} jobs indexed`;
    })
    .catch(() => {});
