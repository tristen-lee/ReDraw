// Leaflet //

const map = L.map('map').setView([45.52, -122.68], 12);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors' 
}).addTo(map);

// Leaflet.draw //

const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

const drawControl = new L.Control.Draw({
    edit: { featureGroup: drawnItems },
    draw: {polygon: true, marker: false, circle: false, rectangle: false, polyline: false }

});
map.addControl(drawControl);


let currentShape;
map.on(L.Draw.Event.CREATED, function (e) {
    const layer = e.layer;
    drawnItems.addLayer(layer);
    currentShape = layer;
});
// HTTP Request Spot //

async function runSearch() {
    const button = document.getElementById('search-button');
    button.disabled = true;
    button.textContent = 'Searching...';

    try {
        const what = document.getElementById('job-input').value;

        const points = currentShape.getLatLngs()[0];
        const polygon = points.map(point => [point.lng, point.lat]);

        const response = await fetch('http://127.0.0.1:8000/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ what, polygon })
        });
        const jobs = await response.json();

        for (const job of jobs) {
            L.marker([job.latitude, job.longitude])
                .addTo(map)
                .bindPopup(`<b>${job.title}</b><br>${job.company}<br><a href="${job.url}" target="_blank">Apply</a>`);
        }
    }

    finally { 
        button.disabled =false; button.textContent='Search'
}}


document.getElementById('search-button').addEventListener('click', runSearch);