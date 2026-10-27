const style = getComputedStyle(document.documentElement);
const cssVar = name => style.getPropertyValue(name).trim();

const MIN_STEP_PX = 6;
const SIMPLIFY_PX = 4;
const MIN_POINTS = 8;
const PAGE_SIZE = 20;
const PHONE = window.matchMedia('(max-width: 760px)');

const SOURCE_LABELS = { usajobs: 'USAJOBS', direct: 'Posted directly' };
const PAY_UNITS = { PA: 'a year', PH: 'an hour', PD: 'a day', PW: 'a week', BW: 'every two weeks', PM: 'a month' };

// The map's own palette: warm paper land, sage woods, a muted river.
// Overrides Protomaps' "light" flavor; anything not listed keeps its default.
function cabinFlavor() {
    const road = '#F6F0E3';
    const casing = '#D3C6AA';
    return {
        ...basemaps.namedFlavor('light'),
        background: '#E9E2D2', earth: '#ECE5D5',
        park_a: '#D7DCC4', park_b: '#C9D3B3', wood_a: '#D5DBC2', wood_b: '#C3CFAC',
        scrub_a: '#DCDFC9', scrub_b: '#CBD3B6', zoo: '#D5DCC4', glacier: '#F2EEE6',
        sand: '#E6DDC6', beach: '#E8DFC8', hospital: '#E6DCCF', school: '#E5DDCC',
        industrial: '#DED8CB', military: '#DCD6C8', aerodrome: '#DED8CB', runway: '#E8E2D5',
        pedestrian: '#E6DFCF', pier: '#E0D8C8', buildings: '#DCD3C2', water: '#AFC6CB',
        highway: road, major: road, link: road, minor_a: '#F2ECDF', minor_b: '#F4EEE2',
        minor_service: '#EEE7D9', other: '#EEE7D9',
        highway_casing_early: casing, highway_casing_late: casing,
        major_casing_early: casing, major_casing_late: casing,
        link_casing: casing, minor_casing: '#DBD0B9', minor_service_casing: '#DBD0B9',
        bridges_highway: road, bridges_major: road, bridges_link: road, bridges_minor: road, bridges_other: '#EEE7D9',
        bridges_highway_casing: casing, bridges_major_casing: casing, bridges_link_casing: casing,
        bridges_minor_casing: casing, bridges_other_casing: casing,
        tunnel_highway: '#E4DCCB', tunnel_major: '#E4DCCB', tunnel_link: '#E4DCCB',
        tunnel_minor: '#E4DCCB', tunnel_other: '#E4DCCB',
        railway: '#B5AC9B', boundaries: '#B3A68D',
        city_label: '#4A4237', city_label_halo: '#ECE5D5',
        subplace_label: '#7A7062', subplace_label_halo: '#ECE5D5',
        state_label: '#9C9182', state_label_halo: '#ECE5D5', country_label: '#8E8474',
        roads_label_major: '#7D7262', roads_label_major_halo: road,
        roads_label_minor: '#857A69', roads_label_minor_halo: road,
        address_label: '#857A69', address_label_halo: road, ocean_label: '#6E8C94',
    };
}

const GLYPHS = 'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf';

