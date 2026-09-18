(function () {
    if (!window.P2P) window.P2P = {};

    const CHUNK_SIZE = 64 * 1024;

    function Peer(roomId, sid, iceConfig, callbacks) {
        this.roomId = roomId;
        this.sid = sid;
        this.callbacks = callbacks || {};
        this.pc = new RTCPeerConnection(iceConfig || { iceServers: [] });
        this.channel = null;
        this.channelReady = false;

        const sendBuffer = [];
        let awaiting = false;

        const self = this;

        function tryFlush() {
            if (awaiting || !self.channel || !self.channelReady) return;
            while (sendBuffer.length > 0) {
                const data = sendBuffer.shift();
                if (self.channel.bufferedAmount > 1024 * 1024) {
                    sendBuffer.unshift(data);
                    awaiting = true;
                    self.channel.onbufferedamountlow = function () {
                        awaiting = false;
                        self.channel.onbufferedamountlow = null;
                        tryFlush();
                    };
                    return;
                }
                try {
                    self.channel.send(data);
                } catch (e) {
                    if (self.callbacks.onError) self.callbacks.onError(e);
                }
            }
        }

        this.send = function (data) {
            sendBuffer.push(data);
            tryFlush();
        };

        this.sendChat = function (text) {
            this.send(JSON.stringify({ type: "chat", text: String(text).slice(0, 4000) }));
        };

        this.createOffer = async function () {
            this.channel = this.pc.createDataChannel("file-transfer", {
                ordered: true,
            });
            this.setupChannel(this.channel);
            const offer = await this.pc.createOffer();
            await this.pc.setLocalDescription(offer);
            this.callbacks.onSignal("offer", { sdp: this.pc.localDescription });
        };

        this.createAnswer = async function (offer) {
            await this.pc.setRemoteDescription(offer);
            this.pc.ondatachannel = (e) => {
                this.channel = e.channel;
                this.setupChannel(this.channel);
            };
            const answer = await this.pc.createAnswer();
            await this.pc.setLocalDescription(answer);
            this.callbacks.onSignal("answer", { sdp: this.pc.localDescription });
        };

        this.acceptAnswer = async function (answer) {
            await this.pc.setRemoteDescription(answer);
        };

        this.addIce = function (candidate) {
            this.pc.addIceCandidate(new RTCIceCandidate(candidate)).catch(() => {});
        };

        this.setupChannel = function (ch) {
            ch.binaryType = "arraybuffer";
            ch.onopen = () => {
                this.channelReady = true;
                if (this.callbacks.onOpen) this.callbacks.onOpen();
                tryFlush();
            };
            ch.onclose = () => {
                if (this.callbacks.onClose) this.callbacks.onClose();
            };
            ch.onmessage = (e) => {
                if (this.callbacks.onMessage) this.callbacks.onMessage(e.data, ch);
            };
        };

        this.pc.onicecandidate = (e) => {
            if (e.candidate) {
                this.callbacks.onSignal("ice", e.candidate);
            }
        };
        this.pc.onconnectionstatechange = () => {
            if (this.callbacks.onState) {
                this.callbacks.onState(this.pc.connectionState);
            }
        };

        this.close = function () {
            try {
                if (this.channel) this.channel.close();
                this.pc.close();
            } catch (e) {}
        };
    }

    function FileSender(peer, file, callbacks) {
        this.name = file.name;
        this.size = file.size;
        this.file = file;
        this.offset = 0;
        this.cancelled = false;
        this.peer = peer;
        this.callbacks = callbacks || {};

        const readChunk = (offset) =>
            new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = () => reject(reader.error);
                reader.readAsArrayBuffer(this.file.slice(offset, offset + CHUNK_SIZE));
            });

        this.start = async function () {
            const meta = {
                type: "file-meta",
                name: this.name,
                size: this.size,
            };
            peer.send(JSON.stringify(meta));
            if (this.callbacks.onStart) this.callbacks.onStart(this);

            while (this.offset < this.size && !this.cancelled) {
                const chunk = await readChunk(this.offset);
                const header = new Uint8Array(4);
                new DataView(header.buffer).setUint32(0, this.offset, false);
                const buf = new Uint8Array(chunk.byteLength + 4);
                buf.set(header, 0);
                buf.set(new Uint8Array(chunk), 4);
                peer.send(buf.buffer);
                this.offset += chunk.byteLength;
                if (this.callbacks.onProgress) this.callbacks.onProgress(this.offset, this.size);
            }

            if (this.cancelled) {
                if (this.callbacks.onCancel) this.callbacks.onCancel(this);
                return;
            }
            peer.send(JSON.stringify({ type: "file-end", name: this.name }));
            if (this.callbacks.onDone) this.callbacks.onDone(this);
        };

        this.cancel = function () {
            this.cancelled = true;
        };
    }

    function FileReceiver() {
        this.files = {};
        this.buffers = {};

        this.handle = function (data, channel) {
            if (typeof data === "string") {
                let msg;
                try {
                    msg = JSON.parse(data);
                } catch (e) {
                    return;
                }
                if (msg.type === "file-meta") {
                    this.buffers[msg.name] = new Uint8Array(msg.size);
                    this.files[msg.name] = { name: msg.name, size: msg.size, received: 0 };
                    if (window.P2P.onReceiveMeta) window.P2P.onReceiveMeta(this.files[msg.name]);
                } else if (msg.type === "file-end") {
                    const f = this.files[msg.name];
                    if (f) {
                        const blob = new Blob([this.buffers[msg.name]]);
                        if (window.P2P.onReceiveDone) window.P2P.onReceiveDone(f, blob);
                    }
                }
                return;
            }

            if (data instanceof ArrayBuffer || ArrayBuffer.isView(data)) {
                const bytes = new Uint8Array(data);
                const view = new DataView(bytes.buffer);
                const offset = view.getUint32(0, false);
                const chunk = bytes.slice(4);
                const fileName = findNameForOffset(this, offset, chunk.byteLength);
                if (!fileName) return;
                this.buffers[fileName].set(chunk, offset);
                const f = this.files[fileName];
                f.received += chunk.byteLength;
                if (window.P2P.onReceiveProgress) window.P2P.onReceiveProgress(f);
            }
        };
    }

    function findNameForOffset(receiver, offset, length) {
        for (const name in receiver.files) {
            const f = receiver.files[name];
            if (offset < f.size && offset + length <= f.size) return name;
        }
        return null;
    }

    window.P2P.Peer = Peer;
    window.P2P.FileSender = FileSender;
    window.P2P.FileReceiver = FileReceiver;
    window.P2P.CHUNK_SIZE = CHUNK_SIZE;
})();