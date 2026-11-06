import { readFile } from "node:fs/promises";
import { type IncomingMessage, type Server, type ServerResponse, createServer } from "node:http";
import { extname, join, resolve, sep } from "node:path";

import { type Browser, type BrowserContext } from "playwright";

import { encodeWireMessage } from "../../src/shared/protocol/wire-codec.ts";
import { GAME_ID, LIVE_CHECKPOINTS, type Viewport } from "./model.ts";

export const APP_ROOT = resolve(import.meta.dirname, "../..");
const DIST = join(APP_ROOT, "dist-dev");
const ASSET_PREFIX = "/game-assets/v2/";
const REPLAY_FIXTURE = join(APP_ROOT, "src/fixtures/replays/four_kans.msgpack");
const TRANSCRIPT_FIXTURE = join(APP_ROOT, "src/fixtures/seat-scenarios/call_prompt_seat_1.json");

const CONTENT_TYPES: Readonly<Record<string, string>> = {
    ".css": "text/css",
    ".html": "text/html",
    ".js": "text/javascript",
    ".msgpack": "application/msgpack",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
};

/** The fixture server's origin and, for each live checkpoint, the socket frames its mocked game server sends. */
export interface Fixtures {
    readonly origin: string;
    readonly frames: ReadonlyMap<string, readonly Uint8Array[]>;
}

interface ReceivedEvent {
    readonly kind: "received";
    readonly label?: string;
    readonly payload: Readonly<Record<string, unknown>>;
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isReceivedEvent(event: unknown): event is ReceivedEvent {
    return isRecord(event) && event.kind === "received" && isRecord(event.payload);
}

/**
 * For each live checkpoint, the frames the server sent the transcript's seat up to the message it labels,
 * MessagePack-encoded.
 */
export async function transcriptFrames(): Promise<ReadonlyMap<string, readonly Uint8Array[]>> {
    const transcript: unknown = JSON.parse(await readFile(TRANSCRIPT_FIXTURE, "utf8"));
    if (!isRecord(transcript) || !Array.isArray(transcript.events)) {
        throw new Error(`${TRANSCRIPT_FIXTURE} has no event list`);
    }
    const received = transcript.events.filter(isReceivedEvent);
    return new Map(
        LIVE_CHECKPOINTS.map((label) => {
            const last = received.findIndex((event) => event.label === label);
            if (last === -1) {
                throw new Error(`${TRANSCRIPT_FIXTURE} has no message labelled ${label}`);
            }
            return [
                label,
                received.slice(0, last + 1).map((event) => encodeWireMessage(event.payload)),
            ];
        }),
    );
}

function assetPath(pathname: string): string | null {
    const file = resolve(DIST, `.${pathname.slice(ASSET_PREFIX.length - 1)}`);
    return file.startsWith(DIST + sep) ? file : null;
}

async function respond(request: IncomingMessage, response: ServerResponse): Promise<void> {
    const { pathname } = new URL(request.url ?? "/", "http://visual-check");
    let file: string | null = null;
    if (pathname.startsWith(ASSET_PREFIX)) {
        file = assetPath(pathname);
    } else if (pathname.startsWith("/api/replays/")) {
        file = REPLAY_FIXTURE;
    } else if (pathname.startsWith("/play/")) {
        file = join(DIST, "index.html");
    }
    if (file === null) {
        response.writeHead(404).end();
        return;
    }
    try {
        const body = await readFile(file);
        const type = CONTENT_TYPES[extname(file)] ?? "text/plain";
        response.writeHead(200, { "Content-Type": type }).end(body);
    } catch {
        response.writeHead(404).end();
    }
}

export async function startServer(): Promise<{ server: Server; origin: string }> {
    const server = createServer((request, response) => {
        void respond(request, response);
    });
    await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
    const address = server.address();
    if (address === null || typeof address === "string") {
        throw new Error("the fixture server has no TCP port");
    }
    return { origin: `http://127.0.0.1:${address.port}`, server };
}

/**
 * A context that keeps the run offline and deterministic: reduced motion, so a shot shows each animation's resting
 * state, nothing off the origin, the handoff set, the socket mocked.
 */
export async function openContext(
    browser: Browser,
    viewport: Viewport,
    {
        frames,
        origin,
    }: {
        readonly frames: readonly Uint8Array[];
        readonly origin: string;
    },
): Promise<BrowserContext> {
    const context = await browser.newContext({
        ...viewport.context,
        locale: "en-US",
        reducedMotion: "reduce",
    });
    await context.route(
        (url) => url.origin !== origin,
        (route) => route.fulfill({ body: "", contentType: "text/css", status: 200 }),
    );
    const wsUrl = `${origin.replace("http", "ws")}/ws/${GAME_ID}`;
    const handoff = JSON.stringify({ gameTicket: "visual-check", wsUrl });
    await context.addInitScript(([key, value]) => sessionStorage.setItem(key, value), [
        `game_session:${GAME_ID}`,
        handoff,
    ] as const);
    await context.routeWebSocket(wsUrl, (socket) => {
        let joined = false;
        socket.onMessage(() => {
            if (joined) {
                return;
            }
            joined = true;
            for (const frame of frames) {
                socket.send(Buffer.from(frame));
            }
        });
    });
    return context;
}
