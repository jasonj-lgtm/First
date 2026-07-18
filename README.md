# Phone Connection

QR-code pairing and a live WebSocket channel between a phone and this server.

A screen displays a QR code; you scan it with a phone, the phone claims the
pairing session with a one-time token, and a WebSocket opens so the two sides
can exchange messages in real time.

## How it works

```
 ┌────────┐   1. POST /api/pairing      ┌──────────┐
 │ Screen │ ──────────────────────────► │  Server  │
 │        │ ◄── QR (session + token) ── │          │
 └────────┘                             └──────────┘
     │  shows QR                              ▲
     │                                        │ 3. POST /api/pairing/claim
     ▼  2. scan                               │    (session + token)
 ┌────────┐ ───────────────────────────────► │
 │ Phone  │                                   │
 └────────┘ ◄── 4. WebSocket /ws ───────────►┘
       both sides connect to /ws?session=<id> and relay messages
```

1. The screen calls `POST /api/pairing` and renders the returned QR code.
2. The phone scans the QR, which opens `/phone.html?session=…&token=…`.
3. The phone calls `POST /api/pairing/claim` to consume the one-time token.
4. Both sides connect to `ws://…/ws?session=<id>` and exchange JSON messages.

Pairing sessions expire after 5 minutes if no phone claims them.

## Skills

Once paired, messages from the phone are dispatched to **skills** on the
screen (`public/skills/`). A skill declares which messages it handles via
`canHandle(data)`; anything unclaimed falls back to the screen's activity log.

### Rendering skill

The first skill: the phone sends content and the screen renders it live on a
surface above the pairing card. On the phone, pick how the screen should show
what you type:

| Kind       | Payload                                            | Screen behaviour                          |
| ---------- | -------------------------------------------------- | ----------------------------------------- |
| `text`     | `{ skill: "render", kind: "text", content }`       | Big centred text.                         |
| `markdown` | `{ skill: "render", kind: "markdown", content }`   | Safe Markdown subset (see below).         |
| `image`    | `{ skill: "render", kind: "image", content: url }` | Shows the image (`http(s)` URLs only).    |
| `clear`    | `{ skill: "render", kind: "clear" }`               | Empties and hides the surface.            |

Each render replaces the previous content. The Markdown renderer HTML-escapes
input first and supports only `#`/`##`/`###` headings, `- ` lists, `**bold**`,
`*italic*`, `` `code` `` and `[text](https://…)` links — phone input can never
inject raw HTML into the screen.

## Run it

### Option A — public link from anywhere (easiest for a phone)

```bash
npm install
npm run share
```

This starts the server, opens a free [Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
(no account needed — `cloudflared` is downloaded automatically the first time),
and prints a **QR code right in your terminal**. Scan it with your phone's
camera from anywhere — no shared Wi-Fi required — and the phone pairs
immediately. Messages you type on the phone then show up in the terminal.

The public address looks like `https://something-random.trycloudflare.com` and
changes each run. Press `Ctrl+C` to stop.

> Needs normal outbound internet. Locked-down networks that block
> `api.trycloudflare.com` (some corporate or sandboxed environments) can't open
> the tunnel — use Option B there, or install `cloudflared` and set up a named
> tunnel.

### Option B — same Wi-Fi (LAN)

```bash
npm install
PUBLIC_URL=http://192.168.1.50:3000 npm run dev   # use YOUR computer's IP
```

Then open `http://192.168.1.50:3000/` on a screen and scan the code with a phone
on the same network. Replace `192.168.1.50` with your computer's actual local IP
(macOS: System Settings → Wi-Fi → Details; Windows: `ipconfig`). `localhost` and
the literal text `<your-machine-ip>` will **not** work from the phone.

## Configuration

| Env var      | Default                 | Description                                  |
| ------------ | ----------------------- | -------------------------------------------- |
| `HOST`       | `0.0.0.0`               | Interface to bind.                           |
| `PORT`       | `3000`                  | Port to listen on.                           |
| `PUBLIC_URL` | `http://<host>:<port>`  | URL the phone uses (must be reachable by it).|

## HTTP API

| Method | Path                    | Purpose                                       |
| ------ | ----------------------- | --------------------------------------------- |
| POST   | `/api/pairing`          | Create a session, return QR + pairing URL.    |
| GET    | `/api/pairing/status`   | Poll a session's status (`?session=<id>`).    |
| POST   | `/api/pairing/claim`    | Phone claims a session with its token.        |
| WS     | `/ws?session=<id>`      | Live bidirectional message channel.           |

## Project layout

```
src/
  pairing.ts   # in-memory pairing session store (tokens, expiry)
  server.ts    # HTTP + WebSocket server, static file serving
  share.ts     # public-link launcher: cloudflared tunnel + terminal QR
public/
  index.html   # screen: shows the QR code + render surface
  screen.js    # screen controller, dispatches messages to skills
  phone.html   # phone: lands here after scanning
  phone.js     # phone controller
  skills/
    rendering.js  # rendering skill: text / markdown / image / clear
tools/
  reveal_builder.py  # That 1 Painter before/after reveal reel builder (ffmpeg + Pillow)
.claude/skills/rendering/
  SKILL.md     # That 1 Painter rendering-skill playbook (brand standard + QA rubric)
```

## Notes

This is a scaffold using an in-memory store, so sessions are lost on restart and
it does not scale across multiple server instances. For production, back the
`PairingStore` with a shared store (e.g. Redis) and serve over HTTPS so the
phone can use `wss://` and the camera API where required.
