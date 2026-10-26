// First-party analytics. Two random ids and nothing else: a visitor id kept in
// localStorage, and a session id that lapses after 30 idle minutes. Admin
// browsers mark themselves internal and send nothing.
(() => {
    const SESSION_IDLE_MS = 30 * 60 * 1000;
    const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign'];

    function store(kind) {
        try { return window[kind]; } catch { return null; }
    }
    const local = store('localStorage');
    const session = store('sessionStorage');

    function newId() {
        if (crypto.randomUUID) return crypto.randomUUID();
        const b = crypto.getRandomValues(new Uint8Array(16));
        b[6] = (b[6] & 0x0f) | 0x40;
        b[8] = (b[8] & 0x3f) | 0x80;
        const h = [...b].map(x => x.toString(16).padStart(2, '0')).join('');
        return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
    }

    function read(storage, key) {
        try { return storage?.getItem(key) ?? null; } catch { return null; }
    }
    function write(storage, key, value) {
        try { storage?.setItem(key, value); } catch { /* private mode */ }
    }

    const internal = read(local, 'cupholder_internal') === '1';

    let visitor = read(local, 'cupholder_visitor');
    if (!visitor) { visitor = newId(); write(local, 'cupholder_visitor', visitor); }

    // Kept in localStorage, not sessionStorage, so a job opened in a new tab
    // stays in the session that found it.
    let sessionId = read(local, 'cupholder_session');
    const lastSeen = Number(read(local, 'cupholder_session_seen') || 0);
    const freshSession = !sessionId || Date.now() - lastSeen > SESSION_IDLE_MS;
    if (freshSession) { sessionId = newId(); write(local, 'cupholder_session', sessionId); }
    write(local, 'cupholder_session_seen', String(Date.now()));

    const params = new URLSearchParams(location.search);
    const utm = {};
    for (const key of UTM_KEYS) if (params.get(key)) utm[key] = params.get(key);

    const width = window.innerWidth;
    const device = width < 768 ? 'phone' : width < 1100 ? 'tablet' : 'desktop';

    function send(name, props = {}, extra = {}) {
        if (internal) return;
        write(local, 'cupholder_session_seen', String(Date.now()));
        const body = JSON.stringify({
            name, props, visitor, session: sessionId, device,
            path: location.pathname, ...extra,
        });
        const blob = new Blob([body], { type: 'application/json' });
        if (!(navigator.sendBeacon && navigator.sendBeacon('/api/events', blob))) {
            fetch('/api/events', { method: 'POST', body, headers: { 'Content-Type': 'application/json' }, keepalive: true })
                .catch(() => {});
        }
    }

    window.cupholder = {
        track: send,
        // Search goes through fetch, so the ids ride along as headers and the
        // server logs the search itself; an ad blocker can't drop that.
        headers: () => internal
            ? { 'X-Cupholder-Internal': '1' }
            : { 'X-Cupholder-Visitor': visitor, 'X-Cupholder-Session': sessionId },
    };

    send('page_view', { new_session: freshSession }, { referrer: document.referrer || null, ...utm });

    const opened = Date.now();
    let left = false;
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'hidden' || left) return;
        left = true;
        send('page_leave', { seconds: Math.round((Date.now() - opened) / 1000) });
    });

    window.addEventListener('error', event => {
        send('js_error', {
            message: String(event.message || '').slice(0, 300),
            source: `${String(event.filename || '').split('/').pop()}:${event.lineno || 0}`,
        });
    });

    // Anything marked data-track="name" reports itself when clicked, with
    // data-track-* attributes as props. Links leaving the site are caught too.
    document.addEventListener('click', event => {
        const marked = event.target.closest('[data-track]');
        if (marked) {
            const props = {};
            for (const [key, value] of Object.entries(marked.dataset)) {
                if (key.startsWith('track') && key !== 'track') {
                    props[key.slice(5).replace(/[A-Z]/g, c => '_' + c.toLowerCase()).slice(1)] = value;
                }
            }
            send(marked.dataset.track, props);
            return;
        }
        const link = event.target.closest('a[href]');
        if (link && link.host && link.host !== location.host) {
            send('outbound_click', { host: link.host, text: link.textContent.trim().slice(0, 60) });
        }
    }, true);
})();
