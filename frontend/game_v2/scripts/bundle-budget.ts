import { readFile, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { gzipSync } from "node:zlib";

/**
 * The v2 client's bundle budget: it reads the built `dist/` through the manifest the gate's build writes
 * (`vite build --manifest`), then deletes it so it is never served, and fails when a route loads more JavaScript or
 * CSS than its budget, raw or gzipped. The game route is the entry and everything it imports statically; a lazy
 * route is what its chunk adds on top of the entry; the tile sprite, an asset every page fetches, has its own. The budgets sit modestly above the measured sizes, so growth
 * is a decision made here, not a drift.
 */

const DIST = resolve(import.meta.dirname, "../dist");
const MANIFEST = join(DIST, ".vite/manifest.json");
const KIB = 1024;

interface Size {
    readonly raw: number;
    readonly gzip: number;
}

interface RouteBudget {
    /** The manifest key of the route's chunk. */
    readonly chunk: string;
    readonly js: Size;
    readonly css: Size;
}

/**
 * Budgets in KiB (raw / gzip), each set about a tenth over what its route measured when it was set, and a lazy
 * route's CSS at least 1 KiB over, so a small style edit is not a budget decision. The game and the replay were set
 * on 2026-10-29 at 417.6 / 83.2 JS and 80.4 / 12.5 CSS, and 7.4 / 2.8 JS and 2.3 / 0.8 CSS; the storybook on
 * 2026-10-30 at 34.4 / 8.0 JS (the four seat transcripts its decisions stories run and the sixteen round ends its
 * result stories show among them) and 1.1 / 0.4 CSS, and its JS raised on 2026-10-30 at 39.0 / 8.7, once the
 * decisions stories ran six transcripts (a double ron's and the game's last round's results to confirm). Every JS
 * budget re-set on 2026-10-30 from 444.0 / 91.0 game, 5.9 / 2.3 replay and 40.0 / 9.1 storybook to 161.3 / 48.8,
 * 10.0 / 3.7 and 45.4 / 11.3: the tile sprite left the entry for an asset of its own (`SPRITE`), Zod is `zod/mini`,
 * and `sideEffects` lets the replay's and the scenarios' modules leave the entry for their own routes. Every page
 * still fetches the sprite, so like for like a replay page's JS and sprite came to 386 / 74 where its JS, the sprite
 * inside, was 450 / 93. The game's CSS then measured 86.4 / 13.3, and the entry's JS 163.5 / 49.7 once it loaded the
 * sprite with retries and tiles named their faces until it lands: a cold start of 463.3 / 83.6 with the sprite.
 * The game's CSS budget re-set on 2026-10-30 from 88 / 14 to 81 / 13.5 at 73.0 / 12.3, the nameplates in it: Pico
 * now emits only the dark scheme and the modules the pages use (`styles/_pico.scss`), 18 KiB less.
 * The replay's budgets re-set on 2026-10-30 from 11 / 4.1 JS and 3.3 / 1.8 CSS to 22 / 7.9 and 7 / 2.5, at
 * 20.5 / 7.3 and 5.9 / 1.5: its cursor, address, narration, round list, load retries, failure screens and its
 * desktop bar. The storybook's JS from 50 / 12.4 to 56 / 14.2 at 50.8 / 12.9: the replay stories load the replay
 * view from its own route's chunk and each generated replay they open in a chunk of its own.
 * The final standings, a lazy chunk of their own (`startStandingsLoad`: their panel, mapper and stylesheet), which
 * each view that may show them loads as it mounts, set on 2026-10-30 at 6.3 / 2.2 JS and 4.5 / 1.3 CSS. The game's
 * budgets re-set the same day from 178 / 54 JS and 81 / 13.5 CSS to 188 / 57.7 and 88 / 14.8, at 170.6 / 52.4 and
 * 79.7 / 13.4: the standings left the entry, and the board keeps its corner clear of a panel over it.
 * The replay's budgets re-set on 2026-10-30 from 22 / 7.9 JS and 7 / 2.5 CSS to 32.5 / 11.1 and 8.9 / 2.8, at
 * 29.4 / 10.1 and 7.9 / 1.8: autoplay and its speeds, the round, Home/End and autoplay keys, the wheel's gesture
 * thresholds, hold-to-repeat, the viewpoint switch, hiding the other hands, the reader's settings and the phone
 * column's narration room.
 */
const BUDGETS: Readonly<Record<string, RouteBudget>> = {
    game: { chunk: "index.html", css: { gzip: 14.8, raw: 88 }, js: { gzip: 57.7, raw: 188 } },
    replay: {
        chunk: "src/views/replay.ts",
        css: { gzip: 2.8, raw: 8.9 },
        js: { gzip: 11.1, raw: 32.5 },
    },
    standings: {
        chunk: "src/entities/table/ui/standings.ts",
        css: { gzip: 2.3, raw: 5.5 },
        js: { gzip: 2.4, raw: 7 },
    },
    storybook: {
        chunk: "src/views/storybook-routes.ts",
        css: { gzip: 1.4, raw: 2.1 },
        js: { gzip: 14.2, raw: 56 },
    },
};

/**
 * The tile sprite, an asset rather than a chunk: every page fetches it beside the entry (the page preloads it), so it
 * has a budget of its own and joins the entry in the cold start the script reports. Set on 2026-10-30, about a tenth
 * over its 213.0 / 20.5.
 */
const SPRITE = { budget: { gzip: 23, raw: 235 }, key: "src/assets/tiles/sprites/fluffy-stuff.svg" };

interface ManifestChunk {
    readonly file: string;
    readonly imports?: readonly string[];
    readonly css?: readonly string[];
}

function isManifest(value: unknown): value is Readonly<Record<string, ManifestChunk>> {
    if (typeof value !== "object" || value === null) {
        return false;
    }
    return Object.values(value).every(
        (chunk: unknown) =>
            typeof chunk === "object" &&
            chunk !== null &&
            "file" in chunk &&
            typeof chunk.file === "string",
    );
}

/** The files a chunk loads: its own, its CSS, and those of every chunk it imports statically, transitively. */
function closure(
    manifest: Readonly<Record<string, ManifestChunk>>,
    key: string,
    seen = new Set<string>(),
): string[] {
    const chunk = manifest[key];
    if (chunk === undefined) {
        throw new Error(`the manifest has no chunk ${key}`);
    }
    seen.add(key);
    const imported = (chunk.imports ?? [])
        .filter((next) => !seen.has(next))
        .flatMap((next) => closure(manifest, next, seen));
    return [chunk.file, ...(chunk.css ?? []), ...imported];
}

async function measure(files: Iterable<string>, extension: string): Promise<Size> {
    const bodies = await Promise.all(
        [...files]
            .filter((file) => file.endsWith(extension))
            .map((file) => readFile(join(DIST, file))),
    );
    const raw = bodies.reduce((sum, body) => sum + body.length, 0);
    const gzip = bodies.reduce((sum, body) => sum + gzipSync(body, { level: 9 }).length, 0);
    return { gzip: gzip / KIB, raw: raw / KIB };
}

function describe(size: Size, budget: Size): string {
    return `${size.raw.toFixed(1)}/${budget.raw} KiB raw, ${size.gzip.toFixed(1)}/${budget.gzip} KiB gzip`;
}

function overBudget(kind: string, size: Size, budget: Size): string[] {
    const over = size.raw > budget.raw || size.gzip > budget.gzip;
    return over ? [`${kind} ${describe(size, budget)}`] : [];
}

async function main(): Promise<number> {
    const manifest: unknown = JSON.parse(await readFile(MANIFEST, "utf8"));
    await rm(dirname(MANIFEST), { recursive: true });
    if (!isManifest(manifest)) {
        throw new Error(`${MANIFEST} is not a Vite manifest`);
    }
    const entry = new Set(closure(manifest, BUDGETS.game.chunk));
    const failures: string[] = [];
    for (const [route, budget] of Object.entries(BUDGETS)) {
        const all = closure(manifest, budget.chunk);
        const own = route === "game" ? all : all.filter((file) => !entry.has(file));
        const js = await measure(own, ".js");
        const css = await measure(own, ".css");
        console.info(`${route}: JS ${describe(js, budget.js)}; CSS ${describe(css, budget.css)}`);
        failures.push(
            ...[...overBudget("JS", js, budget.js), ...overBudget("CSS", css, budget.css)].map(
                (failure) => `${route} ${failure}`,
            ),
        );
    }
    const sprite = manifest[SPRITE.key];
    if (sprite === undefined) {
        throw new Error(`the manifest has no asset ${SPRITE.key}`);
    }
    const spriteSize = await measure([sprite.file], ".svg");
    console.info(`sprite: ${describe(spriteSize, SPRITE.budget)}`);
    failures.push(...overBudget("sprite", spriteSize, SPRITE.budget));
    const coldStart = await measure([...entry, sprite.file], "");
    console.info(
        `cold start (entry JS and CSS, and the sprite): ${coldStart.raw.toFixed(1)} KiB raw, ${coldStart.gzip.toFixed(1)} KiB gzip`,
    );
    if (failures.length > 0) {
        console.error(`Bundle budget exceeded:\n${failures.map((line) => `  ${line}`).join("\n")}`);
        return 1;
    }
    console.info("Bundle budget met");
    return 0;
}

process.exitCode = await main();