function mapStyle(tilesUrl) {
    if (!tilesUrl) {
        return {
            version: 8,
            glyphs: GLYPHS,
            sources: {
                osm: {
                    type: 'raster',
                    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
                    tileSize: 256,
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                },
            },
            layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
        };
    }
    return {
        version: 8,
        glyphs: GLYPHS,
        sprite: 'https://protomaps.github.io/basemaps-assets/sprites/v4/light',
        sources: {
            protomaps: {
                type: 'vector',
                url: `pmtiles://${tilesUrl}`,
                attribution: '<a href="https://protomaps.com">Protomaps</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            },
        },
        layers: basemaps.layers('protomaps', cabinFlavor(), { lang: 'en' }),
    };
}

const els = {
    mapwrap: document.getElementById('mapwrap'),
    chip: document.getElementById('map-chip'),
    draw: document.getElementById('draw-button'),
    drawCancel: document.getElementById('draw-cancel'),
    clear: document.getElementById('clear-button'),
    keyword: document.getElementById('job-input'),
    count: document.getElementById('result-count'),
    status: document.getElementById('status'),
    results: document.getElementById('results'),
    showMore: document.getElementById('show-more'),
    freshness: document.getElementById('freshness'),
};

let map;
let shapeRing = null;
let drawMode = false;
let tracing = false;
let tracePx = [];
let markers = new Map();
let activeKey = null;
let currentJobs = [];
let shownCount = 0;

const emptyCollection = () => ({ type: 'FeatureCollection', features: [] });

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function setStatus(text) {
    els.status.textContent = text;
}

function relativeDate(iso) {
    if (!iso) return '';
    const days = Math.floor((Date.now() - new Date(iso)) / 86400000);
    if (days <= 0) return 'Posted today';
    if (days === 1) return 'Posted yesterday';
    if (days < 7) return `Posted ${days} days ago`;
    if (days < 30) return `Posted ${Math.floor(days / 7)} week${days < 14 ? '' : 's'} ago`;
    return `Posted ${Math.floor(days / 30)} month${days < 60 ? '' : 's'} ago`;
}

function payText(job) {
    const unit = PAY_UNITS[job.salary_interval];
    if (!unit || job.salary_min == null) return '';
    const money = n => '$' + Math.round(n).toLocaleString('en-US');
    return job.salary_max && job.salary_max !== job.salary_min
        ? `${money(job.salary_min)}–${money(job.salary_max)} ${unit}`
        : `${money(job.salary_min)} ${unit}`;
}

function precisionTag(precision) {
    return precision === 'exact'
        ? '<span class="tag tag-exact"><i class="tag-dot"></i>Exact address</span>'
        : '<span class="tag tag-town">Town-level</span>';
}

// ---------------------------------------------------------------------------
// Drawing

function pointFrom(event) {
    const rect = map.getCanvasContainer().getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
}

function distanceToSegmentSq(p, a, b) {
    let [x, y] = a;
    let dx = b[0] - x;
    let dy = b[1] - y;
    if (dx || dy) {
        const t = ((p[0] - x) * dx + (p[1] - y) * dy) / (dx * dx + dy * dy);
        if (t > 1) { x = b[0]; y = b[1]; } else if (t > 0) { x += dx * t; y += dy * t; }
    }
    dx = p[0] - x;
    dy = p[1] - y;
    return dx * dx + dy * dy;
}

// Douglas-Peucker in screen pixels: a traced finger produces hundreds of
// points, and every one of them would otherwise be sent to the search.
function simplify(points, tolerance) {
    if (points.length < 3) return points;
    const keep = new Uint8Array(points.length);
    keep[0] = keep[points.length - 1] = 1;
    const stack = [[0, points.length - 1]];
    const limit = tolerance * tolerance;
    while (stack.length) {
        const [first, last] = stack.pop();
        let farthest = 0;
        let index = 0;
        for (let i = first + 1; i < last; i++) {
            const d = distanceToSegmentSq(points[i], points[first], points[last]);
            if (d > farthest) { farthest = d; index = i; }
        }
        if (farthest > limit) {
            keep[index] = 1;
            stack.push([first, index], [index, last]);
        }
    }
    return points.filter((_, i) => keep[i]);
}

function setDrawMode(on) {
    drawMode = on;
    document.body.classList.toggle('drawing', on);
    els.mapwrap.classList.toggle('fullscreen', on && PHONE.matches);
    els.draw.textContent = on ? 'Cancel' : 'Draw your area';
    // Read the new size now: fitting a shape right after leaving full screen
    // would otherwise use the full-screen dimensions.
    map.resize();

    // Popups sit outside the drawing surface, so an open one silently eats
    // the drag wherever it covers the map.
    if (on) {
        for (const { marker } of markers.values()) {
            if (marker.getPopup().isOpen()) marker.togglePopup();
        }
    }

    for (const handler of [map.dragPan, map.doubleClickZoom, map.touchZoomRotate, map.boxZoom, map.scrollZoom]) {
        on ? handler.disable() : handler.enable();
    }
    if (!on) {
        map.touchZoomRotate.disableRotation();
        tracing = false;
        map.getSource('trace').setData(emptyCollection());
    }
}

function beginTrace(event) {
    if (!drawMode || event.button > 0) return;
    tracing = true;
    tracePx = [pointFrom(event)];
    map.getCanvasContainer().setPointerCapture?.(event.pointerId);
}

function extendTrace(event) {
    if (!tracing) return;
    event.preventDefault();
    const point = pointFrom(event);
    const last = tracePx[tracePx.length - 1];
    if (Math.hypot(point[0] - last[0], point[1] - last[1]) < MIN_STEP_PX) return;
    tracePx.push(point);
    map.getSource('trace').setData({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: tracePx.map(p => map.unproject(p).toArray()) },
    });
}

