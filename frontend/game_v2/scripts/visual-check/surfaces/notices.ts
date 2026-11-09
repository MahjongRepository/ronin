import { type Page, chromium } from "playwright";

import { type BoardMeasure, measureBoxes } from "../board-measure.ts";
import { type Box, EPSILON, MIN_ACTION_SIZE, contains, describeBox, intersects } from "../boxes.ts";
import { boardCase, decisionCase } from "../cases.ts";
import {
    type BoardRun,
    type PageCase,
    type PageReport,
    type PageRun,
    SELECTOR_TIMEOUT_MS,
    type Surface,
} from "../model.ts";
import {
    FLOOR,
    MID_DESKTOP,
    NARROW_DESKTOP,
    SHORTEST_REGULAR_DESKTOP,
    SMALLEST_WINDOW,
} from "../viewports.ts";

/** The stacked story's notices in the stack's order: the ongoing condition, then the acknowledgement. */
const STACK_ORDER = ["tile_sprite", "refused"];
const SHOW_ALL = ".board-notice__more";
const SHEET = ".notice-sheet";
/** The floor's size, where a desktop's notice is made to clamp so its sheet can be opened from "Show all". */
const CLAMPING_SIZE = { height: 375, width: 667 };
/** The faces' notice over a round result the player still has to confirm, which the keys' check goes on to. */
const OVER_CONFIRM = "/play/storybook/decisions?state=notice_over_confirm";
const SHEET_OVER_DECISION = "/play/storybook/decisions?state=notice_sheet_decision";
const CONFIRM = ".round-end-result__confirm";
/** The long notices also checked where the smaller window gives the notices their narrowest field of their own. */
const NARROW_FIELD = [FLOOR, SMALLEST_WINDOW];
/** The least width of the notices' own place, in its notices' ems: a few words a line, never a column of single words. */
const MIN_NOTICE_MEASURE = 7.5;

/**
 * The notices' worst cases: the stack on the desktops too, the long ones also in the smaller window's field, the keys on both engines, and every other once at the floor. The single
 * notices the stack holds (a refused move, faces that did not load) are left out.
 */
const PAGES: readonly PageCase[] = [
    decisionCase("connection_lost", [".board-notice--warning", ".game-menu__alert"]),
    {
        ...decisionCase("notices_stacked", [".board-notice--warning", ".hand-tile--selectable"]),
        at: [FLOOR, MID_DESKTOP, SHORTEST_REGULAR_DESKTOP, NARROW_DESKTOP],
    },
    {
        ...decisionCase("notice_long", [".board-notice--error"]),
        at: NARROW_FIELD,
    },
    {
        ...decisionCase("notice_over_confirm", [".board-notice--warning", CONFIRM]),
        at: NARROW_FIELD,
    },
    {
        ...decisionCase("notice_sheet_decision", [
            `${SHEET} .notice-sheet__close`,
            `${SHEET} .notice-sheet__seconds`,
        ]),
        at: NARROW_FIELD,
    },
    decisionCase("notice_sheet_confirm", [
        `${SHEET} .notice-sheet__close`,
        `${SHEET} .notice-sheet__seconds`,
    ]),
    {
        ...boardCase("board-notice-second-line", "?state=worst&notice=long", [
            ".board-notice--error",
        ]),
        longNames: true,
    },
    {
        at: [FLOOR, MID_DESKTOP],
        check: checkSheetKeys,
        kind: "own",
        name: "notices-sheet-keys",
        path: "/play/storybook/decisions?state=notices_stacked",
        required: { visible: [".board-notice--warning", ".hand-tile--selectable"] },
    },
    {
        at: [FLOOR, MID_DESKTOP],
        check: checkPrecedence,
        kind: "own",
        name: "notices-precedence",
        path: "/play/storybook/decisions?state=notice_sheet_leave",
        required: { visible: [".leave-confirm__stay"] },
    },
];

/**
 * A notice over the table never hides a tile, a nameplate, the centre, the decision's buttons and timer or the panel over the
 * board, however long it stays.
 */
