// Phone-side controller: reads the session + token from the scanned QR URL,
// claims the pairing session, then opens a WebSocket back to the screen.

const stateEl = document.getElementById("state");
const chatEl = document.getElementById("chat");
const textEl = document.getElementById("text");
const sendBtn = document.getElementById("send");
const kindEl = document.getElementById("kind");
const clearBtn = document.getElementById("clear");

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

function send(payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(payload));
  return true;
}

sendBtn.addEventListener("click", () => {
  const value = textEl.value.trim();
  if (!value) return;
  const kind = kindEl.value;
  // "message" keeps the original plain chat payload; the render kinds are
  // handled by the screen's rendering skill.
  const payload =
    kind === "message"
      ? { text: value }
      : { skill: "render", kind, content: value };
  if (send(payload)) textEl.value = "";
});

clearBtn.addEventListener("click", () => {
  send({ skill: "render", kind: "clear" });
});

textEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
});

pair();
