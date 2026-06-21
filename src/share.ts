import { spawn } from "node:child_process";
import { createWriteStream } from "node:fs";
import { chmod, mkdir, access } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { tmpdir } from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import QRCode from "qrcode";
import { WebSocket } from "ws";

const execFileAsync = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN_DIR = join(__dirname, "..", ".bin");

/** Resolve the cloudflared download asset for the current platform. */
function cloudflaredAsset(): { url: string; archive: "raw" | "tgz"; binName: string } {
  const base =
    "https://github.com/cloudflare/cloudflared/releases/latest/download";
  const arch = process.arch === "arm64" ? "arm64" : "amd64";
  if (process.platform === "win32") {
    return { url: `${base}/cloudflared-windows-${arch}.exe`, archive: "raw", binName: "cloudflared.exe" };
  }
  if (process.platform === "darwin") {
    // macOS ships as a .tgz containing the `cloudflared` binary.
    return { url: `${base}/cloudflared-darwin-${arch}.tgz`, archive: "tgz", binName: "cloudflared" };
  }
  return { url: `${base}/cloudflared-linux-${arch}`, archive: "raw", binName: "cloudflared" };
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

/** Download (and extract, on macOS) cloudflared into .bin, returning its path. */
async function ensureCloudflared(): Promise<string> {
  // Prefer a system install if present.
  try {
    await execFileAsync(process.platform === "win32" ? "where" : "which", ["cloudflared"]);
    return "cloudflared";
  } catch {
    // fall through to local download
  }

  const { url, archive, binName } = cloudflaredAsset();
  const binPath = join(BIN_DIR, binName);
  if (await fileExists(binPath)) return binPath;

  await mkdir(BIN_DIR, { recursive: true });
  console.log("Downloading cloudflared (one-time setup)…");
  const res = await fetch(url, { redirect: "follow" });
  if (!res.ok || !res.body) {
    throw new Error(`Failed to download cloudflared: HTTP ${res.status}`);
  }

  if (archive === "tgz") {
    const tgzPath = join(tmpdir(), `cloudflared-${Date.now()}.tgz`);
    await pipeline(Readable.fromWeb(res.body as any), createWriteStream(tgzPath));
    await execFileAsync("tar", ["-xzf", tgzPath, "-C", BIN_DIR]);
  } else {
    await pipeline(Readable.fromWeb(res.body as any), createWriteStream(binPath));
  }
  if (process.platform !== "win32") {
    await chmod(binPath, 0o755);
  }
  return binPath;
}

/** Launch a quick tunnel and resolve with the public https URL it prints. */
function startTunnel(bin: string, port: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(
      bin,
      ["tunnel", "--no-autoupdate", "--url", `http://localhost:${port}`],
      { stdio: ["ignore", "pipe", "pipe"] },
    );

    const urlRe = /https:\/\/[a-z0-9-]+\.trycloudflare\.com/i;
    let settled = false;
    const onData = (buf: Buffer) => {
      const match = buf.toString().match(urlRe);
      if (match && !settled) {
        settled = true;
        resolve(match[0]);
      }
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData); // cloudflared logs the URL on stderr

    child.on("error", reject);
    child.on("exit", (code) => {
      if (!settled) reject(new Error(`cloudflared exited early (code ${code})`));
    });

    setTimeout(() => {
      if (!settled) reject(new Error("Timed out waiting for tunnel URL"));
    }, 30_000);
  });
}

async function main(): Promise<void> {
  process.env.NO_AUTOSTART = "1";
  // Import after NO_AUTOSTART is set so the server doesn't bind on its own.
  const { start, store, PORT } = await import("./server.js");

  await start(); // listening locally on PORT

  let publicUrl: string;
  try {
    const bin = await ensureCloudflared();
    publicUrl = await startTunnel(bin, PORT);
  } catch (err) {
    console.error("\nCould not start a public tunnel:", (err as Error).message);
    console.error(
      "Install cloudflared manually (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)\n" +
        "or set PUBLIC_URL yourself and use `npm start`.",
    );
    process.exit(1);
  }

  // Make every QR code and pairing link use the public URL.
  process.env.PUBLIC_URL = publicUrl;

  // Create one pairing session up front so scanning the QR pairs the phone
  // directly. The terminal plays the role of the "screen".
  const session = store.create();
  const pairUrl = `${publicUrl}/phone.html?session=${session.id}&token=${session.token}`;
  const qr = await QRCode.toString(pairUrl, { type: "terminal", small: true });

  console.log("\n========================================================");
  console.log("  Your phone connection is live. Scan this on your phone:");
  console.log("========================================================\n");
  console.log(qr);
  console.log(`  Or open this link on the phone:\n  ${pairUrl}\n`);
  console.log(`  (Public address: ${publicUrl})`);
  console.log("  Waiting for your phone to connect… (Ctrl+C to stop)\n");

  // Act as the screen side: watch the session for the phone and relay messages.
  const ws = new WebSocket(`ws://localhost:${PORT}/ws?session=${session.id}`);
  ws.on("message", (raw) => {
    const msg = JSON.parse(raw.toString());
    if (msg.type === "paired") {
      console.log(`✅ Phone connected: ${msg.deviceName ?? "phone"}`);
      console.log("   Type in the phone's box and messages will appear here.\n");
    } else if (msg.type === "message") {
      console.log(`📱 Phone: ${JSON.stringify(msg.data)}`);
    } else if (msg.type === "peer_disconnected") {
      console.log("⚠️  Phone disconnected.");
    }
  });
  ws.on("error", (e) => console.error("Watcher socket error:", e.message));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