function endTrace() {
    if (!tracing) return;
    tracing = false;
    map.getSource('trace').setData(emptyCollection());

    if (tracePx.length < MIN_POINTS) {
        window.cupholder?.track('draw_too_short', { points: tracePx.length });
        setStatus('That was too short to be an area. Drag a longer outline.');
        return;
    }

    const ring = simplify(tracePx, SIMPLIFY_PX).map(p => map.unproject(p).toArray());
    setDrawMode(false);
    setShape(ring);
    runSearch('draw');
}

// ---------------------------------------------------------------------------
// Shape and results

function setShape(ring) {
    shapeRing = ring;
    const closed = ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1] ? ring : [...ring, ring[0]];
    map.getSource('shape').setData({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [closed] } });

    els.chip.textContent = 'Your shape';
    els.chip.hidden = false;

    const bounds = closed.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(closed[0], closed[0]));
    map.fitBounds(bounds, { padding: overlayPadding(), duration: 600 });
}

// Keep the shape clear of the label chip and the key, or a marker can end up
// hidden underneath them.
function overlayPadding() {
    const edge = PHONE.matches ? 24 : 48;
    const markerRadius = 16;
    const frame = els.mapwrap.getBoundingClientRect();
    const legend = document.querySelector('.legend').getBoundingClientRect();
    const top = els.chip.hidden
        ? edge
        : els.chip.getBoundingClientRect().bottom - frame.top + 12 + markerRadius;
    const bottom = frame.bottom - legend.top + 12 + markerRadius;
    return { top, bottom, left: edge, right: edge };
}

function clearShape() {
    shapeRing = null;
    map.getSource('shape').setData(emptyCollection());
    els.chip.hidden = true;
    clearMarkers();
    els.results.innerHTML = '';
    els.showMore.hidden = true;
    els.count.textContent = '';
    setStatus('');
}

// The Census geocoder shouts ("58646 MCNULTY WAY, SAINT HELENS, OR, 97051").
const KEEP_UPPER = new Set(['or', 'wa', 'ne', 'nw', 'se', 'sw']);

function tidyAddress(text) {
    if (!text || text !== text.toUpperCase()) return text;
    return text.toLowerCase().replace(/[a-z0-9]+/g, word =>
        KEEP_UPPER.has(word) ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1));
}

// Four decimals is about ten meters: jobs at one building share a pin even
// when one of them was placed by hand a few feet off.
function groupByPoint(jobs) {
    const groups = new Map();
    for (const job of jobs) {
        for (const location of job.locations) {
            const key = `${location.latitude.toFixed(4)},${location.longitude.toFixed(4)}`;
            if (!groups.has(key)) groups.set(key, { key, location, jobs: [] });
            groups.get(key).jobs.push(job);
        }
    }
    return [...groups.values()];
}