function checkNotices(
    { center, notices }: { readonly notices: readonly Box[]; readonly center: readonly Box[] },
    board: BoardMeasure,
    report: PageReport,
): void {
    const covered = [
        ...board.tiles,
        ...board.nameplates,
        ...center,
        ...(board.decisionCorner?.buttons ?? []),
        ...(board.timer === null ? [] : [board.timer]),
        ...(board.overlay === null ? [] : [board.overlay.box]),
    ];
    const over = notices.filter((notice) => covered.some((box) => intersects(notice, box)));
    report.expect(
        over.length === 0,
        `notice(s) over a tile, plate, the centre, a decision button, the timer or panel: ${over.map(describeBox).join(", ")}`,
    );
    const outside = notices.filter((notice) => !contains(board.board, notice));
    report.expect(outside.length === 0, `${outside.length} notice(s) off the board`);
}

/** One notice's clamp as drawn: its lines, what its text shows and holds, its "Show all" and its box. */
interface NoticeClamp {
    readonly id: string;
    readonly clampable: boolean;
    /** Left out of a place too short for the stack, its "Show all" on the last one shown standing for it. */
    readonly left: boolean;
    readonly lines: number | null;
    readonly shownHeight: number;
    /** A clamped text's scroll height, a whole one's text as laid out, which its way out's target never adds to. */
    readonly wholeHeight: number;
    readonly lineHeight: number;
    readonly showAll: boolean;
    readonly height: number;
    readonly withinWidth: boolean;
}

/** The notices' place: each notice's clamp, and whether the place hides any of its stack. */
interface PlaceClamp {
    readonly notices: readonly NoticeClamp[];
    readonly overflows: boolean;
    /** It holds a replay's status under the notices, which may scroll its own way. */
    readonly status: boolean;
    /** Its width in its notices' ems, or null where it is the reserve over a phone's panel. */
    readonly measure: number | null;
}

function measureClamp(page: Page): Promise<PlaceClamp | null> {
    return page.evaluate((showAll) => {
        const place = document.querySelector(".game-board .board-notices");
        if (place === null) {
            return null;
        }
        const notices = [...place.querySelectorAll(".board-notice")].map((notice) => {
            const body = notice.querySelector(".board-notice__body");
            const more = notice.querySelector(showAll);
            const lines =
                notice.getAttribute("data-clamped") === null
                    ? null
                    : Number(getComputedStyle(notice).getPropertyValue("--notice-lines"));
            const box = notice.getBoundingClientRect();
            const room = place.getBoundingClientRect();
            const text = document.createRange();
            if (body !== null) {
                text.selectNodeContents(body);
            }
            const textHeight =
                text.getBoundingClientRect().bottom - (body?.getBoundingClientRect().top ?? 0);
            return {
                clampable: more !== null,
                height: box.height,
                id: notice.getAttribute("data-notice") ?? "",
                left: notice.hasAttribute("data-overflow"),
                lineHeight:
                    body === null ? 0 : Number.parseFloat(getComputedStyle(body).lineHeight),
                lines,
                showAll: more !== null && more.getBoundingClientRect().height > 0,
                shownHeight: body?.clientHeight ?? 0,
                wholeHeight: lines === null ? textHeight : (body?.scrollHeight ?? 0),
                withinWidth: box.left >= room.left - 1 && box.right <= room.right + 1,
            };
        });
        const board = place.closest(".game-board")?.getBoundingClientRect();
        const room = place.getBoundingClientRect();
        const first = place.querySelector(".board-notice");
        const reserve = board !== undefined && room.left > board.left + board.width / 2;
        return {
            measure:
                first === null || reserve
                    ? null
                    : room.width / Number.parseFloat(getComputedStyle(first).fontSize),
            notices,
            overflows: place.scrollHeight > place.clientHeight + 1,
            status: place.querySelector(".replay-status") !== null,
        };
    }, SHOW_ALL);
}

/**
 * One notice the board may open whole: shown whole with no "Show all", or clamped to whole lines (hiding some, unless
 * it stands for notices left out after it) with "Show all" and at least a tap target's height.
 */
