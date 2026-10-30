import { type Page } from "playwright";

import { type BoardMeasure } from "../board-measure.ts";
import {
    type Box,
    EPSILON,
    MIN_ACTION_SIZE,
    contains,
    describeBox,
    findOverlaps,
    intersects,
} from "../boxes.ts";
import { BOARD_VISIBLE, documentCase } from "../cases.ts";
import {
    type BoardCase,
    type BoardRun,
    GAME_ID,
    type PageCase,
    type PageReport,
    type PageRun,
    SELECTOR_TIMEOUT_MS,
    type Surface,
} from "../model.ts";
import { NARROW_DESKTOP, SHORT_DESKTOP, SHORT_TABLET, WIDER_PHONES } from "../viewports.ts";

/** The replay's text: the least font size in px each part reads at on a landscape board. */
const REPLAY_TEXT_PX: Readonly<Record<StatusPart, number>> = {
    end: 12,
    incomplete: 12,
    narration: 13,
    position: 13,
};

/** The most lines each part wraps to on a desktop window, the narrow one's narrow left field included. */
const DESKTOP_TEXT_LINES: Readonly<Partial<Record<StatusPart, number>>> = {
    incomplete: 4,
    narration: 3,
    position: 2,
};

/** The fewest of the narration's lines its place shows at once, without scrolling to them. */
const MIN_NARRATION_LINES = 3;

/** A board with the desktop's chrome: at least this wide and high (smaller chrome holds five moves, not seven). */
const DESKTOP_CHROME = { height: 520, width: 1100 };

/** The moves every board shows, either end too where its chrome is the desktop's, and the options. */
const CORE_MOVES = [
    ".replay-controls__move--prevRound",
    ".replay-controls__move--prev",
    ".replay-controls__play",
    ".replay-controls__move--next",
    ".replay-controls__move--nextRound",
];
const END_MOVES = [".replay-controls__move--first", ".replay-controls__move--last"];
const ROUNDS_TOGGLE = ".replay-controls__option--rounds";
const OPTIONS = [
    ".replay-controls__option--speed",
    ".replay-controls__option--view",
    ".replay-controls__option--hands",
    ROUNDS_TOGGLE,
];

const REPLAY_MAX_STEPS = 300;
const REPLAY_LOCAL_MELDS = 2;
/** Autoplay's stops the gate waits through while it checks the narration stays silent. */
const AUTOPLAY_STEPS = 2;
const AUTOPLAY_TIMEOUT_MS = 5000;
/** Autoplay's fastest speed's label, and how many presses of its speed button cycle through every speed. */
const FASTEST_SPEED = "4";
const SPEED_TRIES = 4;

type StatusPart = "end" | "incomplete" | "narration" | "position";

/** Each part of the status by its selector: the position, the incompleteness, its compact end mark, the narration. */
const STATUS_PARTS: Readonly<Record<StatusPart, string>> = {
    end: ".replay-status__incomplete-end",
    incomplete: ".replay-status__incomplete",
    narration: ".replay-status__narration",
    position: ".replay-status__position",
};

/** A part of the status as drawn: shown (drawn at least a line high), its size, lines, box and lines in its place. */
interface StatusText {
    readonly shown: boolean;
    readonly px: number;
    readonly lines: number;
    readonly box: Box;
    readonly linesInPlace: number;
}

/** A control as drawn: its box, and whether it shows (rendered and at least a pixel each way). */
interface ControlMeasure {
    readonly selector: string;
    readonly shown: boolean;
    readonly box: Box;
}