// One employer at a pin gets named once up top; a mixed pin names each job's.
function popupHtml(group) {
    const count = group.jobs.length;
    const precision = group.location.precision === 'exact' ? 'Exact address' : 'Town-level location';
    const employers = new Set(group.jobs.map(job => job.employer || ''));
    const oneEmployer = employers.size === 1 && [...employers][0];
    const items = group.jobs.map(job => {
        const detail = oneEmployer ? payText(job) : job.employer;
        return `
        <li>
            <a href="${escapeHtml(job.path)}" data-id="${job.id}">${escapeHtml(job.title)}</a>
            ${detail ? `<span>${escapeHtml(detail)}</span>` : ''}
        </li>`;
    }).join('');
    const place = escapeHtml(tidyAddress(group.location.raw_location) || 'Unknown location');
    return `
        <div class="popup">
            ${oneEmployer ? `<p class="popup-place">${escapeHtml(oneEmployer)}</p><p class="popup-meta">${place}</p>` : `<p class="popup-place">${place}</p>`}
            <p class="popup-meta">${count} job${count === 1 ? '' : 's'} &middot; ${precision}</p>
            <ul>${items}</ul>
        </div>`;
}

function markerElement(group) {
    const el = document.createElement('button');
    el.type = 'button';
    const count = group.jobs.length;
    const place = tidyAddress(group.location.raw_location) || 'this location';
    if (group.location.precision === 'exact') {
        el.className = 'pin pin-exact';
        if (count > 1) {
            const badge = document.createElement('span');
            badge.className = 'pin-count';
            badge.textContent = count;
            el.append(badge);
        }
        el.setAttribute('aria-label', `${count} job${count === 1 ? '' : 's'} at an exact address in ${place}`);
    } else {
        el.className = 'pin pin-town';
        el.textContent = count;
        el.setAttribute('aria-label', `${count} job${count === 1 ? '' : 's'} listed in ${place}`);
    }
    el.addEventListener('click', () => {
        window.cupholder?.track('marker_click', { jobs: count, precision: group.location.precision });
        highlight(group.key);
    });
    return el;
}

function clearMarkers() {
    for (const { marker } of markers.values()) marker.remove();
    markers = new Map();
    activeKey = null;
}

function highlight(key) {
    activeKey = key;
    for (const [k, { marker }] of markers) {
        marker.getElement().classList.toggle('is-active', k === key);
    }
    let first = null;
    for (const card of els.results.querySelectorAll('.job')) {
        const match = card.dataset.keys.split('|').includes(key);
        card.classList.toggle('is-active', match);
        if (match && !first) first = card;
    }
    if (first && !PHONE.matches) first.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function focusGroup(key) {
    const entry = markers.get(key);
    if (!entry) return;
    map.easeTo({ center: entry.marker.getLngLat(), zoom: Math.max(map.getZoom(), 10), duration: 500 });
    if (!entry.marker.getPopup().isOpen()) entry.marker.togglePopup();
    highlight(key);
    if (PHONE.matches) els.mapwrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function jobCard(job) {
    const inShape = job.locations;
    const keys = inShape.map(l => `${l.latitude},${l.longitude}`).join('|');
    const first = inShape[0];
    const extra = inShape.length > 1 ? ` <span class="more">+${inShape.length - 1} more</span>` : '';
    const pay = payText(job);
    return `
        <li class="job" data-id="${job.id}" data-keys="${escapeHtml(keys)}" data-first="${escapeHtml(keys.split('|')[0])}">
            <a class="job-title" href="${escapeHtml(job.path)}">${escapeHtml(job.title)}</a>
            <p class="job-employer">${escapeHtml(job.employer || 'Employer not listed')}</p>
            <p class="job-where">${precisionTag(first.precision)} <span>${escapeHtml(tidyAddress(first.raw_location) || '')}</span>${extra}</p>
            <p class="job-meta">${pay ? `<span class="pay">${escapeHtml(pay)}</span> &middot; ` : ''}${escapeHtml(relativeDate(job.date_posted))} &middot; via ${escapeHtml(SOURCE_LABELS[job.source] || 'employer site')}</p>
        </li>`;
}

// A big drawn shape can hold hundreds of jobs; rendering them all buries the
// rest of the page on a phone.
function showMoreJobs(event) {
    if (event) window.cupholder?.track('show_more', { shown: shownCount, total: currentJobs.length });
    const next = currentJobs.slice(shownCount, shownCount + PAGE_SIZE);
    els.results.insertAdjacentHTML('beforeend', next.map(jobCard).join(''));
    shownCount += next.length;

    const remaining = currentJobs.length - shownCount;
    els.showMore.hidden = remaining <= 0;
    els.showMore.textContent = `Show ${Math.min(remaining, PAGE_SIZE)} more of ${remaining}`;
    if (activeKey) highlight(activeKey);
}

function renderJobs(jobs) {
    clearMarkers();

    const groups = groupByPoint(jobs);
    for (const group of groups) {
        const marker = new maplibregl.Marker({ element: markerElement(group) })
            .setLngLat([group.location.longitude, group.location.latitude])
            .setPopup(new maplibregl.Popup({ offset: 18, maxWidth: '300px' }).setHTML(popupHtml(group)))
            .addTo(map);
        markers.set(group.key, { marker, group });
    }

    currentJobs = jobs;
    shownCount = 0;
    els.results.innerHTML = '';
    showMoreJobs();

    const places = groups.length === 1 ? '1 place' : `${groups.length} places`;
    els.count.textContent = `${jobs.length} job${jobs.length === 1 ? '' : 's'} inside your shape`;
    setStatus(`Across ${places}, newest first.`);
}

async function runSearch(trigger = 'keyword') {
    if (!shapeRing) return;
    setStatus('Searching…');

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(window.cupholder?.headers() || {}), 'X-Cupholder-Trigger': trigger },
            body: JSON.stringify({ polygon: shapeRing, what: els.keyword.value }),
        });
        if (!response.ok) {
            setStatus(`Search failed (${response.status}).`);
            return;
        }
        const jobs = await response.json();

        if (!jobs.length) {
            clearMarkers();
            els.results.innerHTML = '';
            els.showMore.hidden = true;
            els.count.textContent = 'Nothing inside that shape yet';
            setStatus(els.keyword.value.trim()
                ? 'Try clearing the keyword, or drawing a wider area.'
                : 'Try a wider area. Most listings sit in towns along the main roads.');
            return;
        }
        renderJobs(jobs);
    } catch {
        setStatus('Search failed. Check your connection and try again.');
    }
}

