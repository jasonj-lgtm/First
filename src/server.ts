import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, normalize } from "node:path";
import { WebSocketServer, WebSocket } from "ws";
import QRCode from "qrcode";
import { PairingStore } from "./pairing.js";

const HOST = process.env.HOST ?? "0.0.0.0";
const PORT = Number(process.env.PORT ?? 3000);
/**
 * Base URL the phone should reach. On a LAN this must be the machine's IP
 * (not localhost), otherwise the QR code won't resolve from the phone.
 */
const PUBLIC_URL = process.env.PUBLIC_URL ?? `http://${HOST}:${PORT}`;

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(__dirname, "..", "public");

const store = new PairingStore();
store.startSweeper();

/** Active WebSocket connections, keyed by pairing session id. */
const sockets = new Map<string, Set<WebSocket>>();

function addSocket(sessionId: string, ws: WebSocket): void {
  let set = sockets.get(sessionId);
  if (!set) {
    set = new Set();
    sockets.set(sessionId, set);
  }
  set.add(ws);
}

function removeSocket(sessionId: string, ws: WebSocket): void {
  const set = sockets.get(sessionId);
  if (!set) return;
  set.delete(ws);
  if (set.size === 0) sockets.delete(sessionId);
}

/** Broadcast a JSON message to every peer in a session except the sender. */
function broadcast(sessionId: string, payload: unknown, except?: WebSocket): void {
  const set = sockets.get(sessionId);
  if (!set) return;
  const data = JSON.stringify(payload);
  for (const ws of set) {
    if (ws !== except && ws.readyState === WebSocket.OPEN) {
      ws.send(data);
    }
  }
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(data),
  });
  res.end(data);
}

const CONTENT_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
};

async function serveStatic(res: ServerResponse, relPath: string): Promise<void> {
  // Prevent path traversal: resolve and confirm the result stays in PUBLIC_DIR.
  const safePath = normalize(join(PUBLIC_DIR, relPath));
  if (!safePath.startsWith(PUBLIC_DIR)) {
    sendJson(res, 403, { error: "forbidden" });
    return;
  }
  try {
    const file = await readFile(safePath);
    const ext = safePath.slice(safePath.lastIndexOf("."));
    res.writeHead(200, {
      "content-type": CONTENT_TYPES[ext] ?? "application/octet-stream",
    });
    res.end(file);
  } catch {
    sendJson(res, 404, { error: "not_found" });
  }
}

async function handleRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const url = new URL(req.url ?? "/", PUBLIC_URL);

  // 1. Create a pairing session + QR code for a screen to display.
  if (url.pathname === "/api/pairing" && req.method === "POST") {
    const session = store.create();
    // The phone opens this URL after scanning; it carries the one-use token.
    const pairUrl = `${PUBLIC_URL}/phone.html?session=${session.id}&token=${session.token}`;
    const qrDataUrl = await QRCode.toDataURL(pairUrl, { margin: 1, width: 320 });
    sendJson(res, 201, {
      sessionId: session.id,
      pairUrl,
      qrDataUrl,
      expiresAt: session.expiresAt,
    });
    return;
  }

  // 2. Poll a session's status (used by the screen while it waits).
  if (url.pathname === "/api/pairing/status" && req.method === "GET") {
    const id = url.searchParams.get("session") ?? "";
    const session = store.get(id);
    if (!session) {
      sendJson(res, 404, { error: "unknown_session" });
      return;
    }
    sendJson(res, 200, {
      status: session.status,
      deviceName: session.deviceName ?? null,
    });
    return;
  }

  // 3. Phone claims the session with the scanned token.
  if (url.pathname === "/api/pairing/claim" && req.method === "POST") {
    const body = await readBody(req);
    const { session: id, token, deviceName } = body as {
      session?: string;
      token?: string;
      deviceName?: string;
    };
    const result = store.claim(id ?? "", token ?? "", deviceName ?? "phone");
    if (!result.ok) {
      sendJson(res, 400, { error: result.reason });
      return;
    }
    broadcast(id ?? "", { type: "paired", deviceName: deviceName ?? "phone" });
    sendJson(res, 200, { ok: true, sessionId: result.session.id });
    return;
  }

  // Static files: index (screen) and phone client.
  if (url.pathname === "/" || url.pathname === "/index.html") {
    await serveStatic(res, "index.html");
    return;
  }
  if (req.method === "GET") {
    await serveStatic(res, url.pathname);
    return;
  }

  sendJson(res, 404, { error: "not_found" });
}

function readBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > 1_000_000) {
        reject(new Error("body_too_large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch {
        reject(new Error("invalid_json"));
      }
    });
    req.on("error", reject);
  });
}

const httpServer = createServer((req, res) => {
  handleRequest(req, res).catch((err) => {
    sendJson(res, 400, { error: String(err.message ?? err) });
  });
});

// WebSocket upgrade: clients connect to /ws?session=<id> to exchange messages.
const wss = new WebSocketServer({ noServer: true });

httpServer.on("upgrade", (req, socket, head) => {
  const url = new URL(req.url ?? "/", PUBLIC_URL);
  if (url.pathname !== "/ws") {
    socket.destroy();
    return;
  }
  const sessionId = url.searchParams.get("session") ?? "";
  const session = store.get(sessionId);
  if (!session || session.status === "expired") {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => {
    wss.emit("connection", ws, req, sessionId);
  });
});

wss.on("connection", (ws: WebSocket, _req: IncomingMessage, sessionId: string) => {
  addSocket(sessionId, ws);
  ws.send(JSON.stringify({ type: "welcome", sessionId }));

  ws.on("message", (raw) => {
    let payload: unknown;
    try {
      payload = JSON.parse(raw.toString());
    } catch {
      ws.send(JSON.stringify({ type: "error", error: "invalid_json" }));
      return;
    }
    // Relay whatever the peer sends to the other side of the connection.
    broadcast(sessionId, { type: "message", data: payload }, ws);
  });

  ws.on("close", () => {
    removeSocket(sessionId, ws);
    broadcast(sessionId, { type: "peer_disconnected" });
  });
});

httpServer.listen(PORT, HOST, () => {
  console.log(`Phone-connection server listening on ${PUBLIC_URL}`);
  console.log(`Open ${PUBLIC_URL}/ on a screen, then scan the QR with a phone.`);
});

export { httpServer, store };
