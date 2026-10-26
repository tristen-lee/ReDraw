const CHART = '#7A9A4C';

const $ = id => document.getElementById(id);
const tip = $('chart-tip');
let days = 30;
let shapesMap = null;

function token() {
    return sessionStorage.getItem('cupholder_admin') || '';
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

const number = n => (n == null ? '–' : Number(n).toLocaleString('en-US'));
const percent = (part, whole) => (whole ? `${Math.round((part / whole) * 100)}%` : '–');
const shortDate = iso => new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

// ---------------------------------------------------------------------------
// Pieces

function tiles(o) {
    const items = [
        ['Visitors', o.visitors, `${number(o.returning_visitors)} came back on another day`],
        ['Sessions', o.sessions, `${number(o.page_views)} page views`],
        ['Searches', o.searches, `by ${number(o.searchers)} visitor${o.searchers === 1 ? '' : 's'}`],
        ['Job pages opened', o.job_views, ''],
        ['Apply clicks', o.apply_clicks, 'sent to employers'],
    ];
    $('tiles').innerHTML = items.map(([label, value, note]) => `
        <div class="tile">
            <p class="tile-label">${label}</p>
            <p class="tile-value">${number(value)}</p>
            ${note ? `<p class="meta">${escapeHtml(note)}</p>` : ''}
        </div>`).join('');
}

function funnel(f) {
    const steps = [
        ['Visited', f.sessions],
        ['Started drawing', f.drew],
        ['Searched', f.searched],
        ['Got results', f.got_results],
        ['Opened a job', f.opened_job],
        ['Clicked apply', f.clicked_apply],
    ];
    const top = f.sessions || 0;
    $('funnel').innerHTML = steps.map(([label, value], i) => {
        const previous = i ? steps[i - 1][1] : null;
        const width = top ? Math.max((value / top) * 100, value ? 0.5 : 0) : 0;
        return `
            <div class="funnel-row" data-tip="${escapeHtml(`${label}: ${number(value)} sessions${previous != null ? `, ${percent(value, previous)} of the step before` : ''}`)}">
                <span class="funnel-label">${label}</span>
                <span class="funnel-track"><span class="funnel-bar" style="width:${width}%"></span></span>
                <span class="funnel-value">${number(value)} <span class="meta">${i ? percent(value, previous) : ''}</span></span>
            </div>`;
    }).join('');
}

// One series per chart: three measures with different scales get three
// charts, never one chart with two axes.
function bars(el, data, key, unit) {
    const W = 320, H = 120, top = 16, bottom = 18;
    const plot = H - top - bottom;
    const max = Math.max(1, ...data.map(d => d[key]));
    const step = W / data.length;
    const gap = Math.min(2, step * 0.25);
    const width = step - gap;
    const radius = Math.min(4, width / 2);

    const columns = data.map((d, i) => {
        const x = i * step;
        const h = (d[key] / max) * plot;
        const y = top + plot - h;
        const r = Math.min(radius, h);
        const shape = h > 0
            ? `<path d="M${x},${top + plot} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${top + plot} Z" fill="${CHART}"/>`
            : '';
        const label = `${shortDate(d.day)}: ${number(d[key])} ${d[key] === 1 ? unit : `${unit}s`}`;
        return `${shape}<rect class="hit" x="${x}" y="0" width="${step}" height="${H - bottom}" data-tip="${escapeHtml(label)}"/>`;
    }).join('');

    el.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeHtml(`${unit}s per day, peak ${max}`)}">
            <text x="0" y="10" class="axis">${number(max)}</text>
            <line x1="0" x2="${W}" y1="${top + plot}" y2="${top + plot}" class="baseline"/>
            ${columns}
            <text x="0" y="${H - 4}" class="axis">${shortDate(data[0].day)}</text>
            <text x="${W}" y="${H - 4}" class="axis" text-anchor="end">${shortDate(data.at(-1).day)}</text>
        </svg>`;
}

function table(el, rows, columns, empty = 'Nothing yet.') {
    if (!rows.length) {
        el.innerHTML = `<p class="meta">${empty}</p>`;
        return;
    }
    el.innerHTML = `
        <table class="stats-table">
            <thead><tr>${columns.map(c => `<th class="${c.num ? 'num' : ''}">${c.label}</th>`).join('')}</tr></thead>
            <tbody>${rows.map(r => `<tr>${columns.map(c => `<td class="${c.num ? 'num' : ''}">${c.html ? c.html(r) : escapeHtml(c.num ? number(r[c.key]) : r[c.key] ?? '–')}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>`;
}

function searching(s) {
    $('searching').innerHTML = `
        <dl class="facts-list">
            <div><dt>Shapes drawn</dt><dd>${number(s.shapes_drawn)}</dd></div>
            <div><dt>Median area</dt><dd>${s.median_area_sq_mi != null ? `${number(s.median_area_sq_mi)} sq mi` : '–'}</dd></div>
            <div><dt>Median results</dt><dd>${number(s.median_results)}</dd></div>
            <div><dt>Came back empty</dt><dd>${number(s.zero_results)} <span class="meta">${percent(s.zero_results, s.searches)}</span></dd></div>
            <div><dt>Used a keyword</dt><dd>${number(s.with_keyword)}</dd></div>
            <div><dt>Search time</dt><dd>${s.avg_ms != null ? `${number(s.avg_ms)} ms` : '–'}</dd></div>
        </dl>`;
}

function drawShapes(shapes) {
    const data = {
        type: 'FeatureCollection',
        features: shapes.map(s => ({
            type: 'Feature',
            geometry: s.geometry,
            properties: { results: s.result_count, keyword: s.keyword || '', when: s.occurred_at },
        })),
    };
    $('shapes-note').textContent = shapes.length
        ? `${number(shapes.length)} most recent shapes. Darker means more people drew over it.`
        : 'No shapes drawn in this range.';

    if (shapesMap) {
        shapesMap.getSource('shapes')?.setData(data);
        fitShapes(data);
        return;
    }

    shapesMap = new maplibregl.Map({
        container: 'shapes-map',
        style: {
            version: 8,
            sources: {
                osm: {
                    type: 'raster',
                    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
                    tileSize: 256,
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                },
            },
            layers: [{ id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': -0.8, 'raster-brightness-max': 0.55 } }],
        },
        center: [-122.95, 45.85],
        zoom: 8,
        attributionControl: { compact: true },
    });
    shapesMap.on('load', () => {
        shapesMap.addSource('shapes', { type: 'geojson', data });
        shapesMap.addLayer({ id: 'shapes-fill', type: 'fill', source: 'shapes', paint: { 'fill-color': CHART, 'fill-opacity': 0.14 } });
        shapesMap.addLayer({ id: 'shapes-line', type: 'line', source: 'shapes', paint: { 'line-color': CHART, 'line-width': 1, 'line-opacity': 0.7 } });
        shapesMap.on('click', 'shapes-fill', event => {
            const items = event.features.slice(0, 6).map(f => {
                const p = f.properties;
                return `<li>${number(p.results)} results${p.keyword ? ` for “${escapeHtml(p.keyword)}”` : ''} · ${new Date(p.when).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</li>`;
            }).join('');
            new maplibregl.Popup({ maxWidth: '280px' })
                .setLngLat(event.lngLat)
                .setHTML(`<div class="popup"><p class="popup-meta">${event.features.length} shape${event.features.length === 1 ? '' : 's'} here</p><ul>${items}</ul></div>`)
                .addTo(shapesMap);
        });
        shapesMap.on('mouseenter', 'shapes-fill', () => { shapesMap.getCanvas().style.cursor = 'pointer'; });
        shapesMap.on('mouseleave', 'shapes-fill', () => { shapesMap.getCanvas().style.cursor = ''; });
        fitShapes(data);
    });
}

function fitShapes(data) {
    if (!data.features.length) return;
    const bounds = new maplibregl.LngLatBounds();
    for (const f of data.features) for (const ring of f.geometry.coordinates) for (const c of ring) bounds.extend(c);
    shapesMap.fitBounds(bounds, { padding: 32, maxZoom: 11, duration: 0 });
}

// ---------------------------------------------------------------------------
// Loading

async function load() {
    $('stats-status').textContent = 'Loading…';
    const response = await fetch(`/api/admin/stats?days=${days}`, { headers: { 'X-Admin-Token': token() } });

    if (response.status === 401 || response.status === 503) {
        sessionStorage.removeItem('cupholder_admin');
        $('auth').hidden = false;
        $('board').hidden = true;
        $('stats-status').textContent = response.status === 401 ? 'Bad token.' : 'ADMIN_TOKEN is not set on the server.';
        return;
    }
    if (!response.ok) {
        $('stats-status').textContent = `Failed to load (${response.status}).`;
        return;
    }

    // This browser belongs to the owner: stop it from counting itself.
    try { localStorage.setItem('cupholder_internal', '1'); } catch { /* private mode */ }

    const s = await response.json();
    $('auth').hidden = true;
    $('board').hidden = false;
    $('stats-status').textContent = `Last ${s.days} days. Your own browser is excluded.`;

    tiles(s.overview);
    funnel(s.funnel);
    bars($('daily-visitors'), s.daily, 'visitors', 'visitor');
    bars($('daily-searches'), s.daily, 'searches', 'search');
    bars($('daily-applies'), s.daily, 'apply_clicks', 'apply click');
    drawShapes(s.shapes);

    table($('sources'), s.sources, [
        { label: 'Source', key: 'source' },
        { label: 'Campaign', key: 'campaign' },
        { label: 'Sessions', key: 'sessions', num: true },
        { label: 'Searched', key: 'searched', num: true },
        { label: 'Applied', key: 'applied', num: true },
    ]);
    searching(s.searching);
    table($('keywords'), s.keywords, [
        { label: 'Keyword', key: 'keyword' },
        { label: 'Searches', key: 'searches', num: true },
        { label: 'Avg results', key: 'avg_results', num: true },
        { label: 'Empty', key: 'zero_results', num: true },
    ], 'No keyword searches yet.');
    table($('pages'), s.pages, [
        { label: 'Page', key: 'path' },
        { label: 'Views', key: 'views', num: true },
        { label: 'Median time', html: r => (r.median_seconds != null ? `${number(r.median_seconds)}s` : '–'), num: true },
    ]);
    table($('devices'), s.devices, [
        { label: 'Device', key: 'device' },
        { label: 'Sessions', key: 'sessions', num: true },
    ]);
    table($('jobs'), s.jobs, [
        { label: 'Job', html: r => `<a href="/jobs/${r.id}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a><br><span class="meta">${escapeHtml(r.employer)} · ${escapeHtml(r.source)}</span>` },
        { label: 'Views', key: 'views', num: true },
        { label: 'Applies', key: 'applies', num: true },
    ]);
    table($('errors'), s.errors, [
        { label: 'When', html: r => escapeHtml(new Date(r.occurred_at).toLocaleString('en-US')) },
        { label: 'Page', key: 'path' },
        { label: 'Error', html: r => `${escapeHtml(r.message)}<br><span class="meta">${escapeHtml(r.source)}</span>` },
    ], 'No script errors. Good.');
}

// ---------------------------------------------------------------------------
// Wiring

document.addEventListener('pointermove', event => {
    const target = event.target.closest('[data-tip]');
    if (!target) {
        tip.hidden = true;
        return;
    }
    tip.textContent = target.dataset.tip;
    tip.hidden = false;
    const x = Math.min(event.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = `${x}px`;
    tip.style.top = `${event.clientY + 14}px`;
});

document.querySelector('.stats-range').addEventListener('click', event => {
    const button = event.target.closest('button[data-days]');
    if (!button) return;
    days = Number(button.dataset.days);
    for (const b of document.querySelectorAll('.stats-range button')) {
        b.setAttribute('aria-pressed', String(b === button));
    }
    load();
});

$('unlock').addEventListener('click', () => {
    sessionStorage.setItem('cupholder_admin', $('token').value);
    load();
});
$('token').addEventListener('keydown', e => {
    if (e.key === 'Enter') $('unlock').click();
});

if (token()) load();
else $('stats-status').textContent = '';
