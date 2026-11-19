import { errors } from "playwright";

import { GAME_ID, type PageCase, type PageRun, type Surface } from "../model.ts";
import { BROWSER_PHONES } from "../viewports.ts";

/** Where a touch browser's tab rests, and the scroll room it keeps below that: `_pages.scss`'s `$bars-*-room`. */
const REST = 100;
const SWIPE_ROOM = 300;
/**
 * How long a scroll's return to the rest may take: the page waits 150ms after a scroll settles, but a loaded run
 * delivers the scroll and fires that timer late, so the check waits for the rest instead of a fixed time.
 */
const REST_TIMEOUT_MS = 3000;

interface PageRest {
    /** How far the document stands past the large viewport, which is what a swipe scrolls to collapse the bars. */
    readonly room: number;
    readonly scrollY: number;
    /** The board page's top in the viewport and its positioning, or null where the page draws none. */
    readonly boardPage: {
        readonly top: number;
        readonly position: string;
    } | null;
}

function measureRest({ page }: PageRun): Promise<PageRest> {
    return page.evaluate(() => {
        const probe = document.createElement("div");
        probe.style.cssText = "position: fixed; top: 0; height: 100lvh; visibility: hidden;";
        document.body.append(probe);
        const large = probe.offsetHeight;
        probe.remove();
        const boardPage = document.querySelector(".board-page");
        return {
            boardPage:
                boardPage === null
                    ? null
                    : {
                          position: getComputedStyle(boardPage).position,
                          top: boardPage.getBoundingClientRect().top,
                      },
            room: document.documentElement.scrollHeight - large,
            scrollY: window.scrollY,
        };
    });
}

async function scrollAndWait(run: PageRun, top: number): Promise<number> {
    await run.page.evaluate((scrollTop) => window.scrollTo(0, scrollTop), top);
    await run.page
        .waitForFunction((rest) => window.scrollY === rest, REST, {
            timeout: REST_TIMEOUT_MS,
        })
        .catch((error: unknown) => {
            if (!(error instanceof errors.TimeoutError)) {
                throw error;
            }
        });
    const { scrollY } = await measureRest(run);
    return scrollY;
}

/**
 * A phone browser's bars collapse only as the document scrolls, and only where a drag can scroll further than the
 * bars are tall: the page must stand taller than the large viewport, rest off its top with that room left below, come
 * back to its rest from either end, and keep its board stuck to the viewport's top throughout.
 */
async function checkBarsCollapse(run: PageRun): Promise<string> {
    const { report } = run;
    const rest = await measureRest(run);
    report.expect(
        rest.room === REST + SWIPE_ROOM,
        `the page stands ${rest.room}px past the large viewport, not ${REST + SWIPE_ROOM}: a swipe cannot collapse the browser's bars`,
    );
    report.expect(rest.scrollY === REST, `the page rests at ${rest.scrollY}px, not ${REST}px`);
    report.expect(
        rest.boardPage?.position === "sticky" && Math.abs(rest.boardPage.top) <= 1,
        `the board page is ${rest.boardPage?.position ?? "missing"} at ${rest.boardPage?.top ?? "no"}px, not stuck to the viewport's top`,
    );
    const fromTop = await scrollAndWait(run, 0);
    report.expect(fromTop === REST, `after a scroll to its top the page stays at ${fromTop}px`);
    const fromEnd = await scrollAndWait(run, rest.room);
    report.expect(fromEnd === REST, `after a scroll to its end the page stays at ${fromEnd}px`);
    return `scroll room ${rest.room}px, rests at ${rest.scrollY}px`;
}

/** The live game and the replay on their own routes, in the phone browsers' boxes with their bars shown. */
const PAGES: readonly PageCase[] = [
    {
        at: BROWSER_PHONES,
        check: checkBarsCollapse,
        checkpoint: "turn",
        kind: "own",
        name: "game-browser-bars",
        path: `/play/${GAME_ID}`,
        required: { visible: [".game__play .hand-tile"] },
    },
    {
        at: BROWSER_PHONES,
        check: checkBarsCollapse,
        kind: "own",
        name: "replay-browser-bars",
        path: `/play/history/${GAME_ID}`,
        required: { visible: [".replay-board-mode .replay-controls"] },
    },
];

export const browserBarsSurface: Surface = { pages: PAGES };
