import { type Page } from "playwright";

import { type BoardMeasure } from "../board-measure.ts";
import { type Box, EPSILON, MIN_ACTION_SIZE, contains, describeBox } from "../boxes.ts";
import { BOARD_VISIBLE, documentCase } from "../cases.ts";
import {
    type BoardCase,
    type BoardRun,
    GAME_ID,
    type PageCase,
    type PageReport,
    SELECTOR_TIMEOUT_MS,
    type Surface,
} from "../model.ts";
import { SHORT_DESKTOP, WIDER_PHONES } from "../viewports.ts";

/** The replay aside's text on a desktop: the least font size in px and the most lines each part may wrap to. */
const REPLAY_TEXT_LIMITS: Readonly<
    Record<string, { readonly px: number; readonly lines: number }>
> = {
    incomplete: { lines: 4, px: 12 },
    narration: { lines: 3, px: 13 },
    round: { lines: 2, px: 13 },
};

/** The fewest lines of the replay's narration a landscape phone's column shows without scrolling it. */
const MIN_PHONE_NARRATION_LINES = 3;

const REPLAY_MAX_STEPS = 300;
const REPLAY_LOCAL_MELDS = 2;

interface ReplayText {
    readonly part: string;
    readonly px: number;
    readonly lines: number;
}

interface NarrationMeasure {
    readonly box: Box;
    readonly visibleLines: number;
}

/** The replay's controls and text: empty, or null, on a page without them. */
interface ReplayMeasure {
    /** The replay's move and option buttons and round toggle beside the board, and its round list's rows over it. */
    readonly replayControls: readonly Box[];
    readonly roundList: Box | null;
    /** The replay aside's text: each part's font size and the lines it wraps to. */
    readonly replayText: readonly ReplayText[];
    /** The replay's narration: its box and how many of its lines its box shows at once. */
    readonly narration: NarrationMeasure | null;
}

/** A replay page story: the replay view as on its route, its replay answered from a generated fixture. */
function replayCase(story: string, extra: readonly string[]): BoardCase {
    return {
        kind: "board",
        name: `replay-${story.replaceAll("_", "-")}`,
        path: `/play/storybook/replay?state=${story}`,
        required: { visible: [...BOARD_VISIBLE, ".replay-controls__moves", ...extra] },
    };
}

/** A replay page story that shows no board: loading, or why the replay cannot be shown. */
function replayStateCase(story: string, content: string): PageCase {
    return documentCase(
        `replay-${story.replaceAll("_", "-")}`,
        `/play/storybook/replay?state=${story}`,
        content,
    );
}

/** The step the replay's controls show within its round, as a number. */
async function replayStep(page: Page): Promise<number> {
    const text = await page.locator(".replay-controls__step").textContent();
    const step = /(?<index>\d+)[/]/u.exec(text ?? "")?.groups?.index;
    if (step === undefined) {
        throw new Error(`the replay shows no step: ${text}`);
    }
    return Number(step);
}

/**
 * Next steps exactly once for each native activation, in the browser's own event order: a click (a press that steps
 * and the click it ends in), and Enter and Space on the focused button, which the page takes as the step.
 */
async function checkStepButton(page: Page): Promise<void> {
    const next = page.locator("[data-step='next']");
    const activations: readonly [string, () => Promise<void>][] = [
        ["a click", () => next.click()],
        ["Enter", () => next.press("Enter")],
        ["Space", () => next.press(" ")],
    ];
    for (const [name, activate] of activations) {
        const before = await replayStep(page);
        await activate();
        const after = await replayStep(page);
        if (after !== before + 1) {
            throw new Error(`${name} on Next stepped from ${before} to ${after}, not once`);
        }
    }
}

async function stepReplayToLocalMelds(page: Page): Promise<void> {
    await page.waitForSelector(".replay-controls", { timeout: SELECTOR_TIMEOUT_MS });
    await checkStepButton(page);
    for (let step = 0; step < REPLAY_MAX_STEPS; step += 1) {
        if ((await page.locator(".board-local .meld").count()) >= REPLAY_LOCAL_MELDS) {
            return;
        }
        await page.keyboard.press("ArrowRight");
    }
    throw new Error(`the replay never showed ${REPLAY_LOCAL_MELDS} local melds`);
}

const PAGES: readonly PageCase[] = [
    { ...replayCase("start", [".replay-controls__narration"]), alsoAt: WIDER_PHONES },
    replayCase("autoplay", [".replay-controls__option--play[aria-pressed='true']"]),
    replayCase("viewpoint_hidden", [".replay-controls__option--hands[aria-pressed='true']"]),
    {
        ...replayCase("round_list", [".round-list__row[aria-current]"]),
        longNames: true,
    },
    replayCase("incomplete", [".replay-controls__incomplete--end"]),
    replayCase("ends_on_result", [".round-end-result__title", ".replay-controls__incomplete--end"]),
    replayCase("damaged", [".replay-controls__incomplete--end"]),
    replayCase("double_ron", [".round-end-result__pager"]),
    replayCase("result_hidden", [
        ".round-end-result__title",
        ".replay-controls__option--hands[aria-pressed='true']",
    ]),
    replayCase("standings", [".standings__round--jump", ".standings__cell--win"]),
    replayCase("standings_long", [".standings__round--jump", ".standings__foot-row--result"]),
    replayStateCase("loading", ".replay-state"),
    replayStateCase("not_found", ".replay-state__links a"),
    {
        alsoAt: [SHORT_DESKTOP],
        kind: "board",
        name: "replay",
        path: `/play/history/${GAME_ID}`,
        prepare: stepReplayToLocalMelds,
        required: { visible: [...BOARD_VISIBLE, ".board-local .meld", ".replay-controls"] },
    },
];

