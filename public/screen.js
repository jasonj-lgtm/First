// Screen-side controller: requests a pairing QR, waits for a phone to pair,
// then opens a WebSocket and dispatches messages relayed from the phone to
// skills. Messages no skill claims fall back to the activity log.

import { renderingSkill } from "./skills/rendering.js";

const qrImg = document.getElementById("qr");
const statusEl = document.getElementById("status");
const refreshBtn = document.getElementById("refresh");
const logEl = document.getElementById("log");
const surfaceEl = document.getElementById("surface");

const skills = [renderingSkill];

let sessionId = null;
let pollTimer = null;
let ws = null;

function log(msg) {
  const line = document.createElement("div");
  line.textContent = `${new Date().toLocaleTimeString()} — ${msg}`;
  logEl.prepend(line);
}

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = `status ${cls}`;
}

async function createPairing() {
  stopPolling();
  closeSocket();
  refreshBtn.hidden = true;
  setStatus("Waiting for phone…", "pending");

  const res = await fetch("/api/pairing", { method: "POST" });
  const data = await res.json();
  sessionId = data.sessionId;
  qrImg.src = data.qrDataUrl;
  log("Pairing code generated.");
  startPolling();
}

function startPolling() {
  pollTimer = setInterval(async () => {
    const res = await fetch(`/api/pairing/status?session=${sessionId}`);
    if (!res.ok) return;
    const { status, deviceName } = await res.json();
    if (status === "connected") {
      stopPolling();
      setStatus(`Connected: ${deviceName || "phone"}`, "connected");
      log(`Phone paired (${deviceName || "phone"}).`);
      openSocket();
    } else if (status === "expired") {
      stopPolling();
      setStatus("Code expired", "expired");
      refreshBtn.hidden = false;
    }
  }, 1500);
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

function openSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws?session=${sessionId}`);
  ws.onopen = () => log("Live channel open.");
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "message") {
      const skill = skills.find((s) => s.canHandle(msg.data));
      if (skill) {
        skill.handle(msg.data, { surface: surfaceEl, log });
      } else {
        log(`Phone: ${JSON.stringify(msg.data)}`);
      }
    } else if (msg.type === "peer_disconnected") {
      log("Phone disconnected.");
    }
  };
  ws.onclose = () => log("Live channel closed.");
}

function closeSocket() {
  if (ws) {
    ws.close();
    ws = null;
  }
}

refreshBtn.addEventListener("click", createPairing);
createPairing();