function checkNoticeClamp(notice: NoticeClamp, standsForMore: boolean, report: PageReport): void {
    if (notice.lines === null) {
        report.expect(
            notice.wholeHeight <= notice.shownHeight + EPSILON && !notice.showAll,
            `the ${notice.id} notice hides part of its text with no "Show all"`,
        );
        return;
    }
    const wholeLines =
        Math.abs(notice.shownHeight - notice.lines * notice.lineHeight) <= EPSILON + 0.5;
    report.expect(
        wholeLines && (standsForMore || notice.wholeHeight > notice.shownHeight + EPSILON),
        `the ${notice.id} notice is clamped to ${notice.shownHeight}px of its ${notice.wholeHeight}px, not ${notice.lines} whole line(s) of ${notice.lineHeight}px`,
    );
    report.expect(
        notice.showAll && notice.height >= MIN_ACTION_SIZE - EPSILON,
        `the clamped ${notice.id} notice shows no "Show all", or is under ${MIN_ACTION_SIZE}px high (${notice.height}px)`,
    );
}

/**
 * A notice the board may open whole shows its text whole, or, clamped, whole lines of it with "Show all" (the notice,
 * its target, at least 40px high); and a stack of such notices fits its place, never scrolled or cut, nor any notice
 * wider than the place.
 */
function checkClamp(place: PlaceClamp, report: PageReport): void {
    report.expect(
        place.measure === null || place.measure >= MIN_NOTICE_MEASURE,
        `the notices' place is ${place.measure?.toFixed(1)}em wide, under ${MIN_NOTICE_MEASURE}em: its notices break into word columns`,
    );
    const shown = place.notices.filter((notice) => !notice.left);
    const leftOut = place.notices.length - shown.length;
    const last = shown.at(-1);
    const wide = shown.filter((notice) => !notice.withinWidth).map((notice) => notice.id);
    report.expect(
        wide.length === 0,
        `notice(s) wider than their place, cut at its side: ${wide.join(", ")}`,
    );
    if (leftOut > 0) {
        report.expect(
            last?.showAll === true,
            `${leftOut} notice(s) left out of their place with no "Show all" on the last one shown`,
        );
    }
    const clampable = shown.filter((notice) => notice.clampable);
    for (const notice of clampable) {
        checkNoticeClamp(notice, leftOut > 0 && notice === last, report);
    }
    if (clampable.length > 0 && clampable.length === shown.length && !place.status) {
        report.expect(
            !place.overflows,
            "the notices' place scrolls: its stack does not fit it, clamped",
        );
    }
}

/** The boxes of the notices a player sees: neither left out of their place nor hidden under their open sheet. */
function measureShownNotices(page: Page): Promise<readonly Box[]> {
    return page.evaluate(() =>
        [...document.querySelectorAll(".game-board .board-notice:not([data-overflow])")]
            .filter((notice) => getComputedStyle(notice).visibility !== "hidden")
            .map((notice) => {
                const rect = notice.getBoundingClientRect();
                return {
                    height: rect.height,
                    left: rect.left + window.scrollX,
                    top: rect.top + window.scrollY,
                    width: rect.width,
                };
            }),
    );
}

/** A notice's way out as a tap finds it: its target's box, whether taps reach it there, and whether it reaches past. */
interface ActionTap {
    /** The tap floor's box around the button where taps at its edges reach it, else the button's own box. */
    readonly box: Box;
    /** A tap at each edge's middle of the floor's box around the button lands on the button. */
    readonly reached: boolean;
    /** A tap just outside that box, still inside the button's notice, lands on the button. */
    readonly leaks: boolean;
}

