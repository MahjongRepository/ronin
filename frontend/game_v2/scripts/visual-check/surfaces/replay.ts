import { type Page } from "playwright";

import { type BoardMeasure } from "../board-measure.ts";
import {
    type Box,
    EPSILON,
    MIN_ACTION_SIZE,
    type Size,
    contains,
    describeBox,
    describeSize,
    findOverlaps,
    intersects,
    sameBox,
} from "../boxes.ts";
import { BOARD_VISIBLE, expectTexts } from "../cases.ts";
import {
    type BoardCase,
    type BoardRun,
    GAME_ID,
    type PageCase,
    PageRecord,
    type PageReport,
    SELECTOR_TIMEOUT_MS,
    type Surface,
    type TaskResult,
} from "../model.ts";
import {
    FLOOR,
    MID_DESKTOP,
    NARROW_DESKTOP,
    SHORT_DESKTOP,
    SHORT_TABLET,
    UPRIGHT_PHONE,
    WORST_CASES,
} from "../viewports.ts";

/** The replay's text: the least font size in px each part reads at on a landscape board. */
const REPLAY_TEXT_PX: Readonly<Record<StatusPart, number>> = {
    end: 12,
    incomplete: 12,
};

/** The most lines each part wraps to on a desktop window, the narrow one's narrow left field included. */
const DESKTOP_TEXT_LINES: Readonly<Partial<Record<StatusPart, number>>> = {
    incomplete: 4,
};

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
const OPTIONS = [".replay-controls__option--hands", ROUNDS_TOGGLE];

const REPLAY_MAX_STEPS = 300;
const REPLAY_LOCAL_MELDS = 2;

type StatusPart = "end" | "incomplete";

/** Each part of the status drawn, by its selector: the incompleteness and its compact end mark. */
const STATUS_PARTS: Readonly<Record<StatusPart, string>> = {
    end: ".replay-status__incomplete-end",
    incomplete: ".replay-status__incomplete",
};

/** A part of the status as drawn: shown (drawn at least a line high), its size, lines and box. */
interface StatusText {
    readonly shown: boolean;
    readonly px: number;
    readonly lines: number;
    readonly box: Box;
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
    /** The notices shown in the place, over the status. */
    readonly notices: readonly Box[];
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
            visible: [...BOARD_VISIBLE, ".replay-controls__moves", ...extra],
        },
    };
}

/**
 * A replay page story that shows no board, loading or why the replay cannot be shown: its screen must read the words of
 * its own state, its retry offered exactly where one may help.
 */
