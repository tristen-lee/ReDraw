const form = document.getElementById('post-form');
const status = document.getElementById('form-status');

function readErrors(body, httpStatus) {
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail)) {
        return body.detail
            .map(d => `${(d.loc || []).slice(-1)[0] || 'field'}: ${d.msg}`)
            .join(' · ');
    }
    return `Submission failed (${httpStatus}).`;
}

form.addEventListener('submit', async event => {
    event.preventDefault();

    const button = form.querySelector('button');
    button.disabled = true;
    status.className = '';
    status.textContent = 'Submitting…';

    const data = Object.fromEntries(new FormData(form).entries());
    for (const key of ['street_address', 'apply_url']) {
        if (!data[key]?.trim()) delete data[key];
    }

    try {
        const response = await fetch('/jobs/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const body = await response.json().catch(() => null);

        if (!response.ok) {
            status.className = 'error';
            status.textContent = readErrors(body, response.status);
            return;
        }

        status.className = 'ok';
        status.textContent = body.placed_as === 'exact'
            ? `Got it — placed at ${body.location}. It goes live once reviewed.`
            : `Got it — placed at ${body.location}, town-level. Add a street address next time for its own pin. It goes live once reviewed.`;
        form.reset();
    } catch {
        status.className = 'error';
        status.textContent = 'Could not reach the server. Try again in a moment.';
    } finally {
        button.disabled = false;
    }
});
