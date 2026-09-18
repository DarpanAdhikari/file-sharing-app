(function () {
    if (!window.P2P.webrtcSupported()) {
        alert("Your browser does not support WebRTC file transfer.");
        return;
    }

    const ROOM_ID = window.ROOM_ID;
    const displayName = sessionStorage.getItem("p2p_displayName") || "Guest";
    const password = sessionStorage.getItem("p2p_roomPassword") || "";
    const isCreator = sessionStorage.getItem("p2p_isCreator") === "1";

    const roomNameEl = document.getElementById("room-name");
    const roomCodeEl = document.getElementById("room-code");
    const connEl = document.getElementById("conn-status");
    const peerListEl = document.getElementById("peer-list");
    const retryBtn = document.getElementById("retry-btn");
    const connHelp = document.getElementById("conn-help");
    const copyBtn = document.getElementById("copy-invite-btn");
    const roleHint = document.getElementById("role-hint");
    const queueListEl = document.getElementById("queue-list");
    const sendBtn = document.getElementById("send-btn");
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const transfersEl = document.getElementById("transfers");

    // chat elements
    const chatLogEl = document.getElementById("chat-log");
    const chatForm = document.getElementById("chat-form");
    const chatText = document.getElementById("chat-text");
    const chatSend = document.getElementById("chat-send");
    const chatEmpty = chatLogEl.querySelector(".chat-empty");

    let socket = io({ transports: ["websocket"] });
    let self = null;          // P2P.Peer
    let roomType = "both";
    let role = "sender";      // who this client plays
    let queue = [];           // File objects
    let receiver = new P2P.FileReceiver();
    let peerName = "Peer";    // name of the connected peer
    let restartAttempts = 0;
    const senders = {};       // transfer id -> FileSender
    const startedAt = {};     // transfer id -> timestamp
    let peerConnected = false;

    // ---- connection status ----
    function setStatus(text, cls) {
        connEl.innerHTML = `<span class="status-dot status-dot--${cls}"></span>${P2P.escapeHtml(text)}`;
    }
    setStatus("Connecting…", "warn");

    function roomCode() {
        return ROOM_ID.slice(0, 6).toUpperCase();
    }

    // ---- copy invite link ----
    if (copyBtn) {
        copyBtn.addEventListener("click", async () => {
            const url = window.location.origin + "/join/" + ROOM_ID;
            try {
                await navigator.clipboard.writeText(url);
                P2P.toast.success("Invite link copied!");
            } catch (e) {
                P2P.toast.error("Could not copy link.");
            }
        });
    }

    // ---- retry connection ----
    if (retryBtn) {
        retryBtn.addEventListener("click", () => {
            if (!self) return;
            setStatus("Retrying connection…", "warn");
            restartAttempts = 0;
            self.restartIce();
        });
    }

    function showRetry() {
        if (retryBtn) retryBtn.classList.remove("hidden");
        if (connHelp) connHelp.style.display = "block";
    }

    // ---- transfer UI helpers ----
    function addTransferItem(id, name, size, mode) {
        const box = document.createElement("div");
        box.className = "transfer-item";
        box.id = id;
        box.innerHTML = `
            <div class="transfer-item__head">
                <span class="transfer-item__name">${P2P.escapeHtml(name)}</span>
                <button class="btn btn--ghost cancel-btn" data-id="${id}">Cancel</button>
            </div>
            <div class="transfer-item__meta">${mode} · 0%</div>
            <div class="progress"><div class="progress__bar"></div></div>
        `;
        transfersEl.querySelector(".empty-state")?.remove();
        transfersEl.appendChild(box);
        return box;
    }

    function updateTransfer(id, pct, text) {
        const box = document.getElementById(id);
        if (!box) return;
        const bar = box.querySelector(".progress__bar");
        bar.style.width = Math.min(100, pct) + "%";
        if (pct >= 100) bar.classList.add("progress__bar--complete");
        const meta = box.querySelector(".transfer-item__meta");
        if (text) meta.textContent = text;
        const cancelBtn = box.querySelector(".cancel-btn");
        if (pct >= 100 && cancelBtn) cancelBtn.remove();
    }

    function transferSpeed(id, bytesDone) {
        const start = startedAt[id];
        if (!start) return "";
        const secs = (Date.now() - start) / 1000;
        if (secs < 0.5 || bytesDone <= 0) return "";
        return P2P.formatBytes(bytesDone / secs) + "/s";
    }

    function finalizeTransfer(id, blob, name) {
        const box = document.getElementById(id);
        const meta = box ? box.querySelector(".transfer-item__meta") : null;
        if (meta) {
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = name;
            link.className = "btn btn--primary";
            link.textContent = "Download";
            box.querySelector(".transfer-item__head").appendChild(link);
            meta.textContent = "✓ Completed";
        }
    }

    // ---- queue rendering ----
    function renderQueue() {
        queueListEl.innerHTML = "";
        queue.forEach((f, i) => {
            const row = document.createElement("div");
            row.className = "transfer-item";
            row.innerHTML = `
                <div class="transfer-item__head">
                    <span class="transfer-item__name">${P2P.escapeHtml(f.name)}</span>
                    <button class="btn btn--ghost remove-file" data-i="${i}">Remove</button>
                </div>
                <div class="transfer-item__meta">${P2P.formatBytes(f.size)}</div>
            `;
            queueListEl.appendChild(row);
        });
        sendBtn.disabled = queue.length === 0;
    }

    queueListEl.addEventListener("click", (e) => {
        const btn = e.target.closest(".remove-file");
        if (!btn) return;
        queue.splice(Number(btn.dataset.i), 1);
        renderQueue();
    });

    const MAX_FILE_SIZE = window.MAX_FILE_SIZE || 200 * 1024 * 1024;

    function addFiles(files) {
        for (const f of files) {
            if (f.size > MAX_FILE_SIZE) {
                P2P.toast.error(`"${f.name}" exceeds the 200 MB limit.`);
                continue;
            }
            if (f.size > 100 * 1024 * 1024) {
                P2P.toast.show(`Large file: "${f.name}" — transfer may be slow on cellular.`);
            }
            queue.push(f);
        }
        renderQueue();
    }

    dropzone.addEventListener("click", () => fileInput.click());
    ["dragover", "dragenter"].forEach((ev) =>
        dropzone.addEventListener(ev, (e) => {
            e.preventDefault();
            dropzone.classList.add("dropzone--active");
        })
    );
    ["dragleave", "drop"].forEach((ev) =>
        dropzone.addEventListener(ev, (e) => {
            e.preventDefault();
            dropzone.classList.remove("dropzone--active");
        })
    );
    dropzone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
    fileInput.addEventListener("change", () => {
        addFiles(fileInput.files);
        fileInput.value = "";
    });

    sendBtn.addEventListener("click", () => {
        if (!self || !self.channelReady) {
            P2P.toast.error("Waiting for a connected peer.");
            return;
        }
        const files = queue.splice(0, queue.length);
        renderQueue();
        for (const f of files) {
            const id = "snd-" + Date.now() + "-" + Math.floor(Math.random() * 1000);
            startedAt[id] = Date.now();
            const item = addTransferItem(id, f.name, f.size, "Sending");
            const sender = new P2P.FileSender(self, f, {
                onProgress: (off, size) => {
                    const speed = transferSpeed(id, off);
                    updateTransfer(
                        id,
                        (off / size) * 100,
                        `Sending · ${P2P.formatBytes(off)} / ${P2P.formatBytes(size)}` + (speed ? ` · ${speed}` : "")
                    );
                },
                onDone: () => updateTransfer(id, 100, "Sent"),
                onCancel: () => updateTransfer(id, 0, "Cancelled"),
                onError: (err) => { P2P.toast.error("Send failed"); console.error(err); },
            });
            senders[id] = sender;
            sender.start();
        }
    });

    transfersEl.addEventListener("click", (e) => {
        const btn = e.target.closest(".cancel-btn");
        if (btn) {
            const id = btn.dataset.id;
            const s = senders[id];
            if (s) {
                s.cancel();
                updateTransfer(id, 0, "Cancelled");
            } else {
                updateTransfer(id, 0, "Cancelled");
            }
        }
    });

    // ---- WebRTC receive callbacks ----
    P2P.onReceiveMeta = function (f) {
        const id = "rcv-" + Date.now();
        f._id = id;
        startedAt[id] = Date.now();
        addTransferItem(id, f.name, f.size, "Receiving");
    };
    P2P.onReceiveProgress = function (f) {
        const id = f._id;
        const speed = transferSpeed(id, f.received);
        updateTransfer(
            id,
            (f.received / f.size) * 100,
            `Receiving · ${P2P.formatBytes(f.received)} / ${P2P.formatBytes(f.size)}` + (speed ? ` · ${speed}` : "")
        );
    };
    P2P.onReceiveDone = function (f, blob) {
        finalizeTransfer(f._id, blob, f.name);
    };
    P2P.onReceiveCancel = function (f) {
        if (f._id) updateTransfer(f._id, 0, "Cancelled");
        else P2P.toast.info && P2P.toast.info("Transfer cancelled by sender.");
    };

    // ---- tabs ----
    document.querySelectorAll(".tab").forEach((tab) =>
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tab").forEach((t) => t.classList.remove("tab--active"));
            document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("tab-panel--active"));
            tab.classList.add("tab--active");
            document.getElementById("tab-" + tab.dataset.tab).classList.add("tab-panel--active");
            if (tab.dataset.tab === "chat") chatText.focus();
        })
    );

    // ---- chat ----
    function appendChat(text, isSelf, name) {
        chatEmpty?.remove();
        const div = document.createElement("div");
        div.className = "chat-msg " + (isSelf ? "chat-msg--self" : "chat-msg--peer");
        const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        div.innerHTML = `
            <span class="chat-msg__name">${P2P.escapeHtml(name)}</span>
            <span>${P2P.escapeHtml(text)}</span>
            <span class="chat-msg__time">${time}</span>
        `;
        chatLogEl.appendChild(div);
        chatLogEl.scrollTop = chatLogEl.scrollHeight;
    }

    function enableChat() {
        chatText.disabled = false;
        chatSend.disabled = false;
    }

    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = chatText.value.trim();
        if (!text || !self || !self.channelReady) return;
        self.sendChat(text);
        appendChat(text, true, displayName);
        chatText.value = "";
    });

    // ---- SocketIO ----
    function teardownPeer() {
        if (self) {
            try { self.close(); } catch (e) {}
        }
        self = null;
        peerConnected = false;
    }

    function makePeer(data) {
        teardownPeer();
        self = new P2P.Peer(ROOM_ID, data.yourSid, data.iceConfig, {
            onSignal: (type, signal) =>
                socket.emit("signal", { roomId: ROOM_ID, target: null, signal }),
            onOpen: () => {
                peerConnected = true;
                setStatus("Connected", "ok");
                enableChat();
                if (role === "sender") P2P.toast.success("Connected — send your files!");
            },
            onClose: () => {
                peerConnected = false;
                setStatus("Disconnected", "err");
            },
            onState: (st) => {
                if (st === "connected") {
                    setStatus("Connected", "ok");
                    if (retryBtn) retryBtn.classList.add("hidden");
                    if (connHelp) connHelp.style.display = "none";
                }
                if (st === "failed") {
                    setStatus("Connection failed", "err");
                    if (restartAttempts < 2) {
                        restartAttempts += 1;
                        P2P.toast.show("Connection lost — retrying…");
                        self.restartIce();
                    } else {
                        showRetry();
                    }
                }
            },
            onMessage: (data, ch) => {
                const chat = P2P.parseChatMessage(data);
                if (chat) {
                    appendChat(chat.text, false, peerName);
                } else {
                    receiver.handle(data, ch);
                }
            },
        });
        return self;
    }

    socket.on("connect", () => {
        setStatus("Authenticating…", "warn");
        socket.emit("authenticate", {
            roomId: ROOM_ID,
            password,
            displayName,
            isCreator,
        });
    });

    socket.on("authenticated", (data) => {
        roomType = data.room.type;
        setStatus("Consulting peers…", "warn");
        makePeer(data);

        roomNameEl.textContent = data.room.name;
        roomCodeEl.textContent = roomCode();
        setRoleHints();
        renderPeers(data.room);
        socket.emit("join", { roomId: ROOM_ID });

        // Creator always initiates the connection (kills glare: only one
        // side ever creates offers). If a peer is already present (e.g. this
        // socket just reconnected), offer immediately.
        const others = (data.peers || []).filter((p) => p.sid !== data.yourSid);
        if (isCreator && others.length > 0) {
            self.sid = others[0].sid;
            self.createOffer().catch((e) => console.error(e));
        }
    });

    socket.on("auth_failed", (data) => {
        setStatus("Incorrect password", "err");
        P2P.toast.error(data.error || "Authentication failed.");
        sessionStorage.removeItem("p2p_roomPassword");
        setTimeout(() => (window.location.href = "/join/" + ROOM_ID), 1500);
    });

    socket.on("error", (data) => {
        setStatus(data.error || "Error", "err");
        P2P.toast.error(data.error || "Something went wrong.");
        const msg = data.error || "";
        if (/does not exist|has expired|is full/i.test(msg)) {
            setTimeout(() => (window.location.href = "/join/" + ROOM_ID), 1500);
        }
    });

    socket.on("disconnect", () => {
        setStatus("Reconnecting…", "warn");
    });

    socket.on("peer_joined", (data) => {
        if (!self) return;
        const name = data.peerName;
        if (name) P2P.toast.show(`${name} joined the room.`);
        if (isCreator) {
            self.sid = data.peer;
            setStatus("Negotiating connection…", "warn");
            self.createOffer().catch((e) => console.error(e));
        }
    });

    socket.on("peer_left", (data) => {
        if (data && data.peer) {
            P2P.toast.show("A device left the room.");
        }
        renderPeers();
    });

    socket.on("signal", (data) => {
        if (!self) return;
        if (data.signal && data.signal.sdp && data.signal.sdp.type === "offer") {
            self.sid = data.from;
            setStatus("Negotiating connection…", "warn");
            self.createAnswer(data.signal).catch((e) => console.error(e));
        } else if (data.signal && data.signal.sdp && data.signal.sdp.type === "answer") {
            self.acceptAnswer(data.signal).catch((e) => console.error(e));
        } else if (data.signal && data.signal.candidate) {
            self.addIce(data.signal);
        }
    });

    socket.on("room_updated", (data) => {
        renderPeers(data.room);
    });

    socket.on("peer_joined_broadcast", () => {});

    function renderPeers(roomData) {
        const room = roomData;
        peerListEl.innerHTML = "";
        if (!room) {
            peerListEl.innerHTML = "<li>Connected to room</li>";
            return;
        }
        room.peers?.forEach?.((p) => {
            const li = document.createElement("li");
            li.innerHTML = `<span>${P2P.escapeHtml(p.name)}</span><span class="muted">${p.isCreator ? "Creator" : "Connected"}</span>`;
            peerListEl.appendChild(li);
            if (!p.isCreator) peerName = p.name;
        });
        if (!room.peers || room.peers.length === 0) {
            peerListEl.innerHTML = "<li>Waiting for devices…</li>";
        }
    }

    function setRoleHints() {
        role = roomType === "receive" ? "receiver" : "sender";
        if (role === "receiver") {
            document.getElementById("send-zone").style.display = "none";
            roleHint.textContent = "You are set to receive files. Waiting for a sender to connect…";
        } else {
            roleHint.textContent = "Select files below and send once a device connects.";
        }
    }

    // heartbeat to keep room alive
    setInterval(() => socket.emit("heartbeat", { roomId: ROOM_ID }), 20000);
})();