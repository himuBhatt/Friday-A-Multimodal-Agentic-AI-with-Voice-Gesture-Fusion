async function toggleFriday() {
    const btn = document.getElementById('power-btn');
    const orb = document.getElementById('orb');
    const status = document.getElementById('sys-status');

    try {
        // Ensure this matches the @app.route in app.py
        const response = await fetch('/api/toggle', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();

        if (data.status === "online") {
            orb.classList.add('active');
            status.innerText = "ONLINE";
            status.style.color = "#00ffff";
            btn.innerText = "TERMINATE SESSION";
        } else {
            orb.classList.remove('active');
            status.innerText = "OFFLINE";
            btn.innerText = "INITIALIZE CORE";
        }
    } catch (error) {
        console.error("Connection Failed:", error);
        alert("Cannot connect to Friday Server. Is app.py running?");
    }
}