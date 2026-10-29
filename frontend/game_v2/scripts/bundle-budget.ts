import { readFile, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { gzipSync } from "node:zlib";

/**
 * The v2 client's bundle budget: it reads the built `dist/` through the manifest the gate's build writes
 * (`vite build --manifest`), then deletes it so it is never served, and fails when a route loads more JavaScript or
 * CSS than its budget, raw or gzipped. The game route is the entry and everything it imports; a lazy
 * route is what its chunk adds on top of the entry. The budgets sit modestly above the measured sizes, so growth
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
 * Budgets in KiB, about a tenth over what each route measured on 2026-10-29 (raw / gzip), and a lazy route's CSS at
 * least 1 KiB over, so a small style edit is not a budget decision: the game 417.6 / 83.2 JS and 80.4 / 12.5 CSS,
 * the replay 7.4 / 2.8 JS and 2.3 / 0.8 CSS, the storybook 26.3 / 6.2 JS (the four seat transcripts its decisions
 * stories run among them) and 1.1 / 0.4 CSS.
 */
const BUDGETS: Readonly<Record<string, RouteBudget>> = {
    game: { chunk: "index.html", css: { gzip: 14, raw: 88 }, js: { gzip: 92, raw: 460 } },
    replay: {
        chunk: "src/views/replay.ts",
        css: { gzip: 1.8, raw: 3.3 },
        js: { gzip: 3.1, raw: 8.2 },
    },
    storybook: {
        chunk: "src/views/storybook-routes.ts",
        css: { gzip: 1.4, raw: 2.1 },
        js: { gzip: 7, raw: 29 },
    },
};

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
    if (failures.length > 0) {
        console.error(`Bundle budget exceeded:\n${failures.map((line) => `  ${line}`).join("\n")}`);
        return 1;
    }
    console.info("Bundle budget met");
    return 0;
}

process.exitCode = await main();
