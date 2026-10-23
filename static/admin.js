const auth = document.getElementById('auth');
const queue = document.getElementById('queue');
const queueStatus = document.getElementById('queue-status');

function token() {
    return sessionStorage.getItem('cupholder_admin') || '';
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

async function loadQueue() {
    queueStatus.className = '';
    queueStatus.textContent = 'Loading…';

    const response = await fetch('/api/admin/pending', { headers: { 'X-Admin-Token': token() } });

    if (response.status === 401) {
        sessionStorage.removeItem('cupholder_admin');
        auth.style.display = '';
        queueStatus.className = 'error';
        queueStatus.textContent = 'Bad token.';
        queue.innerHTML = '';
        return;
    }
    if (response.status === 503) {
        queueStatus.className = 'error';
        queueStatus.textContent = 'ADMIN_TOKEN is not set on the server.';
        return;
    }
    if (!response.ok) {
        queueStatus.className = 'error';
        queueStatus.textContent = `Failed to load (${response.status}).`;
        return;
    }

    const jobs = await response.json();
    auth.style.display = 'none';
    document.getElementById('tools').hidden = false;
    loadReports();
    queueStatus.textContent = jobs.length ? `${jobs.length} waiting.` : 'Nothing waiting.';

    queue.innerHTML = jobs.map(job => `
        <article class="queued" data-id="${job.id}">
            <h3>${escapeHtml(job.title)}</h3>
            <p class="meta">
                ${escapeHtml(job.employer)} &middot;
                ${job.location
                    ? `${escapeHtml(job.location)} &middot; <span class="exact">${escapeHtml(job.precision)}</span>`
                    : `<span class="unplaced">Address not found:</span> ${escapeHtml(job.submitted_address || 'none given')}`}
            </p>
            ${job.location ? '' : `
            <form class="place-form">
                <label>
                    Fix the address, or paste coordinates from Google Maps
                    <input name="place" value="${escapeHtml(job.submitted_address || '')}" autocomplete="off">
                </label>
                <button type="submit">Place it</button>
            </form>`}
            <p class="meta">${escapeHtml(job.contact_email)} &middot; ${escapeHtml(job.submitted_at || '')}</p>
            <p class="meta">Apply link: ${job.apply_url ? `<code>${escapeHtml(job.apply_url)}</code>` : 'none given'}</p>
            <div class="actions">
                <button data-approve="1">Approve</button>
                <button data-approve="0" class="reject">Reject</button>
            </div>
        </article>
    `).join('');
}

const COORDINATES = /^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/;

queue.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target.closest('.place-form');
    if (!form) return;

    const value = form.elements.place.value.trim();
    const point = value.match(COORDINATES);
    const body = point
        ? { latitude: Number(point[1]), longitude: Number(point[2]) }
        : { address: value };

    form.querySelector('button').disabled = true;
    const response = await fetch(`/api/admin/place/${form.closest('.queued').dataset.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token() },
        body: JSON.stringify(body)
    });
    const result = await response.json().catch(() => null);

    if (response.ok) {
        loadQueue();
    } else {
        queueStatus.className = 'error';
        queueStatus.textContent = typeof result?.detail === 'string' ? result.detail : `Placing failed (${response.status}).`;
        form.querySelector('button').disabled = false;
    }
});

queue.addEventListener('click', async event => {
    const button = event.target.closest('button[data-approve]');
    if (!button) return;

    const card = button.closest('.queued');
    card.querySelectorAll('button').forEach(b => (b.disabled = true));

    const response = await fetch(`/api/admin/review/${card.dataset.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token() },
        body: JSON.stringify({ approve: button.dataset.approve === '1' })
    });

    if (response.ok) {
        card.remove();
        const left = queue.querySelectorAll('.queued').length;
        queueStatus.textContent = left ? `${left} waiting.` : 'Nothing waiting.';
    } else {
        const result = await response.json().catch(() => null);
        queueStatus.className = 'error';
        queueStatus.textContent = typeof result?.detail === 'string' ? result.detail : `Review failed (${response.status}).`;
        card.querySelectorAll('button').forEach(b => (b.disabled = false));
    }
});