/** The notices' ways out (a Reload) a player sees, on the board and in the sheet, as a tap finds them. */
function measureShownActions(page: Page): Promise<readonly ActionTap[]> {
    return page.evaluate(
        (floor) =>
            [...document.querySelectorAll(".board-notice__action, .notice-sheet__action")]
                .filter(
                    (action) =>
                        getComputedStyle(action).visibility !== "hidden" &&
                        action.closest(".board-notice[data-overflow]") === null &&
                        action.getBoundingClientRect().width > 0,
                )
                .map((action) => {
                    const button = action.getBoundingClientRect();
                    const width = Math.max(button.width, floor);
                    const height = Math.max(button.height, floor);
                    const left = button.left + (button.width - width) / 2;
                    const top = button.top + (button.height - height) / 2;
                    function lands([pointX, pointY]: readonly number[]): boolean {
                        return (
                            document.elementFromPoint(pointX, pointY)?.closest("button") === action
                        );
                    }
                    function edge(offset: number): number[][] {
                        return [
                            [left + width / 2, top + offset],
                            [left + width / 2, top + height - offset],
                            [left + offset, top + height / 2],
                            [left + width - offset, top + height / 2],
                        ];
                    }
                    const reached = edge(1).every(lands);
                    const notice = action.closest(".board-notice")?.getBoundingClientRect();
                    const leaks =
                        notice !== undefined &&
                        edge(-3)
                            .filter(
                                ([pointX, pointY]) =>
                                    pointX > notice.left + 1 &&
                                    pointX < notice.right - 1 &&
                                    pointY > notice.top + 1 &&
                                    pointY < notice.bottom - 1,
                            )
                            .some(lands);
                    const box = reached
                        ? { height, left, top, width }
                        : {
                              height: button.height,
                              left: button.left,
                              top: button.top,
                              width: button.width,
                          };
                    return { box, leaks, reached };
                }),
        MIN_ACTION_SIZE,
    );
}

/**
 * A notice's way out is a button: taps reach it across the tap floor's box around it, which it meets wherever it shows,
 * and never past that box, so a tap elsewhere on its notice does not reload the page.
 */
function checkActionTaps(actions: readonly ActionTap[], report: PageReport): void {
    const small = actions.filter(
        ({ box }) =>
            box.width < MIN_ACTION_SIZE - EPSILON || box.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `notice action(s) under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(({ box }) => describeBox(box)).join(", ")}`,
    );
    const unreached = actions.filter((action) => !action.reached);
    report.expect(
        unreached.length === 0,
        `notice action(s) a tap at their ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE} target's edges does not reach: ${unreached.map(({ box }) => describeBox(box)).join(", ")}`,
    );
    const leaking = actions.filter((action) => action.leaks);
    report.expect(
        leaking.length === 0,
        `notice action(s) a tap past their ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE} target still reaches: ${leaking.map(({ box }) => describeBox(box)).join(", ")}`,
    );
}

async function checkBoard({ board, page, report, viewport }: BoardRun): Promise<void> {
    if (!viewport.supported) {
        return;
    }
    const notices = await measureShownNotices(page);
    const center = await measureBoxes(page, ".board-center");
    checkNotices({ center, notices }, board, report);
    checkActionTaps(await measureShownActions(page), report);
    const place = await measureClamp(page);
    if (place !== null) {
        checkClamp(place, report);
    }
}

/**
 * Record what the board's live regions (the notices' and the calls') would have read out on each change: the whole
 * region where it is atomic, else only the text a change adds, the one change an additions-only region reads.
 */
async function recordLiveRegions(page: Page): Promise<void> {
    await page.evaluate(() => {
        const heard: string[] = [];
        Reflect.set(window, "__noticesHeard", heard);
        for (const region of document.querySelectorAll(".game-board .board-announce")) {
            const atomic =
                region.getAttribute("aria-atomic") === "true" ||
                (region.getAttribute("role") === "status" &&
                    region.getAttribute("aria-atomic") !== "false");
            new MutationObserver((records) => {
                const added = records.flatMap((record) =>
                    [...record.addedNodes].map((node) => node.textContent?.trim() ?? ""),
                );
                heard.push(
                    ...(atomic ? [region.textContent.trim()] : added.filter((text) => text !== "")),
                );
            }).observe(region, { childList: true, subtree: true });
        }
    });
}

/**
 * The board's live regions read only what they gain: not atomic and relevant to additions alone, as written and, in
 * Chromium, as its accessibility tree exposes them to a screen reader.
 */
