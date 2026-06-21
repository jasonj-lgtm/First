// Phone-side controller: reads the session + token from the scanned QR URL,
// claims the pairing session, then opens a WebSocket back to the screen.

const stateEl = document.getElementById("state");
const chatEl = document.getElementById("chat");
const textEl = document.getElementById("text");
const sendBtn = document.getElementById("send");

const params = new URLSearchParams(location.search);
const session = params.get("session");
const token = params.get("token");

let ws = null;

function setState(text, cls = "") {
  stateEl.textContent = text;
  stateEl.className = `state ${cls}`;
}

async function pair() {
  if (!session || !token) {
    setState("Invalid pairing link.", "err");
    return;
  }
  const deviceName =
    /iPhone|iPad/.test(navigator.userAgent) ? "iPhone" :
    /Android/.test(navigator.userAgent) ? "Android phone" : "phone";

  const res = await fetch("/api/pairing/claim", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session, token, deviceName }),
  });

  if (!res.ok) {
    const { error } = await res.json().catch(() => ({ error: "failed" }));
    setState(`Pairing failed: ${error}`, "err");
    return;
  }

  setState("Connected ✓", "ok");
  chatEl.hidden = false;
  openSocket();
}

function openSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws?session=${session}`);
  ws.onclose = () => setState("Disconnected", "err");
}

sendBtn.addEventListener("click", () => {
  const value = textEl.value.trim();
  if (!value || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ text: value }));
  textEl.value = "";
});

textEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendBtn.click();
});

pair();