/** The replay's controls and its status in the notices' place: empty, or null, on a page without them. */
interface ReplayMeasure {
    /** Every move and option the band may show, by selector, drawn or not. */
    readonly band: readonly ControlMeasure[];
    /** The round list's close and its rows shown inside its scroll. */
    readonly listControls: readonly Box[];
    readonly roundList: Box | null;
    /** The notices' place, which holds the replay's status, and whether it overflows (with and without a way to scroll). */
    readonly place: {
        readonly box: Box;
        readonly clippedDown: boolean;
        readonly scrolls: boolean;
        readonly clippedAcross: boolean;
    } | null;
    readonly status: Box | null;
    /** The parts present in the page, by name; a part absent from the page (no incompleteness) is missing. */
    readonly parts: Readonly<Partial<Record<StatusPart, StatusText>>>;
    /** The replay stands at its last stop of an incomplete recording. */
    readonly atEnd: boolean;
}

/** A replay page story: the replay view as on its route, its replay answered from a generated fixture. */
function replayCase(story: string, extra: readonly string[]): BoardCase {
    return {
        kind: "board",
        name: `replay-${story.replaceAll("_", "-")}`,
        path: `/play/storybook/replay?state=${story}`,
        required: {
            visible: [...BOARD_VISIBLE, ".replay-controls__moves", ".replay-status", ...extra],
        },
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

/** The step the replay shows within its round, as a number. */
async function replayStep(page: Page): Promise<number> {
    const text = await page.locator(".replay-status__step").textContent();
    const step = /Step (?<index>\d+) of/u.exec(text ?? "")?.groups?.index;
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

/** Press autoplay's speed until its label starts with the one asked for, at most once round every speed. */
async function cycleSpeedTo(page: Page, label: string): Promise<void> {
    const speed = page.locator(".replay-controls__option--speed");
    for (let tries = 0; tries < SPEED_TRIES; tries += 1) {
        const shown = await speed.textContent();
        if (shown?.startsWith(label) === true) {
            return;
        }
        await speed.click();
    }
    throw new Error(`autoplay's speed never showed ${label}`);
}

/** Start recording every text the narration's live region holds, as a screen reader would hear its changes. */
async function recordAnnouncements(page: Page): Promise<void> {
    await page.evaluate(() => {
        const live = document.querySelector(".replay-status [aria-live='polite']");
        if (live === null) {
            throw new Error("the narration has no polite live region");
        }
        const heard: string[] = [];
        Reflect.set(window, "__heard", heard);
        new MutationObserver(() => heard.push(live.textContent.trim())).observe(live, {
            characterData: true,
            childList: true,
            subtree: true,
        });
    });
}

/** The texts recorded since the last take, drained from the one queue the observer keeps writing to. */
async function takeAnnouncements(page: Page): Promise<string[]> {
    return page.evaluate(() => {
        const heard: unknown = Reflect.get(window, "__heard");
        return Array.isArray(heard) ? heard.splice(0).map(String) : [];
    });
}

/** The live regions' texts in the page's accessibility tree that carry the narration shown. */
async function narrationInTree(page: Page): Promise<{ narration: string; count: number }> {
    const shown = await page.locator(".replay-status__narration").textContent();
    const narration = shown?.trim() ?? "";
    const tree = await page.locator(".replay-board-mode").ariaSnapshot();
    return { count: tree.split(narration).length - 1, narration };
}

/**
 * The narration is in the accessibility tree once, a step announces its new narration once, and autoplay is silent:
 * the live region holds nothing while it runs, at its fastest speed.
 */
async function checkNarrationAnnounced(page: Page): Promise<void> {
    const shown = await narrationInTree(page);
    if (shown.narration === "" || shown.count !== 1) {
        throw new Error(
            `the narration "${shown.narration}" is in the accessibility tree ${shown.count} time(s), not once`,
        );
    }
    await recordAnnouncements(page);
    await page.locator("[data-step='next']").click();
    const stepped = await takeAnnouncements(page);
    const nextText = await page.locator(".replay-status__narration").textContent();
    const next = nextText?.trim();
    const heard = stepped.filter((text) => text !== "");
    if (heard.length !== 1 || heard[0] !== next) {
        throw new Error(`a step announced ${JSON.stringify(heard)}, not its narration once`);
    }
    const reader = await page.locator(".replay-controls__option--speed").textContent();
    await cycleSpeedTo(page, FASTEST_SPEED);
    await takeAnnouncements(page);
    const before = await replayStep(page);
    await page.locator(".replay-controls__play").click();
    await page.waitForFunction(
        ([from, steps]) => {
            const text = document.querySelector(".replay-status__step")?.textContent ?? "";
            return Number(/Step (?<index>\d+) of/u.exec(text)?.groups?.index) >= from + steps;
        },
        [before, AUTOPLAY_STEPS] as const,
        { timeout: AUTOPLAY_TIMEOUT_MS },
    );
    const playing = await takeAnnouncements(page);
    await page.locator(".replay-controls__play").click();
    await cycleSpeedTo(page, reader ?? "");
    const spoken = playing.filter((text) => text !== "");
    if (spoken.length > 0) {
        throw new Error(`autoplay announced ${JSON.stringify(spoken)}`);
    }
}

async function stepReplayToLocalMelds(page: Page): Promise<void> {
    await page.waitForSelector(".replay-controls", { timeout: SELECTOR_TIMEOUT_MS });
    await checkStepButton(page);
    await checkNarrationAnnounced(page);
    for (let step = 0; step < REPLAY_MAX_STEPS; step += 1) {
        if ((await page.locator(".board-local .meld").count()) >= REPLAY_LOCAL_MELDS) {
            return;
        }
        await page.keyboard.press("ArrowRight");
    }
    throw new Error(`the replay never showed ${REPLAY_LOCAL_MELDS} local melds`);
}

/**
 * A throw while stepping shows the replay's failure screen, its error on the console: checked on a page of its own in
 * the same context, whose console error is expected, before the board the story opened on is checked.
 */
async function checkThrowOnStep(
    { page, report }: PageRun,
    checkShownBoard: () => Promise<string>,
): Promise<string> {
    const stepping = await page.context().newPage();
    try {
        const errors: string[] = [];
        stepping.on("console", (message) => {
            if (message.type() === "error") {
                errors.push(message.text());
            }
        });
        await stepping.goto(page.url());
        await stepping.waitForSelector("[data-step='next']", { timeout: SELECTOR_TIMEOUT_MS });
        await stepping.locator("[data-step='next']").click();
        const title = await stepping
            .locator(".replay-state--failed .replay-state__title")
            .textContent({ timeout: SELECTOR_TIMEOUT_MS });
        report.expect(
            title === "This replay cannot be shown",
            `a throw while stepping showed "${title}", not the failure screen`,
        );
        report.expect(
            errors.some((error) => error.startsWith("The replay could not be shown:")),
            `a throw while stepping left no error on the console: ${errors.join("; ")}`,
        );
        report.expect(
            (await stepping.locator(".replay-state__links a").count()) === 2,
            "the failure screen after a throw offers no way back",
        );
    } finally {
        await stepping.close();
    }
    return checkShownBoard();
}

const PAGES: readonly PageCase[] = [
    {
        ...replayCase("start", [".replay-status__narration"]),
        alsoAt: [...WIDER_PHONES, SHORT_DESKTOP, NARROW_DESKTOP, SHORT_TABLET],
    },
    replayCase("autoplay", [".replay-controls__play[aria-pressed='true']"]),
    replayCase("viewpoint_hidden", [".replay-controls__option--hands[aria-pressed='true']"]),
    {
        ...replayCase("round_list", [".round-list__row[aria-current]", ".round-list__row--end"]),
        alsoAt: [SHORT_TABLET],
        longNames: true,
    },
    replayCase("incomplete", [".replay-status__incomplete--end"]),
    replayCase("ends_on_result", [".round-end-result__title", ".replay-status__incomplete--end"]),
    replayCase("damaged", [".replay-status__incomplete--end"]),
    { ...replayCase("double_ron", [".round-end-result__pager"]), alsoAt: [SHORT_TABLET] },
    {
        ...replayCase("result_hidden", [".round-end-result__title"]),
        required: {
            attached: [".replay-controls__option--hands[aria-pressed='true']"],
            visible: [...BOARD_VISIBLE, ".replay-controls__moves", ".round-end-result__title"],
        },
    },
    replayCase("standings", [".standings__round--jump", ".standings__cell--win"]),
    replayCase("standings_long", [".standings__round--jump", ".standings__foot-row--result"]),
    {
        check: checkThrowOnStep,
        kind: "own",
        name: "replay-throws-on-step",
        onlyAt: ["desktop-1440", "phone-se-landscape"],
        path: "/play/storybook/replay?state=throws_on_step",
        required: { visible: [...BOARD_VISIBLE, ".replay-controls__moves"] },
    },
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
    return page.evaluate(
        ({ bandSelectors, parts }) => {
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
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function lineTops(element: Element): number[] {
                const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
                const rects: DOMRect[] = [];
                for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
                    const range = document.createRange();
                    range.selectNodeContents(node);
                    rects.push(...[...range.getClientRects()].filter((rect) => rect.height > 0));
                }
                const tops = rects
                    .map((rect) => rect.top)
                    .toSorted((first, second) => first - second);
                const lineGap = Math.min(...rects.map((rect) => rect.height)) / 2;
                return tops.filter((top, index) => index === 0 || top - tops[index - 1] > lineGap);
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
            const band = bandSelectors.flatMap((selector) => {
                const element = document.querySelector(selector);
                if (element === null) {
                    return [];
                }
                const { height, width } = element.getBoundingClientRect();
                return [
                    {
                        box: box(element),
                        selector,
                        shown: element.checkVisibility() && width >= 1 && height >= 1,
                    },
                ];
            });
            const status = document.querySelector(".replay-status");
            const placeElement = status?.closest(".board-notices") ?? null;
            const placeBottom =
                placeElement === null
                    ? 0
                    : placeElement.getBoundingClientRect().top + placeElement.clientHeight;
            const measured = Object.entries(parts).flatMap(([part, selector]) => {
                const element = document.querySelector(selector);
                if (element === null) {
                    return [];
                }
                const lineHeight = Number.parseFloat(getComputedStyle(element).lineHeight);
                const rect = element.getBoundingClientRect();
                const tops = lineTops(element);
                const shown =
                    element.checkVisibility() &&
                    element.textContent.trim() !== "" &&
                    rect.width > 1 &&
                    rect.height >= lineHeight * 0.9;
                return [
                    [
                        part,
                        {
                            box: box(element),
                            lines: tops.length,
                            linesInPlace: tops.filter((top) => top + lineHeight <= placeBottom + 1)
                                .length,
                            px: Number.parseFloat(getComputedStyle(element).fontSize),
                            shown,
                        },
                    ],
                ];
            });
            return {
                atEnd: document.querySelector(".replay-status__incomplete--end") !== null,
                band,
                listControls: [
                    ...(roundList?.querySelectorAll(
                        ".round-list__close, .round-list__foot .round-list__row",
                    ) ?? []),
                    ...shownRows,
                ].map(box),
                parts: Object.fromEntries(measured),
                place:
                    placeElement === null
                        ? null
                        : {
                              box: box(placeElement),
                              clippedAcross:
                                  placeElement.scrollWidth > placeElement.clientWidth + 1,
                              clippedDown:
                                  placeElement.scrollHeight > placeElement.clientHeight + 1,
                              scrolls: ["auto", "scroll"].includes(
                                  getComputedStyle(placeElement).overflowY,
                              ),
                          },
                roundList: roundList === null ? null : box(roundList),
                status: status === null ? null : box(status),
            };
        },
        { bandSelectors: [...CORE_MOVES, ...END_MOVES, ...OPTIONS], parts: STATUS_PARTS },
    );
}

/** What a board must show of the replay: its chrome's moves, and every option unless a small board's panel is open. */
interface ReplayState {
    /** The desktop's chrome, whose switches' place holds either end too. */
    readonly desktopChrome: boolean;
    /**
     * The panel-only exception: on a board with smaller chrome a panel over it takes all but the moves' row, so the
     * options but the round list's toggle hide, and the status is compact (the position and the end's mark).
     */
    readonly compact: boolean;
}

function replayState(board: BoardMeasure): ReplayState {
    const desktopChrome =
        board.board.width >= DESKTOP_CHROME.width && board.board.height >= DESKTOP_CHROME.height;
    return { compact: !desktopChrome && board.overlay !== null, desktopChrome };
}

/** The band's controls the board must show, by selector, in its state. */
function expectedControls({ compact, desktopChrome }: ReplayState): readonly string[] {
    return [
        ...CORE_MOVES,
        ...(desktopChrome ? END_MOVES : []),
        ...(compact ? [ROUNDS_TOGGLE] : OPTIONS),
    ];
}

/**
 * The replay's controls sit on the board and the screen: every control the board's state asks for shown, large enough
 * to tap and apart from one another, covering no tile, badge or the centre, never under a panel over the board (so the
 * replay always moves on), and its round list on the board; the open list hides none of them from these checks.
 */
function checkReplayControls(
    replay: ReplayMeasure,
    {
        board,
        screen,
        state,
    }: { readonly board: BoardMeasure; readonly screen: Box; readonly state: ReplayState },
    report: PageReport,
): void {
    const expected = expectedControls(state);
    const missing = expected.filter(
        (selector) =>
            !replay.band.some((control) => control.selector === selector && control.shown),
    );
    report.expect(missing.length === 0, `replay control(s) not shown: ${missing.join(", ")}`);
    const band = replay.band.filter((control) => control.shown).map((control) => control.box);
    const controls = [...band, ...replay.listControls];
    const outside = controls.filter(
        (control) => !contains(screen, control) || !contains(board.board, control),
    );
    report.expect(
        outside.length === 0,
        `replay control(s) off the board or the screen: ${outside.map(describeBox).join(", ")}`,
    );
    const small = controls.filter(
        (control) =>
            control.width < MIN_ACTION_SIZE - EPSILON || control.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `replay controls under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
    const crowded = findOverlaps(
        band.map((control, index) => ({ box: control, group: `${index}` })),
    );
    report.expect(crowded.length === 0, `replay controls overlap: ${crowded.join(", ")}`);
    const table = [
        ...board.tiles,
        ...board.nameplates,
        ...(board.center === null ? [] : [board.center]),
    ];
    const over = band.filter((control) => table.some((covered) => intersects(control, covered)));
    report.expect(
        over.length === 0,
        `replay control(s) over a tile, a badge or the centre: ${over.map(describeBox).join(", ")}`,
    );
    if (board.overlay !== null) {
        const { box: panel } = board.overlay;
        const under = band.filter((control) => intersects(control, panel));
        report.expect(
            under.length === 0,
            `the panel ${describeBox(panel)} covers replay control(s): ${under.map(describeBox).join(", ")}`,
        );
    }
    if (replay.roundList !== null) {
        report.expect(
            contains(board.board, replay.roundList),
            `the round list ${describeBox(replay.roundList)} leaves the board`,
        );
    }
}

/** The status's parts the board must show: the position always, the narration unless compact, the end's mark there. */
function expectedParts(replay: ReplayMeasure, { compact }: ReplayState): readonly StatusPart[] {
    const incomplete = replay.parts.incomplete === undefined ? [] : (["incomplete"] as const);
    const end = compact && replay.atEnd ? (["end"] as const) : [];
    return ["position", ...(compact ? [] : (["narration"] as const)), ...incomplete, ...end];
}

/** A part of the status the state asks for: shown, at its size, and within its lines on a desktop window. */
function checkStatusPart(
    part: StatusPart,
    { desktop, text }: { readonly desktop: boolean; readonly text: StatusText | undefined },
    report: PageReport,
): void {
    if (text === undefined || !text.shown) {
        report.expect(false, `the replay's ${part} is not shown`);
        return;
    }
    const floor = REPLAY_TEXT_PX[part];
    const most = desktop ? DESKTOP_TEXT_LINES[part] : undefined;
    report.expect(
        text.px >= floor && (most === undefined || text.lines <= most),
        `the replay's ${part} at ${text.px}px on ${text.lines} line(s), past ${floor}px${most === undefined ? "" : ` on ${most}`}`,
    );
}

/**
 * The replay's status in the notices' place: on the board and the screen, wholly inside its place, which scrolls down
 * where it is too short but never clips sideways or silently, over no tile, badge, control or panel (over a panel's
 * dimming it covers only the inert table); every part the state asks for shown at its size, within its lines on a
 * desktop window, and with no panel at least three of the narration's lines (or all it has) in view at once.
 */
function checkReplayStatus(
    replay: ReplayMeasure,
    {
        board,
        desktop,
        screen,
        state,
    }: {
        readonly board: BoardMeasure;
        readonly desktop: boolean;
        readonly screen: Box;
        readonly state: ReplayState;
    },
    report: PageReport,
): void {
    const { place, status } = replay;
    if (place === null || status === null) {
        report.expect(false, "the replay shows no status in the notices' place");
        return;
    }
    report.expect(
        contains(screen, place.box) &&
            contains(board.board, place.box) &&
            contains(place.box, status),
        `the replay's status ${describeBox(status)} leaves its place ${describeBox(place.box)}, the board or the screen`,
    );
    report.expect(
        !place.clippedAcross && (!place.clippedDown || place.scrolls),
        "the replay's status overflows the notices' place sideways, or down with no way to scroll to it",
    );
    const panel = board.overlay?.box;
    const band = replay.band.filter((control) => control.shown).map((control) => control.box);
    const covered = [
        ...band,
        ...(panel === undefined ? [...board.tiles, ...board.nameplates] : [panel]),
    ];
    report.expect(
        !covered.some((box) => intersects(place.box, box)),
        `the notices' place ${describeBox(place.box)} covers a tile, a badge, a control or the panel`,
    );
    for (const part of expectedParts(replay, state)) {
        checkStatusPart(part, { desktop, text: replay.parts[part] }, report);
    }
    const { narration } = replay.parts;
    if (panel === undefined && narration !== undefined && narration.shown) {
        report.expect(
            narration.linesInPlace >= Math.min(narration.lines, MIN_NARRATION_LINES),
            `the replay's narration shows ${narration.linesInPlace} of its ${narration.lines} line(s) at once, under ${MIN_NARRATION_LINES}`,
        );
    }
}

/** The replay's controls and status on a supported screen: in landscape all of the checks, upright on the page. */
async function checkBoard({ board, page, report, screen, viewport }: BoardRun): Promise<void> {
    const replay = await measureReplay(page);
    if (replay.band.length === 0 || !viewport.supported) {
        return;
    }
    const state = replayState(board);
    if (viewport.portrait) {
        const shown = replay.band.filter((control) => control.shown).map((control) => control.box);
        const outside = shown.filter((control) => !contains(board.board, control));
        report.expect(outside.length === 0, `${outside.length} replay control(s) off the board`);
        const { position } = replay.parts;
        const panel = board.overlay?.box;
        report.expect(
            position !== undefined &&
                position.shown &&
                contains(board.board, position.box) &&
                (panel === undefined || !intersects(panel, position.box)),
            "the replay's position is not shown on the board, clear of the panel",
        );
        return;
    }
    checkReplayControls(replay, { board, screen, state }, report);
    checkReplayStatus(replay, { board, desktop: viewport.desktop, screen, state }, report);
}

/** The replay page: its stories, its states without a board, and the route stepped to the local melds. */
export const replaySurface: Surface = {
    checkBoard,
    pages: PAGES,
};