const REASONS = { scam: 'Looks like a scam', filled: 'Filled or gone', wrong_location: 'Wrong location', other: 'Something else' };
const reportsBox = document.getElementById('reports');
const reportsStatus = document.getElementById('reports-status');
const toolsStatus = document.getElementById('tools-status');

function adminPost(path, body) {
    return fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token() },
        body: JSON.stringify(body || {})
    }).then(async response => ({ ok: response.ok, status: response.status, body: await response.json().catch(() => null) }));
}

function explain(result) {
    return typeof result.body?.detail === 'string' ? result.body.detail : `Failed (${result.status}).`;
}

async function loadReports() {
    const response = await fetch('/api/admin/reports', { headers: { 'X-Admin-Token': token() } });
    if (!response.ok) {
        reportsStatus.textContent = `Couldn't load reports (${response.status}).`;
        return;
    }
    const reports = await response.json();
    reportsStatus.textContent = reports.length ? `${reports.length} open.` : 'No open reports.';
    reportsBox.innerHTML = reports.map(report => `
        <article class="queued" data-job="${report.job_id}">
            <h3><a href="/jobs/${report.job_id}" target="_blank" rel="noopener">${escapeHtml(report.title)}</a></h3>
            <p class="meta">${escapeHtml(report.employer)} &middot; ${escapeHtml(report.source)}${report.reports_on_job > 1 ? ` &middot; <span class="unplaced">${report.reports_on_job} reports</span>` : ''}</p>
            <p class="meta"><strong>${escapeHtml(REASONS[report.reason] || report.reason)}</strong>${report.details ? `: ${escapeHtml(report.details)}` : ''}</p>
            <div class="actions">
                <button data-report="remove">Take it down</button>
                <button data-report="dismiss" class="reject">Dismiss</button>
            </div>
        </article>
    `).join('');
}

reportsBox.addEventListener('click', async event => {
    const button = event.target.closest('button[data-report]');
    if (!button) return;
    const jobId = button.closest('.queued').dataset.job;
    button.disabled = true;
    const result = button.dataset.report === 'remove'
        ? await adminPost(`/api/admin/jobs/${jobId}/remove`, { note: 'reported' })
        : await adminPost(`/api/admin/reports/${jobId}/dismiss`);
    if (!result.ok) {
        reportsStatus.className = 'error';
        reportsStatus.textContent = explain(result);
        button.disabled = false;
        return;
    }
    loadReports();
});

document.getElementById('remove-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target;
    const input = form.elements.job.value.trim();
    const match = input.match(/\/jobs\/(\d+)/) || input.match(/^(\d+)$/);
    if (!match) {
        toolsStatus.className = 'error';
        toolsStatus.textContent = "That doesn't have a job number in it.";
        return;
    }
    const result = await adminPost(`/api/admin/jobs/${match[1]}/remove`, { note: form.elements.note.value.trim() || null });
    toolsStatus.className = result.ok ? 'ok' : 'error';
    toolsStatus.textContent = result.ok
        ? (result.body.removed ? `Took down "${result.body.title}" (${result.body.employer}).` : `"${result.body.title}" was already down.`)
        : explain(result);
    if (result.ok) form.reset();
});

document.getElementById('optout-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target;
    const name = form.elements.name.value.trim();
    if (!confirm(`Remove every listing from "${name}" and never crawl them again?`)) return;
    const result = await adminPost('/api/admin/employers/opt-out', { name });
    toolsStatus.className = result.ok ? 'ok' : 'error';
    toolsStatus.textContent = result.ok
        ? `${result.body.employer} is opted out. ${result.body.jobs_removed} listing(s) taken down.`
        : explain(result);
    if (result.ok) form.reset();
});

document.getElementById('unlock').addEventListener('click', () => {
    sessionStorage.setItem('cupholder_admin', document.getElementById('token').value);
    loadQueue();
});

document.getElementById('token').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('unlock').click();
});

if (token()) loadQueue();
