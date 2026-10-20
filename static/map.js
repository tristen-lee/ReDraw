const map = L.map('map', { zoomControl: false }).setView([45.85, -122.95], 9);

L.control.zoom({ position: 'bottomright' }).addTo(map);

L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
}).addTo(map);

const results = L.layerGroup().addTo(map);
const container = map.getContainer();

const BRAND = getComputedStyle(document.documentElement)
    .getPropertyValue('--brand').trim() || '#197082';

const SIMPLIFY_TOLERANCE = 6;
const MIN_POINTS = 8;

let drawMode = false;
let drawing = false;
let trace = [];
let traceLine = null;
let shape = null;

function setStatus(text) {
    document.getElementById('status').textContent = text;
}

function setDrawMode(on) {
    drawMode = on;
    container.classList.toggle('drawing', on);
    document.getElementById('draw-button').textContent = on ? 'Cancel' : 'Draw your area';
    if (on) {
        map.dragging.disable();
        map.doubleClickZoom.disable();
        setStatus('Drag across the map to outline where you would work.');
    } else {
        map.dragging.enable();
        map.doubleClickZoom.enable();
    }
}

function simplify(latlngs) {
    const points = latlngs.map(ll => map.latLngToLayerPoint(ll));
    return L.LineUtil.simplify(points, SIMPLIFY_TOLERANCE).map(p => map.layerPointToLatLng(p));
}

function beginTrace(event) {
    if (!drawMode || event.button === 2) return;
    drawing = true;
    trace = [map.mouseEventToLatLng(event)];
    if (traceLine) map.removeLayer(traceLine);
    traceLine = L.polyline(trace, { color: BRAND, weight: 3, dashArray: '4 4' }).addTo(map);
    container.setPointerCapture?.(event.pointerId);
}

function extendTrace(event) {
    if (!drawing) return;
    event.preventDefault();
    trace.push(map.mouseEventToLatLng(event));
    traceLine.setLatLngs(trace);
}

function endTrace() {
    if (!drawing) return;
    drawing = false;

    if (traceLine) {
        map.removeLayer(traceLine);
        traceLine = null;
    }

    if (trace.length < MIN_POINTS) {
        setStatus('That was too short to be an area — drag a longer outline.');
        return;
    }

    const simplified = simplify(trace);
    if (shape) map.removeLayer(shape);
    shape = L.polygon(simplified, {
        color: BRAND,
        weight: 2,
        fillOpacity: 0.07
    }).addTo(map);

    setDrawMode(false);
    runSearch();
}

container.addEventListener('pointerdown', beginTrace);
container.addEventListener('pointermove', extendTrace, { passive: false });
container.addEventListener('pointerup', endTrace);
container.addEventListener('pointercancel', endTrace);

document.getElementById('draw-button').addEventListener('click', () => setDrawMode(!drawMode));

document.getElementById('clear-button').addEventListener('click', () => {
    if (shape) map.removeLayer(shape);
    shape = null;
    results.clearLayers();
    setDrawMode(false);
    setStatus('Draw an area to search inside it.');
});

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
            if (!groups.has(key)) groups.set(key, { location, jobs: [] });
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
            <a href="${escapeHtml(job.path)}">${escapeHtml(job.title)}</a>
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
    const icon = L.divIcon({
        className: 'job-marker',
        html: `<span>${group.jobs.length}</span>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14]
    });
    return L.marker([group.location.latitude, group.location.longitude], { icon })
        .bindPopup(popupHtml(group), { maxHeight: 320 });
}

async function runSearch() {
    if (!shape) {
        setStatus('Draw an area first.');
        return;
    }

    setStatus('Searching…');

    try {
        const polygon = shape.getLatLngs()[0].map(p => [p.lng, p.lat]);
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
            setStatus('No jobs in that area. Try a wider outline or clear the keyword.');
            return;
        }

        const groups = groupByPoint(jobs);
        groups.forEach(group => markerFor(group).addTo(results));

        const places = groups.length === 1 ? '1 place' : `${groups.length} places`;
        setStatus(`${jobs.length} jobs across ${places}.`);
    } catch {
        setStatus('Search failed. Check your connection and try again.');
    }
}

document.getElementById('search-button').addEventListener('click', runSearch);
document.getElementById('job-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') runSearch();
});

fetch('/api/health')
    .then(r => r.json())
    .then(data => {
        document.getElementById('freshness').textContent = `${data.mappable_jobs} jobs on the map`;
    })
    .catch(() => {});
