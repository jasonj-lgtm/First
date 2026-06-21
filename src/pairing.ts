import { randomUUID, randomBytes } from "node:crypto";

/** Lifecycle states for a pairing session. */
export type PairingStatus = "pending" | "connected" | "expired";

export interface PairingSession {
  /** Stable id for the session (also used as the WebSocket room). */
  id: string;
  /** Single-use secret the phone must present to claim the session. */
  token: string;
  status: PairingStatus;
  createdAt: number;
  expiresAt: number;
  /** Set once a phone has successfully paired. */
  deviceName?: string;
}

export interface PairingStoreOptions {
  /** How long a pending session stays valid, in milliseconds. */
  ttlMs?: number;
}

/**
 * In-memory registry of pairing sessions.
 *
 * A session starts life as `pending` when a screen requests a QR code, and
 * flips to `connected` once a phone presents the matching token. Expired
 * sessions are swept lazily on access and on an interval.
 */
export class PairingStore {
  private readonly sessions = new Map<string, PairingSession>();
  private readonly ttlMs: number;
  private sweeper?: ReturnType<typeof setInterval>;

  constructor(options: PairingStoreOptions = {}) {
    this.ttlMs = options.ttlMs ?? 5 * 60 * 1000; // 5 minutes
  }

  /** Create a new pending session and return it. */
  create(): PairingSession {
    const now = Date.now();
    const session: PairingSession = {
      id: randomUUID(),
      token: randomBytes(24).toString("base64url"),
      status: "pending",
      createdAt: now,
      expiresAt: now + this.ttlMs,
    };
    this.sessions.set(session.id, session);
    return session;
  }

  /** Look up a session, applying lazy expiry. */
  get(id: string): PairingSession | undefined {
    const session = this.sessions.get(id);
    if (!session) return undefined;
    if (session.status !== "connected" && Date.now() > session.expiresAt) {
      session.status = "expired";
    }
    return session;
  }

  /**
   * Attempt to claim a pending session with the token the phone scanned.
   * Returns the session on success, or an error reason on failure.
   */
  claim(
    id: string,
    token: string,
    deviceName: string,
  ): { ok: true; session: PairingSession } | { ok: false; reason: string } {
    const session = this.get(id);
    if (!session) return { ok: false, reason: "unknown_session" };
    if (session.status === "expired") return { ok: false, reason: "expired" };
    if (session.status === "connected") {
      return { ok: false, reason: "already_paired" };
    }
    if (session.token !== token) return { ok: false, reason: "bad_token" };

    session.status = "connected";
    session.deviceName = deviceName;
    return { ok: true, session };
  }

  /** Start the periodic sweep of expired sessions. */
  startSweeper(intervalMs = 60_000): void {
    if (this.sweeper) return;
    this.sweeper = setInterval(() => this.sweep(), intervalMs);
    this.sweeper.unref?.();
  }

  /** Stop the periodic sweep (useful for tests / shutdown). */
  stopSweeper(): void {
    if (this.sweeper) {
      clearInterval(this.sweeper);
      this.sweeper = undefined;
    }
  }

  private sweep(): void {
    const now = Date.now();
    for (const [id, session] of this.sessions) {
      if (session.status === "connected") continue;
      if (now > session.expiresAt + this.ttlMs) {
        this.sessions.delete(id);
      }
    }
  }
}
