(function () {
    const createBtn = document.getElementById("create-room-btn");
    const modal = document.getElementById("create-modal");
    const form = document.getElementById("create-form");
    const listEl = document.getElementById("room-list");

    if (!P2P.webrtcSupported()) {
        P2P.toast.error("Your browser does not support WebRTC file transfer.");
    }

    function openModal() { modal.classList.remove("hidden"); }
    function closeModal() { modal.classList.add("hidden"); }

    if (createBtn) createBtn.addEventListener("click", openModal);
    modal.querySelectorAll("[data-close]").forEach((el) =>
        el.addEventListener("click", closeModal)
    );
    modal.addEventListener("click", (e) => {
        if (e.target === modal) closeModal();
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        const data = Object.fromEntries(new FormData(form).entries());
        try {
            const res = await fetch("/api/rooms", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            });
            const body = await res.json();
            if (!res.ok) throw new Error(body.error || "Failed to create room.");
            const room = body.room;
            closeModal();
            form.reset();
            P2P.toast.success("Room created!");
            window.location.href = "/room/" + room.id;
        } catch (err) {
            P2P.toast.error(err.message);
        } finally {
            submitBtn.disabled = false;
        }
    });

    function renderRoom(room) {
        const card = document.createElement("div");
        card.className = "room-card";
        card.innerHTML = `
            <h3 class="room-card__name">${P2P.escapeHtml(room.name)}</h3>
            <div class="room-card__meta">by ${P2P.escapeHtml(room.creator)}</div>
            <div class="room-card__badges">
                <span class="badge badge--live">Live</span>
                <span class="badge">${P2P.escapeHtml(room.type)}</span>
                <span class="badge badge--lock">Password</span>
            </div>
            <div class="room-card__meta">
                ${room.peerCount}/${room.maxPeers} connected ·
                ${room.fileCount} file${room.fileCount === 1 ? "" : "s"}
            </div>
            <a class="btn btn--primary btn--block" href="/join/${P2P.escapeHtml(room.id)}">Join Room</a>
        `;
        listEl.appendChild(card);
    }

    async function loadRooms() {
        try {
            const res = await fetch("/api/rooms");
            const body = await res.json();
            listEl.innerHTML = "";
            listEl.setAttribute("aria-busy", "false");
            const rooms = body.rooms || [];
            if (rooms.length === 0) {
                listEl.innerHTML =
                    '<div class="empty-state">No rooms right now. Create one to get started!</div>';
                return;
            }
            rooms.forEach(renderRoom);
        } catch (err) {
            listEl.setAttribute("aria-busy", "false");
            listEl.innerHTML =
                '<div class="empty-state">Could not load rooms. Please try again.</div>';
        }
    }

    loadRooms();
    const refreshTimer = setInterval(loadRooms, 15000);
})();