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

    const response = await fetch('/admin/pending', { headers: { 'X-Admin-Token': token() } });

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
    queueStatus.textContent = jobs.length ? `${jobs.length} waiting.` : 'Nothing waiting.';

    queue.innerHTML = jobs.map(job => `
        <article class="queued" data-id="${job.id}">
            <h3>${escapeHtml(job.title)}</h3>
            <p class="meta">
                ${escapeHtml(job.employer)} &middot;
                ${escapeHtml(job.location || 'no location')} &middot;
                <span class="${job.precision === 'exact' ? 'exact' : ''}">${escapeHtml(job.precision || '?')}</span>
            </p>
            <p class="meta">${escapeHtml(job.contact_email)} &middot; ${escapeHtml(job.submitted_at || '')}</p>
            <div class="actions">
                <button data-approve="1">Approve</button>
                <button data-approve="0" class="reject">Reject</button>
            </div>
        </article>
    `).join('');
}

queue.addEventListener('click', async event => {
    const button = event.target.closest('button[data-approve]');
    if (!button) return;

    const card = button.closest('.queued');
    card.querySelectorAll('button').forEach(b => (b.disabled = true));

    const response = await fetch(`/admin/review/${card.dataset.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token() },
        body: JSON.stringify({ approve: button.dataset.approve === '1' })
    });

    if (response.ok) {
        card.remove();
        const left = queue.querySelectorAll('.queued').length;
        queueStatus.textContent = left ? `${left} waiting.` : 'Nothing waiting.';
    } else {
        queueStatus.className = 'error';
        queueStatus.textContent = `Review failed (${response.status}).`;
        card.querySelectorAll('button').forEach(b => (b.disabled = false));
    }
});

document.getElementById('unlock').addEventListener('click', () => {
    sessionStorage.setItem('cupholder_admin', document.getElementById('token').value);
    loadQueue();
});

document.getElementById('token').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('unlock').click();
});

if (token()) loadQueue();
