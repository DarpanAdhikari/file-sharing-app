(function () {
    const info = document.getElementById("room-info");
    const form = document.getElementById("join-form");
    const joinBtn = document.getElementById("join-btn");
    const errEl = document.getElementById("join-error");
    const roomIdInput = document.getElementById("room-id-input");
    const scanBtn = document.getElementById("scan-btn");
    const scannerEl = document.getElementById("scanner");
    const scanStatus = document.getElementById("scan-status");
    const scanStop = document.getElementById("scan-stop");
    const video = document.getElementById("scan-video");

    const INITIAL = window.INITIAL_ROOM_ID || "";

    function extractRoomId(value) {
        const v = (value || "").trim();
        if (!v) return "";
        // full URL: https://host/join/ROOMID
        const m = v.match(/\/join\/([a-f0-9]+)/i);
        if (m) return m[1];
        return v.split("?")[0];
    }

    function resolveRoomId() {
        const roomId = extractRoomId(roomIdInput.value) || extractRoomId(INITIAL);
        roomIdInput.value = roomId;
        return roomId;
    }

    if (INITIAL) {
        roomIdInput.value = extractRoomId(INITIAL);
        resolveRoomId();
        info.textContent = "Room: " + roomIdInput.value;
    }

    document.getElementById("back-btn").addEventListener("click", () => {
        window.location.href = "/";
    });

    function showError(msg) {
        errEl.textContent = msg;
        errEl.classList.remove("hidden");
    }

    // ---- QR scanner ----
    let stream = null;
    let scanTimer = null;

    async function startScanner() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "environment" },
                audio: false,
            });
        } catch (e) {
            showError("Camera access denied or unavailable. Please enter the room code manually.");
            return;
        }
        scannerEl.classList.remove("hidden");
        video.srcObject = stream;
        await video.play();
        scanStatus.textContent = "Point your camera at the room's QR code.";
        scanTimer = setInterval(scanFrame, 250);
    }

    function scanFrame() {
        if (video.readyState !== video.HAVE_ENOUGH_DATA) return;
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const code = window.jsQR(imageData.data, imageData.width, imageData.height, {
            inversionAttempts: "dontInvert",
        });
        if (code && code.data) {
            const roomId = extractRoomId(code.data);
            if (roomId) {
                roomIdInput.value = roomId;
                info.textContent = "Room: " + roomId;
                scanStatus.textContent = "QR detected. Enter the room password to continue.";
                stopScanner();
                document.querySelector('input[name="password"]').focus();
                P2P.toast.success("Room detected — enter the password.");
            }
        }
    }

    function stopScanner() {
        if (scanTimer) { clearInterval(scanTimer); scanTimer = null; }
        if (stream) {
            stream.getTracks().forEach((t) => t.stop());
            stream = null;
        }
        if (video.srcObject) video.srcObject = null;
        scannerEl.classList.add("hidden");
    }

    scanBtn.addEventListener("click", startScanner);
    scanStop.addEventListener("click", stopScanner);

    window.addEventListener("pagehide", stopScanner);

    // ---- submit ----
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        errEl.classList.add("hidden");
        const roomId = resolveRoomId();
        if (!roomId) { showError("Please enter a room code or scan a QR code."); return; }

        joinBtn.disabled = true;
        const data = Object.fromEntries(new FormData(form).entries());
        try {
            const res = await fetch("/api/rooms/" + encodeURIComponent(roomId) + "/authenticate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ password: data.password, displayName: data.displayName }),
            });
            const body = await res.json();
            if (!res.ok) throw new Error(body.error || "Failed to join.");
            sessionStorage.setItem("p2p_displayName", data.displayName);
            sessionStorage.setItem("p2p_roomPassword", data.password);
            sessionStorage.removeItem("p2p_isCreator");
            window.location.href = "/room/" + roomId;
        } catch (err) {
            showError(err.message);
            joinBtn.disabled = false;
        }
    });
})();