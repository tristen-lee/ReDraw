const form = document.getElementById('post-form');
const status = document.getElementById('form-status');

const FIELD_NAMES = {
    employer: 'Employer',
    title: 'Job title',
    town: 'Town',
    street_address: 'Street address',
    description: 'Description',
    apply_url: 'Where to apply',
    contact_email: 'Your email',
};

function readErrors(body, httpStatus) {
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail)) {
        return body.detail
            .map(d => `${FIELD_NAMES[(d.loc || []).slice(-1)[0]] || 'Form'}: ${d.msg.replace(/^Value error, /, '')}`)
            .join(' · ');
    }
    return `Submission failed (${httpStatus}).`;
}

form.addEventListener('focusin', () => window.cupholder?.track('post_start', {}), { once: true });

form.addEventListener('submit', async event => {
    event.preventDefault();

    const button = form.querySelector('button');
    button.disabled = true;
    status.className = '';
    status.textContent = 'Submitting…';

    const data = Object.fromEntries(new FormData(form).entries());
    try {
        const response = await fetch('/api/jobs/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const body = await response.json().catch(() => null);

        if (!response.ok) {
            window.cupholder?.track('post_failed', { status: response.status });
            status.className = 'error';
            status.textContent = readErrors(body, response.status);
            return;
        }

        window.cupholder?.track('post_submitted', { placed: Boolean(body.placed) });
        status.className = 'ok';
        status.textContent = body.placed
            ? `Got it. Placed at ${body.location}. It goes live once reviewed.`
            : `Got it. We'll double-check the address and put it on the map once it's reviewed.`;
        if (body.manage_url) {
            const keep = document.createElement('p');
            keep.className = 'manage-link';
            keep.append(body.emailed
                ? `We also emailed this to ${data.contact_email}. Use it to renew the post or take it down: `
                : 'Bookmark this to renew it or take it down later: ');
            const link = document.createElement('a');
            link.href = body.manage_url;
            link.textContent = body.manage_url;
            keep.append(link);
            status.append(keep);
        }
        form.reset();
    } catch {
        status.className = 'error';
        status.textContent = 'Could not reach the server. Try again in a moment.';
    } finally {
        button.disabled = false;
    }
});