async function checkLiveRegionSemantics({
    page,
    report,
    viewport,
}: Pick<PageRun, "page" | "report" | "viewport">): Promise<void> {
    for (const selector of [
        ".game-board .board-announce--notices",
        ".game-board .board-announce--calls",
    ]) {
        const written = await page.evaluate((query) => {
            const region = document.querySelector(query);
            return region === null
                ? null
                : `${region.getAttribute("role") ?? ""}|${region.getAttribute("aria-atomic")}|${region.getAttribute("aria-relevant")}`;
        }, selector);
        report.expect(
            written === "|false|additions",
            `${selector} is not an additions-only, non-atomic live region: ${written}`,
        );
        if (viewport.engine === chromium) {
            const exposed = await exposedLive(page, selector);
            report.expect(
                exposed.live === "polite" && exposed.atomic !== true,
                `${selector} is exposed to assistive technology as ${JSON.stringify(exposed)}, not a polite non-atomic region`,
            );
        }
    }
}

/** How Chromium's accessibility tree exposes the element `selector` names: its live politeness and atomicity. */
async function exposedLive(
    page: Page,
    selector: string,
): Promise<{ readonly live: unknown; readonly atomic: unknown }> {
    const session = await page.context().newCDPSession(page);
    try {
        const { result } = await session.send("Runtime.evaluate", {
            expression: `document.querySelector(${JSON.stringify(selector)})`,
        });
        if (result.objectId === undefined) {
            return { atomic: null, live: null };
        }
        const { nodes } = await session.send("Accessibility.getPartialAXTree", {
            fetchRelatives: false,
            objectId: result.objectId,
        });
        const properties = new Map(
            (nodes[0]?.properties ?? []).map((property) => [property.name, property.value.value]),
        );
        return { atomic: properties.get("atomic") ?? null, live: properties.get("live") ?? null };
    } finally {
        await session.detach();
    }
}

async function takeHeard(page: Page): Promise<readonly string[]> {
    return page.evaluate(() => {
        const heard: unknown = Reflect.get(window, "__noticesHeard");
        return Array.isArray(heard) ? heard.splice(0).map(String) : [];
    });
}

/** What the live regions hold: each notice's text and each call's words, by region. */
function liveTexts(page: Page): Promise<{ notices: string[]; calls: string[]; shown: string[] }> {
    return page.evaluate(() => {
        const [calls, notices, shown] = [
            ".game-board .board-announce--calls p",
            ".game-board .board-announce--notices p",
            ".game-board .board-notice .board-notice__body",
        ].map((selector) =>
            [...document.querySelectorAll(selector)].map((node) => node.textContent.trim()),
        );
        return {
            calls: calls ?? [],
            notices: notices ?? [],
            shown: (shown ?? []).map((text) => text.replace(/Reload$/, "").trim()),
        };
    });
}

async function focusedMatches(page: Page, selector: string): Promise<boolean> {
    return page.evaluate((query) => document.activeElement?.matches(query) === true, selector);
}

async function sheetClosed(page: Page): Promise<boolean> {
    return page
        .waitForFunction((sheet) => document.querySelector(sheet) === null, SHEET, {
            timeout: SELECTOR_TIMEOUT_MS,
        })
        .then(() => true)
        .catch(() => false);
}

/** Open the sheet from the focused "Show all" by Enter; whether it opened with Close focused and the board inert. */
async function openSheet(page: Page, report: PageReport): Promise<void> {
    await page.locator(`.board-notice[data-notice="tile_sprite"] ${SHOW_ALL}`).focus();
    await page.keyboard.press("Enter");
    await page.waitForSelector(SHEET, { timeout: SELECTOR_TIMEOUT_MS });
    await page
        .waitForFunction(
            () => document.activeElement?.matches(".notice-sheet__close") === true,
            null,
            {
                timeout: SELECTOR_TIMEOUT_MS,
            },
        )
        .catch(() => undefined);
    const opened = await page.evaluate(() => ({
        closeFocused: document.activeElement?.matches(".notice-sheet__close") === true,
        inert: document.querySelector(".game-board .board-layout")?.hasAttribute("inert") === true,
        seconds: document.querySelector(".notice-sheet .notice-sheet__seconds") !== null,
    }));
    report.expect(opened.closeFocused, "the notice's sheet opened without Close focused");
    report.expect(opened.inert, "the board under the notice's sheet is not inert");
    report.expect(
        opened.seconds,
        "the notice's sheet over the round confirm shows no seconds left",
    );
}

