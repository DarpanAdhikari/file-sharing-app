window.P2P = window.P2P || {};

P2P.toast = (function () {
    const root = document.getElementById("toast-root");
    if (!root) {
        return { show() {}, success() {}, error() {} };
    }
    function show(message, type) {
        const el = document.createElement("div");
        el.className = "toast" + (type ? " toast--" + type : "");
        el.textContent = message;
        root.appendChild(el);
        setTimeout(() => {
            el.style.opacity = "0";
            el.style.transition = "opacity .3s";
            setTimeout(() => el.remove(), 300);
        }, 3200);
    }
    return {
        show,
        success: (m) => show(m, "success"),
        error: (m) => show(m, "error"),
    };
})();

P2P.escapeHtml = function (str) {
    return String(str).replace(/[&<>"']/g, function (c) {
        return {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
        }[c];
    });
};

P2P.formatBytes = function (bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    const val = bytes / Math.pow(1024, i);
    return (i === 0 ? val : val.toFixed(1)) + " " + units[i];
};

P2P.webrtcSupported = function () {
    return !!(
        window.RTCPeerConnection &&
        (window.RTCDataChannel || window.mozRTCPeerConnection)
    );
};

P2P.parseChatMessage = function (data) {
    if (typeof data !== "string") return null;
    let msg;
    try {
        msg = JSON.parse(data);
    } catch (e) {
        return null;
    }
    if (msg && msg.type === "chat" && typeof msg.text === "string") {
        return { type: "chat", text: msg.text };
    }
    return null;
};

P2P.getLocation = function () {
    return {
        protocol: window.location.protocol,
        host: window.location.host,
    };
};