// ---------------------------------------------------------------------------
// Town labels

// The basemap leaves small towns unnamed until you're zoomed well in, which
// hides exactly the places people here draw around. Rank 1 is the corridor
// and shows at every zoom; rank 2 joins once the region fills the screen.
// Each town stops at its "until" zoom, where the basemap takes over naming it.
// Layer zoom ranges can't read feature properties, so there's one pair of
// layers per rank and cutoff.
async function addTownLabels() {
    let towns;
    try {
        towns = await (await fetch('/towns.geojson')).json();
    } catch {
        return;
    }
    map.addSource('towns', { type: 'geojson', data: towns });
    const groups = new Set(towns.features.map(f => `${f.properties.rank}|${f.properties.until}`));
    for (const group of groups) {
        const [rank, until] = group.split('|').map(Number);
        const minzoom = rank === 1 ? 0 : 8;
        const size = rank === 1 ? 13 : 12;
        const filter = ['all', ['==', ['get', 'rank'], rank], ['==', ['get', 'until'], until]];
        map.addLayer({
            id: `town-dot-${group}`, type: 'circle', source: 'towns', minzoom, maxzoom: until, filter,
            paint: { 'circle-radius': 3, 'circle-color': '#3A342C', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#F6F0E3' },
        }, 'trace-line');
        map.addLayer({
            id: `town-label-${group}`, type: 'symbol', source: 'towns', minzoom, maxzoom: until, filter,
            layout: {
                'text-field': ['get', 'name'],
                'text-font': [rank === 1 ? 'Noto Sans Medium' : 'Noto Sans Regular'],
                'text-size': size,
                'text-anchor': ['match', ['get', 'side'], 'left', 'right', 'left'],
                'text-offset': ['match', ['get', 'side'], 'left', ['literal', [-0.6, 0]], ['literal', [0.6, 0]]],
            },
            paint: { 'text-color': '#2E2A24', 'text-halo-color': '#F6F0E3', 'text-halo-width': 1.5 },
        }, 'trace-line');
    }
}

// ---------------------------------------------------------------------------
// Wiring

function wireControls() {
    const canvas = map.getCanvasContainer();
    canvas.addEventListener('pointerdown', beginTrace);
    canvas.addEventListener('pointermove', extendTrace, { passive: false });
    canvas.addEventListener('pointerup', endTrace);
    canvas.addEventListener('pointercancel', endTrace);

    els.draw.addEventListener('click', () => {
        window.cupholder?.track(drawMode ? 'draw_cancel' : 'draw_start', { redraw: Boolean(shapeRing) });
        setDrawMode(!drawMode);
    });
    els.drawCancel.addEventListener('click', () => {
        window.cupholder?.track('draw_cancel', {});
        setDrawMode(false);
    });
    els.clear.addEventListener('click', () => {
        window.cupholder?.track('shape_cleared', { results: currentJobs.length });
        setDrawMode(false);
        clearShape();
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && drawMode) setDrawMode(false); });

    els.showMore.addEventListener('click', showMoreJobs);

    let debounce;
    els.keyword.addEventListener('input', () => {
        clearTimeout(debounce);
        debounce = setTimeout(runSearch, 350);
    });

    els.results.addEventListener('click', event => {
        const card = event.target.closest('.job');
        if (!card) return;
        const rank = [...els.results.children].indexOf(card) + 1;
        if (event.target.closest('a')) {
            window.cupholder?.track('job_open', { job_id: Number(card.dataset.id), rank, from: 'list' });
            return;
        }
        window.cupholder?.track('card_click', { job_id: Number(card.dataset.id), rank });
        focusGroup(card.dataset.first);
    });

    // Popups are rebuilt by MapLibre, so listen on the map container.
    els.mapwrap.addEventListener('click', event => {
        const link = event.target.closest('.popup a');
        if (link) window.cupholder?.track('job_open', { job_id: Number(link.dataset.id), from: 'map' });
    });

    // Going full-screen to draw changes the map's size without a window resize.
    new ResizeObserver(() => map.resize()).observe(els.mapwrap);
}

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        return (await response.json()).tiles_url;
    } catch {
        return null;
    }
}