/**
 * The notices' keys and announcements. On the stacked story (a refused move's acknowledgement under the faces' ongoing
 * notice, the chi's call showing): the stack in its order, each notice and the call read once by the live regions.
 * Then over the round confirm: the faces' notice clamped (a desktop at the floor's size) with "Show all"; the sheet
 * opened from it by Enter, modal (Close focused, the board inert, Tab kept inside, the seconds left shown); Escape
 * closes it alone (its event handled, nothing sent, the confirm still owed) with the focus back on "Show all", as Close
 * does; and neither the clamp nor the sheet reads anything out again.
 */
async function checkSheetKeys(
    { page, report, viewport }: PageRun,
    checkShownBoard: () => Promise<string>,
): Promise<string> {
    const summary = await checkShownBoard();
    const order = await page.evaluate(() =>
        [...document.querySelectorAll(".game-board .board-notice")].map((notice) =>
            notice.getAttribute("data-notice"),
        ),
    );
    report.expect(
        JSON.stringify(order) === JSON.stringify(STACK_ORDER),
        `the notices stack as ${JSON.stringify(order)}, not ongoing before acknowledgements ${JSON.stringify(STACK_ORDER)}`,
    );
    const live = await liveTexts(page);
    report.expect(
        JSON.stringify(live.notices) === JSON.stringify(live.shown),
        `the notices' live region holds ${JSON.stringify(live.notices)}, not each notice once ${JSON.stringify(live.shown)}`,
    );
    report.expect(
        live.calls.length === 1 && live.calls[0]?.endsWith(": Chii") === true,
        `the calls' live region holds ${JSON.stringify(live.calls)}, not the chi's call once`,
    );
    await checkLiveRegionSemantics({ page, report, viewport });
    const size = page.viewportSize();
    await page.goto(new URL(OVER_CONFIRM, page.url()).href);
    await page.waitForSelector(CONFIRM, { state: "visible", timeout: SELECTOR_TIMEOUT_MS });
    await recordLiveRegions(page);
    if (viewport.desktop) {
        await page.setViewportSize(CLAMPING_SIZE);
    }
    const clamped = await page
        .waitForSelector(`.board-notice[data-clamped] ${SHOW_ALL}`, {
            state: "visible",
            timeout: SELECTOR_TIMEOUT_MS,
        })
        .then(() => true)
        .catch(() => false);
    report.expect(
        clamped,
        'the notice over the round confirm never clamped with "Show all" at the floor\'s size',
    );
    if (!clamped) {
        return summary;
    }
    await page.evaluate(() => {
        Reflect.set(window, "__escapeUnhandled", 0);
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !event.defaultPrevented) {
                Reflect.set(
                    window,
                    "__escapeUnhandled",
                    Number(Reflect.get(window, "__escapeUnhandled")) + 1,
                );
            }
        });
    });
    await openSheet(page, report);
    for (let press = 0; press < 3; press += 1) {
        await page.keyboard.press("Tab");
    }
    report.expect(
        await page.evaluate((sheet) => document.activeElement?.closest(sheet) !== null, SHEET),
        "Tab moved the focus out of the notice's sheet",
    );
    await page.keyboard.press("Escape");
    report.expect(await sheetClosed(page), "Escape did not close the notice's sheet");
    const alone = await page.evaluate(
        (confirm) => ({
            confirm: document.querySelector(confirm) !== null,
            sent: document.querySelector(".decisions-storybook__sent") !== null,
            unhandled: Number(Reflect.get(window, "__escapeUnhandled")),
        }),
        CONFIRM,
    );
    report.expect(
        alone.unhandled === 0 && !alone.sent && alone.confirm,
        `Escape on the sheet did more than close it: ${JSON.stringify(alone)}`,
    );
    report.expect(
        await focusedMatches(page, `.board-notice[data-notice="tile_sprite"] ${SHOW_ALL}`),
        'closing the sheet by Escape did not give the focus back to "Show all"',
    );
    await openSheet(page, report);
    await page.locator(".notice-sheet__close").click();
    report.expect(await sheetClosed(page), "Close did not close the notice's sheet");
    report.expect(
        await page
            .waitForSelector(CONFIRM, { state: "visible", timeout: SELECTOR_TIMEOUT_MS })
            .then(() => true)
            .catch(() => false),
        "the round's result did not come back as the notice's sheet closed",
    );
    report.expect(
        await focusedMatches(page, `.board-notice[data-notice="tile_sprite"] ${SHOW_ALL}`),
        'closing the sheet by Close did not give the focus back to "Show all"',
    );
    const heard = await takeHeard(page);
    report.expect(
        heard.length === 0,
        `the clamp or the sheet made the live regions read: ${JSON.stringify(heard)}`,
    );
    await checkFocusAfterUnclamp(page, report, size);
    await checkCloseOverDecision(page, report);
    return summary;
}