function measureReplay(page: Page): Promise<ReplayMeasure> {
    return page.evaluate(() => {
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function box(element: Element): Box {
            const rect = element.getBoundingClientRect();
            return {
                height: rect.height,
                left: rect.left + window.scrollX,
                top: rect.top + window.scrollY,
                width: rect.width,
            };
        }
        const roundList = document.querySelector(".round-list");
        const roundRows = document.querySelector(".round-list__rows");
        const shownRows =
            roundRows === null
                ? []
                : [...roundRows.querySelectorAll(".round-list__row")].filter((row) => {
                      const shown = roundRows.getBoundingClientRect();
                      const { bottom, top } = row.getBoundingClientRect();
                      return top >= shown.top && bottom <= shown.bottom;
                  });
        const replayTextParts: Readonly<Record<string, string>> = {
            incomplete: ".replay-controls__incomplete",
            narration: ".replay-controls__narration",
            round: ".replay-controls__round",
        };
        const replayText = Object.entries(replayTextParts).flatMap(([part, selector]) => {
            const element = document.querySelector(selector);
            if (element === null || element.textContent.trim() === "") {
                return [];
            }
            const px = Number.parseFloat(getComputedStyle(element).fontSize);
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            const rects: DOMRect[] = [];
            for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
                const range = document.createRange();
                range.selectNodeContents(node);
                rects.push(...[...range.getClientRects()].filter((rect) => rect.height > 0));
            }
            const tops = rects.map((rect) => rect.top).toSorted((first, second) => first - second);
            const lineGap = Math.min(...rects.map((rect) => rect.height)) / 2;
            const lines = tops.filter(
                (top, index) => index === 0 || top - tops[index - 1] > lineGap,
            );
            return [{ lines: lines.length, part, px }];
        });
        const narrationElement = document.querySelector(".replay-controls__narration");
        const narration =
            narrationElement === null
                ? null
                : {
                      box: box(narrationElement),
                      visibleLines: Math.floor(
                          (narrationElement.clientHeight + 1) /
                              Number.parseFloat(getComputedStyle(narrationElement).lineHeight),
                      ),
                  };
        const replayControls = [
            ...document.querySelectorAll(
                ".replay-controls__move, .replay-controls__option, .replay-controls__round, .round-list__close",
            ),
            ...shownRows,
        ].map(box);
        return {
            narration,
            replayControls,
            replayText,
            roundList: roundList === null ? null : box(roundList),
        };
    });
}

/** The replay's controls sit on the screen, large enough to tap, and its round list on the board. */
function checkReplayControls(
    replay: ReplayMeasure,
    { board, screen }: { readonly board: Box; readonly screen: Box },
    report: PageReport,
): void {
    const outside = replay.replayControls.filter((control) => !contains(screen, control));
    report.expect(outside.length === 0, `${outside.length} replay control(s) off the screen`);
    const small = replay.replayControls.filter(
        (control) =>
            control.width < MIN_ACTION_SIZE - EPSILON || control.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `replay controls under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
    if (replay.roundList !== null) {
        report.expect(
            contains(board, replay.roundList),
            `the round list ${describeBox(replay.roundList)} leaves the board`,
        );
    }
}

/** On a desktop the replay's aside reads at a glance: its narration and round, and its incompleteness label. */
function checkReplayText(replay: ReplayMeasure, report: PageReport): void {
    for (const { lines, part, px } of replay.replayText) {
        const limit = REPLAY_TEXT_LIMITS[part];
        report.expect(
            px >= limit.px && lines <= limit.lines,
            `the replay's ${part} at ${px}px on ${lines} line(s), past ${limit.px}px on ${limit.lines}`,
        );
    }
}

/**
 * On a landscape phone the replay's column keeps room for its narration, at least three lines in view at once
 * whatever else the column holds, and the narration wholly on the screen and inside the column.
 */
function checkPhoneNarration(
    replay: ReplayMeasure,
    { board, screen }: { readonly board: BoardMeasure; readonly screen: Box },
    report: PageReport,
): void {
    const { narration } = replay;
    const { aside } = board;
    if (narration === null || aside === null) {
        return;
    }
    report.expect(
        narration.visibleLines >= MIN_PHONE_NARRATION_LINES,
        `the replay's narration shows ${narration.visibleLines} line(s) at once, under ${MIN_PHONE_NARRATION_LINES}`,
    );
    report.expect(
        contains(screen, narration.box) && contains(aside.box, narration.box),
        `the replay's narration ${describeBox(narration.box)} leaves the screen or its column`,
    );
}

/**
 * The replay's controls on a supported landscape screen, on the screen and large enough to tap and its round list on
 * the board; its aside's text on a desktop, and its narration's room in a landscape phone's column.
 */
async function checkBoard({ board, page, report, screen, viewport }: BoardRun): Promise<void> {
    const landscape = viewport.supported && !viewport.portrait;
    if (!landscape && !viewport.desktop) {
        return;
    }
    const replay = await measureReplay(page);
    if (landscape) {
        checkReplayControls(replay, { board: board.board, screen }, report);
    }
    if (viewport.desktop) {
        checkReplayText(replay, report);
    } else {
        checkPhoneNarration(replay, { board, screen }, report);
    }
}

/** The replay page: its stories, its states without a board, and the route stepped to the local melds. */
export const replaySurface: Surface = {
    checkBoard,
    pages: PAGES,
};