async function init() {
    maplibregl.addProtocol('pmtiles', new pmtiles.Protocol().tile);
    const tilesUrl = await loadConfig();

    map = new maplibregl.Map({
        container: 'map',
        style: mapStyle(tilesUrl),
        center: [-122.95, 45.85],
        zoom: 8.4,
        maxBounds: [[-127.5, 40.5], [-113.5, 50.5]],
        attributionControl: { compact: true },
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

    map.on('load', () => {
        map.addSource('shape', { type: 'geojson', data: emptyCollection() });
        map.addLayer({
            id: 'shape-fill', type: 'fill', source: 'shape',
            paint: { 'fill-color': cssVar('--map-shape'), 'fill-opacity': 0.24 },
        });
        map.addLayer({
            id: 'shape-line', type: 'line', source: 'shape',
            paint: { 'line-color': cssVar('--brand'), 'line-width': 2.5, 'line-dasharray': [2, 1.5] },
        });
        map.addSource('trace', { type: 'geojson', data: emptyCollection() });
        map.addLayer({
            id: 'trace-line', type: 'line', source: 'trace',
            layout: { 'line-cap': 'round', 'line-join': 'round' },
            paint: { 'line-color': cssVar('--brand'), 'line-width': 3 },
        });

        addTownLabels();
        wireControls();
        clearShape();
    });

    fetch('/api/health')
        .then(r => r.json())
        .then(data => {
            const run = data.last_successful_run;
            const hours = run?.finished_at ? Math.round((Date.now() - new Date(run.finished_at)) / 3600000) : null;
            const fresh = hours == null ? '' : hours < 1 ? ' · updated within the hour' : ` · updated ${hours} hour${hours === 1 ? '' : 's'} ago`;
            els.freshness.textContent = `${data.mappable_jobs} jobs across Oregon and Washington${fresh}`;
        })
        .catch(() => {});
}

init();