/** Where the focus is: on a visible element of the board, never the page's body; its class for a failure. */
async function focusOnBoard(
    page: Page,
): Promise<{ readonly onBoard: boolean; readonly at: string }> {
    return page.evaluate(() => {
        const active = document.activeElement;
        const onBoard =
            active !== null &&
            active !== document.body &&
            active.closest(".game-board") !== null &&
            active.getClientRects().length > 0;
        return { at: active?.className ?? "nothing", onBoard };
    });
}

/**
 * The sheet opened from a clamped "Show all", the window then grown until that notice shows whole (its "Show all"
 * gone): Close gives the focus to the board still, never the page's body. The page's size comes back after.
 */
async function checkFocusAfterUnclamp(
    page: Page,
    report: PageReport,
    size: { readonly width: number; readonly height: number } | null,
): Promise<void> {
    await openSheet(page, report);
    await page.setViewportSize({ height: 900, width: 1440 });
    await page
        .waitForSelector(`.board-notice[data-clamped] ${SHOW_ALL}`, {
            state: "detached",
            timeout: SELECTOR_TIMEOUT_MS,
        })
        .catch(() => undefined);
    await page.locator(".notice-sheet__close").click();
    report.expect(
        await sheetClosed(page),
        "Close did not close the notice's sheet once its notice showed whole",
    );
    const focus = await focusOnBoard(page);
    report.expect(
        focus.onBoard,
        `closing the sheet after its notice showed whole left the focus at ${focus.at}`,
    );
    if (size !== null) {
        await page.setViewportSize(size);
    }
}

/**
 * The sheet open over a decision (the faces' and a refused move's notices, the turn reopened) closed by Escape: the
 * focus goes back to the board, never the page's body.
 */
async function checkCloseOverDecision(page: Page, report: PageReport): Promise<void> {
    await page.goto(new URL(SHEET_OVER_DECISION, page.url()).href);
    await page.waitForSelector(".notice-sheet__close", {
        state: "visible",
        timeout: SELECTOR_TIMEOUT_MS,
    });
    await page.locator(".notice-sheet__close").focus();
    await page.keyboard.press("Escape");
    report.expect(
        await sheetClosed(page),
        "Escape did not close the notice's sheet over a decision",
    );
    const focus = await focusOnBoard(page);
    report.expect(focus.onBoard, `closing the sheet over a decision left the focus at ${focus.at}`);
}

/**
 * The overlay's precedence: the leave question asked over an open notice's sheet shows in its place, and staying
 * (Escape) brings the sheet back.
 */
async function checkPrecedence(
    { page, report }: PageRun,
    checkShownBoard: () => Promise<string>,
): Promise<string> {
    const summary = await checkShownBoard();
    report.expect(
        (await page.locator(SHEET).count()) === 0,
        "the notice's sheet shows beside the leave question, not under it",
    );
    await page.locator(".leave-confirm__stay").focus();
    await page.keyboard.press("Escape");
    const sheet = await page
        .waitForSelector(SHEET, { timeout: SELECTOR_TIMEOUT_MS })
        .then(() => true)
        .catch(() => false);
    report.expect(sheet, "staying did not bring the notice's sheet back");
    return summary;
}

/**
 * The notices over the table: a lost connection, a refused move, faces that did not load, several stacked, a long one
 * alone and over a panel, beside the left strip's second meld line, opened whole over a decision and the round confirm,
 * under the leave question; their clamp, sheet and announcements.
 */
export const noticesSurface: Surface = {
    checkBoard,
    pages: PAGES,
};
