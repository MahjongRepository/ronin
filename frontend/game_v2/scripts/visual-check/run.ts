import { readdir, rm } from "node:fs/promises";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";

import {
    type Browser,
    type BrowserContext,
    type BrowserType,
    type Page,
    chromium,
    webkit,
} from "playwright";

import { describeBoard, measureBoard } from "./board-measure.ts";
import { CONTRAST_VIEWPORTS, checkContrast } from "./contrast.ts";
import { APP_ROOT, type Fixtures, openContext, startServer, transcriptFrames } from "./fixtures.ts";
import {
    type BoardOptions,
    type PageCase,
    PageReport,
    type PageRun,
    SELECTOR_TIMEOUT_MS,
    type Surface,
    type TaskResult,
    type Viewport,
} from "./model.ts";
import { checkTileFaces, checkVisible, measurePage, viewportBox } from "./page-checks.ts";
import { boardSurface } from "./surfaces/board.ts";
import { decisionsSurface } from "./surfaces/decisions.ts";
import { noticesSurface } from "./surfaces/notices.ts";
import { panelsSurface } from "./surfaces/panels.ts";
import { replaySurface } from "./surfaces/replay.ts";
import { FLOOR, VIEWPORTS, checkCaptureModel, emulateInsets } from "./viewports.ts";

/**
 * The v2 client's targeted layout check: the pages and viewports a run names, never a sweep of all of them. It builds
 * nothing itself: it serves the development build in `dist-dev/` (the app page for every `/play/` path), a replay
 * fixture under the replay API and a seat transcript over a mocked game socket, then loads the selected pages and
 * asserts what a player would see: content visible, nothing overlapping, everything inside the board and the screen,
 * readable text and tappable tiles. Any console error, failed request or missing element fails it. It writes a
 * screenshot of each page for review. Each surface (`Surface`) declares its pages and its checks; the runner loads
 * the pages and runs every surface's checks on each.
 */

const DEFAULT_SHOTS = resolve(APP_ROOT, "../../thoughts/screenshots/visual-check");
const SETTLE_MS = 150;
/** Pages a browser checks at once, each in its own context; the engines run one after the other. */
const PAGES_AT_ONCE = 3;
/** The most pages a run checks without `--many`: a targeted run names a few pages at two or three viewports. */
const MAX_PAGES = 60;

const SURFACES: readonly Surface[] = [
    boardSurface,
    decisionsSurface,
    panelsSurface,
    replaySurface,
    noticesSurface,
];
const PAGES: readonly PageCase[] = SURFACES.flatMap((surface) => surface.pages);

/** Measure the board once and hold it to every surface's checks, in turn; the board's summary line. */
async function checkBoard(run: PageRun, options: BoardOptions): Promise<string> {
    const board = await measureBoard(run.page);
    const screen = await viewportBox(run.page);
    const boardRun = { ...run, board, options, screen };
    for (const surface of SURFACES) {
        await surface.checkBoard?.(boardRun);
    }
    return describeBoard(board);
}

async function checkPage(
    { page, report, viewport }: Omit<PageRun, "measure">,
    pageCase: PageCase,
): Promise<string> {
    const measure = await measurePage(page);
    const run = { measure, page, report, viewport };
    report.expect(
        measure.scrollWidth <= measure.innerWidth,
        `horizontal page overflow: ${measure.scrollWidth} > ${measure.innerWidth}`,
    );
    await checkVisible(page, pageCase.required.visible, report);
    switch (pageCase.kind) {
        case "document": {
            return `page ${measure.scrollWidth}x${measure.scrollHeight}`;
        }
        case "board": {
            return checkBoard(run, pageCase);
        }
        case "own": {
            return pageCase.check(run, () => checkBoard(run, {}));
        }
    }
}

interface PageLoad {
    readonly context: BrowserContext;
    readonly viewport: Viewport;
    readonly origin: string;
    readonly shots: string;
}

async function loadPage(page: Page, pageCase: PageCase, origin: string): Promise<void> {
    await page.goto(origin + pageCase.path);
    if (pageCase.kind === "board" && pageCase.prepare) {
        await pageCase.prepare(page);
    }
    const { attached = [], visible } = pageCase.required;
    for (const selector of visible) {
        await page.waitForSelector(selector, { state: "visible", timeout: SELECTOR_TIMEOUT_MS });
    }
    for (const selector of attached) {
        await page.waitForSelector(selector, { state: "attached", timeout: SELECTOR_TIMEOUT_MS });
    }
}

