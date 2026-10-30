import { type Browser } from "playwright";

import { BUDGET_GAME_ID, openContext } from "./fixtures.ts";
import { SELECTOR_TIMEOUT_MS } from "./model.ts";
import { VIEWPORTS } from "./viewports.ts";

/**
 * The replay load budget: reading the largest replay fixture (parse, reduce into the client timeline, steps and
 * navigation index), measured by the replay view's `replay-load` User Timing on Chromium slowed to a low-end phone's
 * CPU, the median of a few loads. Measured 2026-10-29 on a 12-core dev host: 12 ms unthrottled, 40 ms at 4x, 69 ms
 * at 6x; the budget leaves room for a slower host, not for a slower reader.
 */
const LOAD_CPU_SLOWDOWN = 6;
const LOAD_RUNS = 3;
const LOAD_BUDGET_MS = 120;
const LOAD_MEASURE = "replay-load";
/** What reading the whole fixture yields, which every timed load must report before its time counts. */
const LOAD_EXPECTED = {
    complete: true,
    damagedLine: null,
    rounds: 12,
    standings: [
        [3, 25_000],
        [0, 25_000],
        [1, 25_000],
        [2, 25_000],
    ],
    stops: 1693,
};

function median(values: readonly number[]): number {
    const sorted = values.toSorted((left, right) => left - right);
    return sorted[Math.floor(sorted.length / 2)];
}

/** One load's timing and what the replay view says it read, from its `replay-load` measure. */
interface LoadRun {
    readonly ms: number;
    readonly detail: unknown;
}

/** One load of the largest replay on a slowed CPU: the view's `replay-load` measure. */
async function measureReplayLoad(browser: Browser, origin: string): Promise<LoadRun> {
    const context = await openContext(browser, VIEWPORTS[0], { frames: [], origin });
    try {
        const page = await context.newPage();
        const cdp = await context.newCDPSession(page);
        await cdp.send("Emulation.setCPUThrottlingRate", { rate: LOAD_CPU_SLOWDOWN });
        await page.goto(`${origin}/play/history/${BUDGET_GAME_ID}`);
        await page.waitForSelector(".replay-controls", { timeout: SELECTOR_TIMEOUT_MS * 2 });
        return await page.evaluate((name) => {
            const [entry] = performance.getEntriesByName(name, "measure");
            return entry instanceof PerformanceMeasure
                ? { detail: entry.detail, ms: entry.duration }
                : { detail: null, ms: Number.NaN };
        }, LOAD_MEASURE);
    } finally {
        await context.close();
    }
}

/** Why a load's timing does not count: it read something other than the whole fixture, or recorded no time. */
function invalidLoad({ detail, ms }: LoadRun): string | null {
    if (JSON.stringify(detail) !== JSON.stringify(LOAD_EXPECTED)) {
        return `read ${JSON.stringify(detail)}, not the fixture's ${JSON.stringify(LOAD_EXPECTED)}`;
    }
    return Number.isFinite(ms) && ms > 0 ? null : `recorded no time (${ms})`;
}

export async function checkReplayLoad(browser: Browser, origin: string): Promise<string[]> {
    const runs: LoadRun[] = [];
    for (let run = 0; run < LOAD_RUNS; run += 1) {
        runs.push(await measureReplayLoad(browser, origin));
    }
    const invalid = runs.flatMap((run) => invalidLoad(run) ?? []);
    if (invalid.length > 0) {
        return invalid.map((reason) => `replay load: a run ${reason}`);
    }
    const typical = median(runs.map((run) => run.ms));
    const shown = runs.map((run) => run.ms.toFixed(0)).join(", ");
    console.info(
        `replay load at ${LOAD_CPU_SLOWDOWN}x CPU slowdown: median ${typical.toFixed(0)} ms (${shown}), budget ${LOAD_BUDGET_MS} ms`,
    );
    return typical > LOAD_BUDGET_MS
        ? [`replay load: median ${typical.toFixed(0)} ms over the ${LOAD_BUDGET_MS} ms budget`]
        : [];
}