function replayStateCase(
    story: string,
    texts: Readonly<Record<string, string>>,
    retry: boolean | null,
): PageCase {
    return {
        at: [UPRIGHT_PHONE],
        async check({ measure, page, report }) {
            await expectTexts(page, texts);
            if (retry !== null) {
                const offered = (await page.getByRole("button", { name: "Try again" }).count()) > 0;
                report.expect(
                    offered === retry,
                    retry
                        ? "the failure screen offers no retry"
                        : "the failure screen offers a retry",
                );
            }
            return `page ${measure.scrollWidth}x${measure.scrollHeight}`;
        },
        kind: "own",
        name: `replay-${story.replaceAll("_", "-")}`,
        path: `/play/storybook/replay?state=${story}`,
        required: {
            visible: [
                retry === null ? ".replay-state" : ".replay-state--failed .replay-state__links a",
                ...Object.keys(texts),
            ],
        },
    };
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
 * A story's `prepare` that requires the replay to stand at the stop its address names (`step`, from 0), which its
 * position counts from 1.
 */
function expectStep(step: number): (page: Page) => Promise<void> {
    return async (page) => {
        await page.waitForSelector(".replay-status__step", {
            state: "attached",
            timeout: SELECTOR_TIMEOUT_MS,
        });
        const shown = await replayStep(page);
        if (shown !== step + 1) {
            throw new Error(`the replay shows step ${shown}, not its address's ${step + 1}`);
        }
    };
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

/**
 * The replay's worst cases: its first stop wherever the live board's geometry is compared with it (the notch phone's
 * insets aside), a desktop's status where its lines bind (a damaged recording's), the open round list's desktop rows, a panel over the upright and the short tablet's board, and every other
 * story once, at the floor or, with no board, upright. A story a kept one shows in a harsher form is left out (an
 * incomplete recording, under the damaged one's longer words).
 */
const PAGES: readonly PageCase[] = [
    {
        ...replayCase("start", []),
        at: [...WORST_CASES, SHORT_DESKTOP, NARROW_DESKTOP, SHORT_TABLET, UPRIGHT_PHONE],
    },
    {
        ...replayCase("seating", []),
        at: [FLOOR, UPRIGHT_PHONE],
        required: {
            visible: [".seating__name", ".seating__action", ".replay-controls__moves"],
        },
    },
    { ...replayCase("mid", []), prepare: expectStep(14) },
    replayCase("autoplay", [".replay-controls__play[aria-pressed='true']"]),
    replayCase("viewpoint_hidden", [".replay-controls__option--hands[aria-pressed='true']"]),
    {
        ...replayCase("round_list", [".round-list__row[aria-current]", ".round-list__row--end"]),
        at: [FLOOR, MID_DESKTOP, SHORT_TABLET],
        longNames: true,
    },
    {
        ...replayCase("ends_on_result", [
            ".round-end-result__kind",
            ".replay-status__incomplete--end",
        ]),
        at: [FLOOR, UPRIGHT_PHONE],
    },
    { ...replayCase("damaged", [".replay-status__incomplete--end"]), at: [FLOOR, MID_DESKTOP] },
    { ...replayCase("double_ron", [".round-end-result__pager"]), at: [FLOOR, SHORT_TABLET] },
    {
        ...replayCase("result_hidden", [".round-end-result__kind"]),
        required: {
            attached: [".replay-controls__option--hands[aria-pressed='true']"],
            visible: [...BOARD_VISIBLE, ".replay-controls__moves", ".round-end-result__kind"],
        },
    },
    replayCase("game_end", [".seating__ending--tobi", ".seating__result--positive"]),
    replayStateCase("loading", { ".replay-state__detail": "Loading the replay…" }, null),
    replayStateCase(
        "waiting",
        { ".replay-state__detail": "Waiting for the replay to be saved…" },
        null,
    ),
    replayStateCase("not_found", { ".replay-state__title": "Replay not found" }, true),
    replayStateCase(
        "unreachable",
        {
            ".replay-state__detail": "The server could not be reached.",
            ".replay-state__title": "The replay could not be loaded",
        },
        true,
    ),
    replayStateCase(
        "unsupported",
        {
            ".replay-state__detail":
                'It was recorded in format "0.1", which this page cannot read.',
            ".replay-state__title": "This replay cannot be shown",
        },
        false,
    ),
    replayStateCase(
        "no_round",
        {
            ".replay-state__detail": "The recording stops before the first deal.",
            ".replay-state__title": "This replay holds no round",
        },
        false,
    ),
    {
        at: [FLOOR, SHORT_DESKTOP],
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
            /** Each line's middle: its text's, which its line box centres whatever the leading. */
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function lineMiddles(element: Element): number[] {
                const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
                const rects: DOMRect[] = [];
                for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
                    const range = document.createRange();
                    range.selectNodeContents(node);
                    rects.push(...[...range.getClientRects()].filter((rect) => rect.height > 0));
                }
                const middles = rects
                    .map((rect) => rect.top + rect.height / 2)
                    .toSorted((first, second) => first - second);
                const lineGap = Math.min(...rects.map((rect) => rect.height)) / 2;
                return middles.filter(
                    (middle, index) => index === 0 || middle - middles[index - 1] > lineGap,
                );
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
            const measured = Object.entries(parts).flatMap(([part, selector]) => {
                const element = document.querySelector(selector);
                if (element === null) {
                    return [];
                }
                const lineHeight = Number.parseFloat(getComputedStyle(element).lineHeight);
                const rect = element.getBoundingClientRect();
                const middles = lineMiddles(element);
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
                            lines: middles.length,
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
                notices: [...(placeElement?.querySelectorAll(".board-notice") ?? [])]
                    .filter((notice) => notice.checkVisibility())
                    .map(box),
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
     * options but the round list's toggle hide, and the status is compact (the end's mark).
     */
    readonly compact: boolean;
}

function replayState(board: BoardMeasure): ReplayState {
    const desktopChrome = board.chrome === "regular" || board.chrome === "large";
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

/** The status's parts the board must show: an incomplete replay's note, its end's mark where compact. */
function expectedParts(replay: ReplayMeasure, { compact }: ReplayState): readonly StatusPart[] {
    const incomplete = replay.parts.incomplete === undefined ? [] : (["incomplete"] as const);
    const end = compact && replay.atEnd ? (["end"] as const) : [];
    return [...incomplete, ...end];
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
 * The replay's status in the notices' place: on the board and the screen, wholly inside its place under any notice,
 * which scrolls down where it is too short but never clips sideways or silently, over no tile, badge, control or panel (over a panel's
 * dimming it covers only the inert table); every part the state asks for shown at its size, within its lines on a
 * desktop window.
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
    const over = replay.notices.filter(
        (notice) =>
            !contains(place.box, notice) || notice.top + notice.height > status.top + EPSILON,
    );
    report.expect(
        over.length === 0,
        `notice(s) not over the replay's status ${describeBox(status)} in its place: ${over.map(describeBox).join(", ")}`,
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
}

/** The geometry the replay's board shares with live play's: the board's box, the centre's, a river and an own tile. */
interface SharedGeometry {
    readonly board: Box;
    readonly center: Box | null;
    readonly riverTile: number | null;
    readonly ownTile: Size | null;
}

const SHARED_GEOMETRY = new PageRecord<SharedGeometry>();

/** The live game's own route at its turn, and the replay's pages whose board must lie as its board does. */
const LIVE_REFERENCE = "game-turn";
const SAME_AS_LIVE: ReadonlySet<string> = new Set(["replay-start", "replay"]);

/** The board's river tile as the sizing rule sets it (`--rw`), laid or not: a turn's rivers may still be empty. */
async function measureRiverTile(page: Page): Promise<number | null> {
    const length = await page.evaluate(() => {
        const center = document.querySelector(".game-board .board-center");
        return center === null ? "" : getComputedStyle(center).getPropertyValue("--rw");
    });
    const pixels = Number.parseFloat(length);
    return Number.isFinite(pixels) ? pixels : null;
}

async function sharedGeometry(page: Page, board: BoardMeasure): Promise<SharedGeometry> {
    return {
        board: board.board,
        center: board.center,
        ownTile: board.localTileSizes[0] ?? null,
        riverTile: await measureRiverTile(page),
    };
}

function sameLength(one: number | null, other: number | null): boolean {
    return one === null || other === null ? one === other : Math.abs(one - other) <= EPSILON;
}

function sameGeometry(first: SharedGeometry, second: SharedGeometry): boolean {
    const centers =
        first.center === null || second.center === null
            ? first.center === second.center
            : sameBox(first.center, second.center);
    return (
        sameBox(first.board, second.board) &&
        centers &&
        sameLength(first.ownTile?.width ?? null, second.ownTile?.width ?? null) &&
        sameLength(first.ownTile?.height ?? null, second.ownTile?.height ?? null) &&
        sameLength(first.riverTile, second.riverTile)
    );
}

function describeGeometry({ board, center, ownTile, riverTile }: SharedGeometry): string {
    return `board ${describeBox(board)}, centre ${center === null ? "none" : describeBox(center)}, own tile ${ownTile === null ? "none" : describeSize(ownTile)}, river tile ${riverTile ?? "none"}px`;
}

/**
 * The replay's board is live play's (the spec's Replay: its geometry identical): at each viewport where both were
 * measured in landscape, its box, its centre, its river tile and its own tile stand as the live game's at its turn.
 */
function checkLiveGeometry(results: readonly TaskResult[]): string[] {
    return results.flatMap(({ page, report, viewport }) => {
        const replay = SHARED_GEOMETRY.read(report);
        if (!SAME_AS_LIVE.has(page) || replay === undefined) {
            return [];
        }
        const reference = results.find(
            (result) => result.page === LIVE_REFERENCE && result.viewport === viewport,
        );
        const live = reference === undefined ? undefined : SHARED_GEOMETRY.read(reference.report);
        if (live === undefined) {
            return [
                `${viewport}: ${page}'s board has no live ${LIVE_REFERENCE} measured at this viewport to match (check them together)`,
            ];
        }
        if (sameGeometry(live, replay)) {
            return [];
        }
        return [
            `${viewport}: ${page}'s board is not the live game's: ${describeGeometry(replay)} against ${describeGeometry(live)}`,
        ];
    });
}

/** The overlay's tile unit (`.board-overlay`'s): its clamp in px, its hand and height in units, its chrome in rem. */
const OVERLAY_UNIT = { chromeRem: 3, handUnits: 1000, heightUnits: 640, max: 0.8, min: 0.25 };
const UNIT_EPSILON = 0.001;

/**
 * A seating panel over a replay's board at the desktop's chrome stands in the board's free box (`--geo-overlay-*`),
 * centred on the board, and its tile unit leaves the free box's sides beside it.
 */
async function checkSeatingField(page: Page, report: PageReport): Promise<void> {
    const field = await page.evaluate(() => {
        const board = document.querySelector(".game-board");
        const overlay = board?.querySelector(":scope > .board-overlay:has(.seating)") ?? null;
        const panel = overlay?.querySelector(":scope > .board-overlay__panel") ?? null;
        if (board === null || overlay === null || panel === null) {
            return null;
        }
        const boardStyle = getComputedStyle(board);
        const boardBox = board.getBoundingClientRect();
        const panelBox = panel.getBoundingClientRect();
        return {
            height: board.clientHeight,
            left: Number.parseFloat(boardStyle.getPropertyValue("--geo-overlay-left")),
            panelLeft: panelBox.left - boardBox.left,
            panelRight: panelBox.right - boardBox.left,
            rem: Number.parseFloat(getComputedStyle(document.documentElement).fontSize),
            right: Number.parseFloat(boardStyle.getPropertyValue("--geo-overlay-right")),
            unit: Number.parseFloat(getComputedStyle(overlay).getPropertyValue("--board-unit")),
            width: board.clientWidth,
        };
    });
    if (field === null) {
        return;
    }
    const { height, left, panelLeft, panelRight, rem, right, unit, width } = field;
    report.expect(
        panelLeft >= left - EPSILON && panelRight <= width - right + EPSILON,
        `the replay's seating spans ${panelLeft}-${panelRight}px, outside its free box ${left}-${width - right}px`,
    );
    report.expect(
        Math.abs(panelLeft + panelRight - width) <= 2 * EPSILON,
        `the replay's seating spans ${panelLeft}-${panelRight}px, not centred on the ${width}px board`,
    );
    const expected = Math.min(
        OVERLAY_UNIT.max,
        Math.max(
            OVERLAY_UNIT.min,
            Math.min(
                (width - OVERLAY_UNIT.chromeRem * rem - left - right) / OVERLAY_UNIT.handUnits,
                height / OVERLAY_UNIT.heightUnits,
            ),
        ),
    );
    report.expect(
        Math.abs(unit - expected) <= UNIT_EPSILON,
        `the replay's seating takes a tile unit of ${unit}px, not its free box's ${expected.toFixed(4)}px`,
    );
}

/** The replay's controls and status on a supported screen: in landscape all of the checks, upright on the page. */
async function checkBoard({ board, page, report, screen, viewport }: BoardRun): Promise<void> {
    if (!viewport.portrait) {
        SHARED_GEOMETRY.keep(report, await sharedGeometry(page, board));
    }
    const replay = await measureReplay(page);
    if (replay.band.length === 0 || !viewport.supported) {
        return;
    }
    const state = replayState(board);
    if (viewport.portrait) {
        const shown = replay.band.filter((control) => control.shown).map((control) => control.box);
        const outside = shown.filter((control) => !contains(board.board, control));
        report.expect(outside.length === 0, `${outside.length} replay control(s) off the board`);
        return;
    }
    checkReplayControls(replay, { board, screen, state }, report);
    checkReplayStatus(replay, { board, desktop: viewport.desktop, screen, state }, report);
    if (state.desktopChrome) {
        await checkSeatingField(page, report);
    }
}

/** The replay page: its stories, its states without a board, and the route stepped to the local melds. */
export const replaySurface: Surface = {
    checkBoard,
    checkResults: checkLiveGeometry,
    pages: PAGES,
};