async function runPage(
    { context, origin, shots, viewport }: PageLoad,
    pageCase: PageCase,
): Promise<PageReport> {
    const report = new PageReport();
    const page = await context.newPage();
    page.on("console", (message) => {
        if (message.type() === "error") {
            report.failures.push(`console error: ${message.text()}`);
        }
    });
    page.on("pageerror", (error) => report.failures.push(`page error: ${error.message}`));
    page.on("requestfailed", (request) => {
        report.failures.push(`request failed: ${request.url()}`);
    });
    try {
        await loadPage(page, pageCase, origin);
        await emulateInsets(page, viewport.insets);
        await checkCaptureModel(page, viewport, report);
        await page.evaluate(() => document.fonts.ready.then(() => undefined));
        await page.waitForTimeout(SETTLE_MS);
        await checkTileFaces(page, report);
        report.summary = await checkPage({ page, report, viewport }, pageCase);
        await page.screenshot({ path: join(shots, `${viewport.name}-${pageCase.name}.png`) });
        if (pageCase.contrast === true && CONTRAST_VIEWPORTS.has(viewport.name)) {
            report.summary += `, ${await checkContrast(page, report)}`;
        }
        if (pageCase.kind === "board") {
            for (const surface of SURFACES) {
                await surface.checkAfterShot?.(page, report);
            }
        }
    } catch (error: unknown) {
        report.failures.push(error instanceof Error ? error.message : String(error));
    } finally {
        await page.close();
    }
    if (report.checks === 0 && report.failures.length === 0) {
        report.failures.push("no check ran");
    }
    return report;
}

/** One page at one viewport, checked in a context of its own, its findings named by both. */
interface PageTask {
    readonly viewport: Viewport;
    readonly pageCase: PageCase;
}

async function runTask(
    browser: Browser,
    { pageCase, viewport }: PageTask,
    { fixtures, shots }: { readonly fixtures: Fixtures; readonly shots: string },
): Promise<TaskResult> {
    const frames =
        pageCase.kind === "own" && pageCase.checkpoint !== undefined
            ? fixtures.frames.get(pageCase.checkpoint)
            : [];
    const context = await openContext(browser, viewport, {
        frames: frames ?? [],
        origin: fixtures.origin,
    });
    try {
        const report = await runPage(
            { context, origin: fixtures.origin, shots, viewport },
            pageCase,
        );
        return {
            name: `${viewport.name} ${pageCase.name}`,
            page: pageCase.name,
            report,
            viewport: viewport.name,
        };
    } finally {
        await context.close();
    }
}

/** Run `tasks` with at most `limit` at once, keeping their order in the results. */
async function runPooled<Task, Result>(
    tasks: readonly Task[],
    limit: number,
    run: (task: Task) => Promise<Result>,
): Promise<Result[]> {
    const results: Result[] = [];
    let next = 0;
    async function worker(): Promise<void> {
        for (let index = next++; index < tasks.length; index = next++) {
            results[index] = await run(tasks[index]);
        }
    }
    await Promise.all(Array.from({ length: Math.min(limit, tasks.length) }, worker));
    return results;
}

/** The pages and viewports a run checks: the ones `--page` and `--viewport` name. */
interface Selection {
    readonly pages: readonly PageCase[];
    readonly viewports: readonly Viewport[];
    /** Both were named: each page is checked at every viewport named, whether it names it or not (a before and after). */
    readonly anyViewport: boolean;
}

/** The viewports a page is checked at, by name. */
function viewportsOf(pageCase: PageCase): readonly string[] {
    return pageCase.at ?? [FLOOR];
}

/** The selected pages at each of an engine's selected viewports that the page names, or every one (`anyViewport`). */
function tasksOf(engine: BrowserType, selection: Selection): PageTask[] {
    const viewports = selection.viewports.filter((viewport) => viewport.engine === engine);
    return viewports.flatMap((viewport) =>
        selection.pages
            .filter(
                (pageCase) =>
                    selection.anyViewport || viewportsOf(pageCase).includes(viewport.name),
            )
            .map((pageCase) => ({ pageCase, viewport })),
    );
}

/**
 * What would make the gate check less than it says, silently: a page naming no viewport or an unknown one, a viewport
 * no page names, an unknown contrast viewport, and a page measured for contrast at none of the contrast viewports.
 */
function findSelectionErrors(): string[] {
    const names = new Set(VIEWPORTS.map(({ name }) => name));
    const named = new Set(PAGES.flatMap(viewportsOf));
    return [
        ...PAGES.filter((pageCase) => viewportsOf(pageCase).length === 0).map(
            (pageCase) => `${pageCase.name} names no viewport`,
        ),
        ...PAGES.flatMap((pageCase) =>
            viewportsOf(pageCase)
                .filter((name) => !names.has(name))
                .map((name) => `${pageCase.name} names an unknown viewport "${name}"`),
        ),
        ...[...names]
            .filter((name) => !named.has(name))
            .map((name) => `no page is checked at ${name}`),
        ...[...CONTRAST_VIEWPORTS]
            .filter((name) => !names.has(name))
            .map((name) => `the contrast viewport "${name}" is unknown`),
        ...PAGES.filter(
            (pageCase) =>
                pageCase.contrast === true &&
                !viewportsOf(pageCase).some((name) => CONTRAST_VIEWPORTS.has(name)),
        ).map((pageCase) => `${pageCase.name} is measured for contrast at no contrast viewport`),
    ];
}

/** Check an engine's tasks in one browser, several pages at once. */
async function runEngine(
    browser: Browser,
    tasks: readonly PageTask[],
    run: { readonly fixtures: Fixtures; readonly shots: string },
): Promise<TaskResult[]> {
    return runPooled(tasks, PAGES_AT_ONCE, (task) => runTask(browser, task, run));
}

function reportFailures(results: readonly TaskResult[]): string[] {
    return results.flatMap(({ name, report }) => {
        if (report.summary !== "") {
            console.info(`${name}: ${report.summary}`);
        }
        return report.failures.map((failure) => `${name}: ${failure}`);
    });
}

/** An engine's pages in its own browser, launched only when it has any. */
async function checkEngine(
    engine: BrowserType,
    tasks: readonly PageTask[],
    run: { readonly fixtures: Fixtures; readonly shots: string },
): Promise<TaskResult[]> {
    if (tasks.length === 0) {
        return [];
    }
    const browser = await engine.launch();
    try {
        return await runEngine(browser, tasks, run);
    } finally {
        await browser.close();
    }
}

/** Each engine's pages in turn, so only one browser loads pages at a time. */
async function checkAll(
    fixtures: Fixtures,
    shots: string,
    selection: Selection,
): Promise<string[]> {
    const run = { fixtures, shots };
    const results = [
        ...(await checkEngine(chromium, tasksOf(chromium, selection), run)),
        ...(await checkEngine(webkit, tasksOf(webkit, selection), run)),
    ];
    return [
        ...reportFailures(results),
        ...SURFACES.flatMap((surface) => surface.checkResults?.(results) ?? []),
    ];
}

/** Remove the last run's screenshots, so the folder holds only this run's. */
async function clearShots(folder: string): Promise<void> {
    const files = await readdir(folder).catch(() => []);
    await Promise.all(
        files.filter((file) => file.endsWith(".png")).map((file) => rm(join(folder, file))),
    );
}

/** Keep the items whose name contains one of `filters`, or every item when there are none. */
function matching<Item extends { readonly name: string }>(
    items: readonly Item[],
    filters: readonly string[],
): readonly Item[] {
    if (filters.length === 0) {
        return items;
    }
    return items.filter((item) => filters.some((filter) => item.name.includes(filter)));
}

/** The run's selection from `--page` and `--viewport` (each repeatable, matching a name by substring). */
function selectRun(pageFilters: readonly string[], viewportFilters: readonly string[]): Selection {
    return {
        anyViewport: pageFilters.length > 0 && viewportFilters.length > 0,
        pages: matching(PAGES, pageFilters),
        viewports: matching(VIEWPORTS, viewportFilters),
    };
}

async function main(): Promise<number> {
    const { values } = parseArgs({
        options: {
            many: { default: false, type: "boolean" },
            page: { default: [], multiple: true, type: "string" },
            shots: { default: DEFAULT_SHOTS, type: "string" },
            viewport: { default: [], multiple: true, type: "string" },
        },
    });
    const errors = findSelectionErrors();
    if (errors.length > 0) {
        console.error(
            `Visual check misconfigured:\n${errors.map((line) => `  ${line}`).join("\n")}`,
        );
        return 1;
    }
    if (values.page.length === 0 && values.viewport.length === 0) {
        console.error(
            "Visual check needs --page or --viewport: it shoots only what a change touched",
        );
        return 1;
    }
    const selection = selectRun(values.page, values.viewport);
    const pageCount = tasksOf(chromium, selection).length + tasksOf(webkit, selection).length;
    if (pageCount > MAX_PAGES && !values.many) {
        console.error(
            `Visual check selected ${pageCount} pages, over ${MAX_PAGES}: name exact pages at fewer viewports, or pass --many`,
        );
        return 1;
    }
    if (pageCount === 0) {
        console.error(
            `Visual check selected nothing: pages ${PAGES.map(({ name }) => name).join(", ")}; viewports ${VIEWPORTS.map(({ name }) => name).join(", ")}`,
        );
        return 1;
    }
    const shots = resolve(values.shots);
    if (shots === DEFAULT_SHOTS) {
        await clearShots(shots);
    }
    const frames = await transcriptFrames();
    const { origin, server } = await startServer();
    const failures = await checkAll({ frames, origin }, shots, selection).finally(() =>
        server.close(),
    );
    if (failures.length > 0) {
        console.error(
            `Visual check failed:\n${failures.map((failure) => `  ${failure}`).join("\n")}`,
        );
        return 1;
    }
    console.info(`Visual check passed: ${pageCount} pages; screenshots in ${shots}`);
    return 0;
}

process.exitCode = await main();
