import { type Page } from "playwright";

import { type BoardMeasure, measureBoxes } from "../board-measure.ts";
import {
    type Box,
    EPSILON,
    MIN_ACTION_SIZE,
    type Size,
    contains,
    describeBox,
    describeSize,
    intersects,
} from "../boxes.ts";
import { boardCase, decisionCase, expectAnnounced, expectTexts } from "../cases.ts";
import {
    type BoardCase,
    type BoardRun,
    GAME_ID,
    type PageCase,
    type PageReport,
    type PageRun,
    SELECTOR_TIMEOUT_MS,
    type Surface,
    type Viewport,
} from "../model.ts";
import { checkVisible } from "../page-checks.ts";
import { MIN_TEXT_PX } from "../text.ts";
import {
    FLOOR,
    MID_DESKTOP,
    NOTCH_PHONE,
    SHORTEST_REGULAR_DESKTOP,
    SMALLEST_WINDOW,
    SMALL_WINDOWS,
    UPRIGHT_PHONE,
    WORST_CASES,
} from "../viewports.ts";

/** The least room between two names on a line of a result's scores, so each name and its end read as one. */
const MIN_RESULT_NAME_GAP = 12;

/**
 * The final standings over the board: its panel, the sheet its rounds scroll in, the totals that stick to the sheet's
 * foot, its controls (its ways on and the rounds shown whole in the sheet) and its smallest text.
 */
interface StandingsMeasure {
    readonly panel: Box;
    readonly sheet: Box;
    readonly sheetScroll: Size;
    readonly sheetClient: Size;
    readonly sheetOverflowY: string;
    readonly totals: Box | null;
    readonly controls: readonly Box[];
    readonly minFontPx: number;
    /** A positive and a negative round's cell and result, where the ledger has one: the colour each shows and its tone's. */
    readonly tones: readonly ToneColour[];
}

interface ToneColour {
    readonly cell: string;
    readonly shown: string | null;
    readonly tone: string;
}

/** A round result over the board storybook's board, one of its result stories, at a page of it. */
function resultCase(result: string, query: string, extra: readonly string[]): BoardCase {
    return boardCase(
        `board-result-${result.replaceAll("_", "-")}`,
        `?overlay=round_end&result=${result}${query}`,
        [".board-overlay__panel", ...extra],
    );
}

/** A result story whose panel must read its family's heading and label, the state it proves. */
function resultStory(
    result: string,
    texts: Readonly<Record<string, string>>,
    extra: readonly string[] = [],
): PageCase {
    return {
        ...resultCase(result, "", [...Object.keys(texts), ...extra]),
        prepare: (page) => expectTexts(page, texts),
    };
}

/** A decisions story whose result panel is forced shorter than its content: the live confirm must stay in view. */
function scrollingResultCase(story: string, extra: readonly string[]): PageCase {
    return {
        ...decisionCase(story, extra),
        name: `decisions-${story.replaceAll("_", "-")}-scrolling`,
        panelScrolls: true,
        prepare: forceResultPanelShort,
    };
}

/** The forced result panel's height: under every result's content, above its foot of scores and controls. */
const FORCED_PANEL_HEIGHT = "12rem";

async function forceResultPanelShort(page: Page): Promise<void> {
    await page.addStyleTag({
        content: `.board-overlay__panel:has(> .round-end-result) { max-height: ${FORCED_PANEL_HEIGHT} !important; }`,
    });
}

/** An upright board's result panel made as tall as its overlay allows: it must still leave the page's corner clear. */
async function forceResultPanelTall(page: Page): Promise<void> {
    await page.addStyleTag({
        content: ".board-overlay__panel:has(> .round-end-result) { height: 100vh !important; }",
    });
}

/** What a rotate story shows: an element proving it, whether it counts seconds down, and the words it must read. */
interface RotateExpectation {
    readonly content: string;
    readonly countdown: boolean;
    /** Words it shows a player. */
    readonly texts?: Readonly<Record<string, string>>;
    /** Words only its live region holds, read out and never drawn. */
    readonly announced?: Readonly<Record<string, string>>;
}

/** A rotate panel story: the panel an upright phone shows in place of the live board, reading its own state's words. */
function rotateCase(
    state: string,
    { announced = {}, content, countdown, texts = {} }: RotateExpectation,
): PageCase {
    return {
        at: [UPRIGHT_PHONE],
        async check({ page, report }) {
            await expectTexts(page, texts);
            await expectAnnounced(page, announced);
            return checkRotatePanel(page, countdown, report);
        },
        kind: "own",
        name: `rotate-${state}`,
        path: `/play/storybook/rotate?state=${state}`,
        required: { visible: [".rotate-panel", content] },
    };
}

const LEAVE_QUESTION = ".game__play .leave-confirm";

async function openLeaveQuestion(page: Page): Promise<void> {
    await page.locator(".game__play .game-menu__leave").click();
    await page.waitForSelector(LEAVE_QUESTION, { timeout: SELECTOR_TIMEOUT_MS });
}

/** Whether the focus stays in the leave question over `presses` presses of Tab. */
async function tabStaysInLeaveQuestion(page: Page, presses: number): Promise<boolean> {
    for (let press = 0; press < presses; press += 1) {
        await page.keyboard.press("Tab");
        const inside = await page.evaluate(
            (question) => document.activeElement?.closest(question) !== null,
            LEAVE_QUESTION,
        );
        if (!inside) {
            return false;
        }
    }
    return true;
}

/**
 * The live game's leave question, asked from the page's corner: it opens modal with Stay focused, the board inert and
 * Tab kept inside it, and Escape stays, closing it and giving the focus back to the corner's control that asked. The
 * board is checked before it opens, and the page is shot with it opened again.
 */
async function checkLeaveQuestion(
    { page, report }: PageRun,
    checkShownBoard: () => Promise<string>,
): Promise<string> {
    const summary = await checkShownBoard();
    await openLeaveQuestion(page);
    const opened = await page.evaluate(() => ({
        inert: document.querySelector(".game__play .board-layout")?.hasAttribute("inert") === true,
        stayFocused: document.activeElement?.matches(".game__play .leave-confirm__stay") === true,
    }));
    report.expect(opened.stayFocused, "the leave question opened without Stay focused");
    report.expect(opened.inert, "the board under the leave question is not inert");
    report.expect(
        await tabStaysInLeaveQuestion(page, 3),
        "Tab moved the focus out of the leave question",
    );
    await page.locator(".game__play .leave-confirm__stay").focus();
    await page.keyboard.press("Escape");
    const closed = await page
        .waitForFunction((question) => document.querySelector(question) === null, LEAVE_QUESTION, {
            timeout: SELECTOR_TIMEOUT_MS,
        })
        .then(() => true)
        .catch(() => false);
    report.expect(closed, "Escape did not close the leave question");
    report.expect(
        await page.evaluate(
            () => document.activeElement?.matches(".game__play .game-menu__leave") === true,
        ),
        "staying did not give the focus back to the control that asked",
    );
    await openLeaveQuestion(page);
    return summary;
}

/**
 * The panels' worst cases: the densest results (pao, a double ron's pager, a hand with its melds) and the standings
 * at the desktops and the notch phone too, the results a forced short panel makes scroll at the small windows, and
 * every other panel once, at the floor or, for the rotate panel, upright. A panel a kept one shows in a harsher form
 * is left out (the plain round end and its reconnected copy, a head bump, an all-noten draw, a double ron's first page
 * unforced, the last result and its reopened copy, a kick, the leave question after a win, the rotate panel waiting
 * or counting down).
 */
const PAGES: readonly PageCase[] = [
    {
        at: [FLOOR, MID_DESKTOP],
        check: checkLeaveQuestion,
        checkpoint: "turn",
        kind: "own",
        name: "game-leave-question",
        path: `/play/${GAME_ID}`,
        required: { visible: [".game__play .game-menu__leave", ".game__play .hand-tile"] },
    },
    resultCase("yakuman", "", [".round-end-result__limit"]),
    resultCase("triple_ron", "", [".round-end-result__from"]),
    boardCase("board-standings-stick-lost", "?overlay=game_end&leftover=lost", [
        ".standings__unawarded",
    ]),
    {
        ...resultCase("double_ron", "&page=1", [".round-end-result__pager"]),
        at: [FLOOR, MID_DESKTOP],
    },
    {
        ...resultCase("sanbaiman", "", [".round-end-result__hand .meld"]),
        at: [FLOOR, MID_DESKTOP],
        contrast: true,
    },
    { ...resultCase("pao", "", [".round-end-result__notes"]), at: [...WORST_CASES, NOTCH_PHONE] },
    resultCase("exhaustive", "", [".round-end-result__tenpai .tile"]),
    resultStory("tsumo", {
        ".round-end-result__kind": "Tsumo",
        ".round-end-result__win-label": "Tsumo",
    }),
    resultStory("ron", {
        ".round-end-result__from": "from Charlie",
        ".round-end-result__kind": "Ron",
        ".round-end-result__limit": "Haneman",
    }),
    resultStory("dealer", {
        ".round-end-result__limit": "Mangan",
        ".round-end-result__points": "12,000",
        ".round-end-result__wind": "East",
    }),
    resultStory("kazoe", { ".round-end-result__limit": "Kazoe Yakuman" }),
    resultStory("chankan", {
        ".round-end-result__from": "robbing Alice's kan",
        ".round-end-result__kind": "Ron",
    }),
    resultStory(
        "nagashi",
        {
            ".round-end-result__from": "by Alice",
            ".round-end-result__kind": "Draw",
            ".round-end-result__title": "Nagashi Mangan",
        },
        [".round-end-result__tenpai .tile"],
    ),
    resultStory("kyuushu", {
        ".round-end-result__from": "declared by Alice",
        ".round-end-result__title": "Nine terminals",
    }),
    resultStory("four_winds", {
        ".round-end-result__from": "Abortive draw",
        ".round-end-result__title": "Four winds",
    }),
    resultStory("four_riichi", {
        ".round-end-result__from": "Abortive draw",
        ".round-end-result__title": "Four riichi",
    }),
    resultStory("four_kans", {
        ".round-end-result__from": "Abortive draw",
        ".round-end-result__title": "Four kans",
    }),
    {
        ...boardCase("board-standings", "?overlay=game_end", [
            ".standings__ending--length",
            ".standings__foot-row--leftover",
            ".standings__cell .standings__riichi",
            ".standings__cell .standings__mark--deal-in",
            ".standings__legend",
        ]),
        at: [...WORST_CASES, NOTCH_PHONE, SHORTEST_REGULAR_DESKTOP, ...SMALL_WINDOWS],
    },
    {
        kind: "board",
        name: "decisions-game-start",
        path: "/play/storybook/decisions?state=game_start",
        required: { visible: [".game-start__seat--viewer", ".game-start__status", ".nameplate"] },
    },
    {
        ...decisionCase("round_end", [".round-end-result__confirm"]),
        at: [UPRIGHT_PHONE],
        name: "decisions-round-end-tall",
        prepare: forceResultPanelTall,
    },
    scrollingResultCase("round_end", [
        ".round-end-result__confirm",
        ".round-end-result__countdown",
    ]),
    {
        ...scrollingResultCase("double_ron_first", [
            ".round-end-result__pager",
            ".round-end-result__confirm",
            ".round-end-result__countdown",
        ]),
        at: [FLOOR, MID_DESKTOP, ...SMALL_WINDOWS],
    },
    {
        ...decisionCase("double_ron_last", [
            ".round-end-result__confirm",
            ".round-end-result__countdown",
        ]),
        prepare: (page) => expectTexts(page, { ".board-overlay .round-end-result__page": "2 / 2" }),
    },
    decisionCase("waiting", [".round-end-result__waiting"]),
    decisionCase("standings", [
        ".standings__ending--tobi",
        ".standings__cell--win",
        ".standings__foot-row--result",
        ".standings__actions a[href*='seat=1']",
    ]),
    {
        ...decisionCase("out_of_step_result", [
            ".round-end-result__uncertain",
            ".round-end-result__confirm",
            ".round-end-result__indicator-tiles .tile",
        ]),
        at: [FLOOR, SMALLEST_WINDOW],
    },
    decisionCase("out_of_step_standings", [".standings__incomplete"]),
    decisionCase("leave_confirm", [".leave-confirm__leave", ".leave-confirm__stay"]),
    rotateCase("leave", { content: ".rotate-panel .leave-confirm__leave", countdown: false }),
    rotateCase("ended", { content: ".rotate-panel .failure-panel__reload", countdown: false }),
    rotateCase("expired", {
        announced: { ".rotate-panel__announce": "Time is up" },
        content: ".rotate-panel__decision--expired",
        countdown: false,
        texts: {
            ".rotate-panel__decision--expired":
                "You can call the last discard, and its time is up: the server makes the move.",
        },
    }),
    rotateCase("reconnecting", {
        content: ".rotate-panel .connection-status.status-disconnected",
        countdown: false,
        texts: { ".rotate-panel .connection-status": "Reconnecting" },
    }),
    rotateCase("result", {
        content: ".rotate-panel__seconds",
        countdown: true,
        texts: {
            ".rotate-panel__decision p":
                "The round's result awaits your OK. Its timer keeps running while the phone is upright.",
            ".rotate-panel__seconds": "8",
        },
    }),
    rotateCase("untimed", {
        content: ".rotate-panel__decision",
        countdown: false,
        texts: {
            ".rotate-panel__decision p":
                "It is your turn. Play continues, and your timer keeps running while the phone is upright.",
        },
    }),
];

function checkOverlay(board: BoardMeasure, viewport: Viewport, report: PageReport): void {
    const { overlay } = board;
    if (overlay === null) {
        return;
    }
    report.expect(contains(board.board, overlay.box), "the overlay panel leaves the board");
    const covered = board.menu.filter((control) => intersects(control, overlay.box));
    report.expect(
        covered.length === 0,
        `the overlay panel ${describeBox(overlay.box)} covers the page's corner: ${covered.map(describeBox).join(", ")}`,
    );
    if (viewport.supported) {
        report.expect(
            overlay.scroll.width <= overlay.client.width + EPSILON &&
                (overlay.result || overlay.scroll.height <= overlay.client.height + EPSILON),
            `the overlay panel's content overflows it: ${describeSize(overlay.scroll)} > ${describeSize(overlay.client)}`,
        );
    }
}

/**
 * Upright, where the notices' own checks do not run, a notice shown over a panel stands in its reserve under the right
 * strip's end, clear of the panel, which stops above the foreground for it.
 */
async function checkUprightNotices(page: Page, panel: Box, report: PageReport): Promise<void> {
    const notices = await page.evaluate(() =>
        [...document.querySelectorAll(".game-board .board-notice")]
            .filter((notice) => notice.checkVisibility({ visibilityProperty: true }))
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
    const over = notices.filter((notice) => intersects(notice, panel));
    report.expect(
        over.length === 0,
        `notice(s) over the upright panel ${describeBox(panel)}: ${over.map(describeBox).join(", ")}`,
    );
}

/** What a round result's panel shows at one end of its scroll. */
interface ResultPanelView {
    readonly scrollTop: number;
    /** The panel's visible area, inside its border. */
    readonly shown: Box;
    /** The primary button and its countdown, which stay in view at either end. */
    readonly kept: readonly { readonly name: string; readonly box: Box }[];
    readonly pager: readonly Box[];
    readonly foot: Box | null;
    /** The lowest edge of the result's content above its foot. */
    readonly contentBottom: number;
}

/** A round result's panel at the start and the end of its scroll, restored to its start after. */
interface ResultPanelMeasure {
    readonly overflowY: string;
    readonly scroll: Size;
    readonly client: Size;
    readonly start: ResultPanelView;
    readonly end: ResultPanelView;
}

function measureResultPanel(page: Page): Promise<ResultPanelMeasure | null> {
    return page.evaluate(async () => {
        const panel = document.querySelector(".board-overlay__panel:has(> .round-end-result)");
        if (!(panel instanceof HTMLElement)) {
            return null;
        }
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
        function view(shownPanel: HTMLElement): ResultPanelView {
            const outer = box(shownPanel);
            const foot = shownPanel.querySelector(".round-end-result__foot");
            const content = [
                ...shownPanel.querySelectorAll(".round-end-result > :not(.round-end-result__foot)"),
            ].map(box);
            return {
                contentBottom: Math.max(...content.map((part) => part.top + part.height)),
                foot: foot === null ? null : box(foot),
                kept: [
                    ...shownPanel.querySelectorAll(
                        ".round-end-result__confirm, .round-end-result__countdown",
                    ),
                ].map((element) => ({ box: box(element), name: element.className.split(" ")[0] })),
                pager: [...shownPanel.querySelectorAll(".round-end-result__page-btn")].map(box),
                scrollTop: shownPanel.scrollTop,
                shown: {
                    height: shownPanel.clientHeight,
                    left: outer.left + shownPanel.clientLeft,
                    top: outer.top + shownPanel.clientTop,
                    width: shownPanel.clientWidth,
                },
            };
        }
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function nextFrame(): Promise<void> {
            return new Promise((done) => {
                requestAnimationFrame(() => done());
            });
        }
        panel.scrollTo({ behavior: "instant", top: 0 });
        await nextFrame();
        const start = view(panel);
        panel.scrollTo({ behavior: "instant", top: panel.scrollHeight });
        await nextFrame();
        const end = view(panel);
        panel.scrollTo({ behavior: "instant", top: 0 });
        await nextFrame();
        return {
            client: { height: panel.clientHeight, width: panel.clientWidth },
            end,
            overflowY: getComputedStyle(panel).overflowY,
            scroll: { height: panel.scrollHeight, width: panel.scrollWidth },
            start,
        };
    });
}

/**
 * A round result that does not fit its panel scrolls inside it, never clipped: its content reaches past its foot at the
 * scroll's end, and its primary button and countdown stay wholly in view at both ends, the winner pager at the start.
 * A case that forces the panel short first proves that it overflows; on a desktop, any other result fits whole.
 */
function checkResultPanel(
    panel: ResultPanelMeasure | null,
    { desktop, mustScroll }: { readonly desktop: boolean; readonly mustScroll: boolean },
    report: PageReport,
): void {
    if (panel === null) {
        report.expect(!mustScroll, "no round result panel to scroll");
        return;
    }
    const overflows = panel.scroll.height > panel.client.height + EPSILON;
    report.expect(
        overflows || !mustScroll,
        `the result panel forced short still fits: ${describeSize(panel.scroll)} in ${describeSize(panel.client)}`,
    );
    report.expect(
        !overflows || mustScroll || !desktop,
        `a desktop's result does not fit its panel: ${describeSize(panel.scroll)} in ${describeSize(panel.client)}`,
    );
    const ends = [
        ["start", panel.start],
        ["end", panel.end],
    ] as const;
    for (const [end, view] of ends) {
        const hidden = view.kept.filter(({ box }) => !contains(view.shown, box));
        report.expect(
            hidden.length === 0,
            `at the scroll's ${end}, the result's ${hidden.map(({ name }) => name).join(", ")} leave(s) its panel's view`,
        );
    }
    const hiddenPager = panel.start.pager.filter((button) => !contains(panel.start.shown, button));
    report.expect(
        hiddenPager.length === 0,
        `the winner pager leaves the result panel's view: ${hiddenPager.map(describeBox).join(", ")}`,
    );
    if (!overflows) {
        return;
    }
    report.expect(
        panel.overflowY === "auto" || panel.overflowY === "scroll",
        `the result overflows its panel (${describeSize(panel.scroll)} in ${describeSize(panel.client)}) with overflow-y ${panel.overflowY}`,
    );
    report.expect(
        panel.end.scrollTop > panel.start.scrollTop + EPSILON,
        "the result overflows its panel but does not scroll",
    );
    const { contentBottom, foot, shown } = panel.end;
    const limit = Math.min(shown.top + shown.height, foot?.top ?? Infinity);
    report.expect(
        contentBottom <= limit + EPSILON,
        `at the scroll's end the result's content ends at ${contentBottom.toFixed(0)}px, under its foot or panel at ${limit.toFixed(0)}px`,
    );
}

/** The page a result's pager shows, from 1, or NaN without one. */
async function shownResultPage(page: Page): Promise<number> {
    const label = page.locator(".board-overlay .round-end-result__page");
    return (await label.count()) === 0
        ? Number.NaN
        : Number.parseInt((await label.textContent()) ?? "", 10);
}

function waitForResultPage(page: Page, expected: number): Promise<boolean> {
    return page
        .waitForFunction(
            (wanted) =>
                Number.parseInt(
                    document.querySelector(".board-overlay .round-end-result__page")?.textContent ??
                        "",
                    10,
                ) === wanted,
            expected,
            { timeout: SELECTOR_TIMEOUT_MS },
        )
        .then(() => true)
        .catch(() => false);
}

/**
 * A double ron's result pages and confirms by a player's click (Playwright's, which fails on a control another covers):
 * its winner pager moves one page, on or back from the last; and where the live game's primary button shows, it turns
 * the pages to the last, whose press confirms, after which the seat waits for the others.
 */
async function checkResultPaging(page: Page, report: PageReport): Promise<void> {
    if ((await page.locator(".board-overlay .round-end-result__page-btn").count()) === 0) {
        return;
    }
    const before = await shownResultPage(page);
    const next = page.locator(".board-overlay [aria-label='Next winner']");
    const forward = await next.isEnabled();
    const step = forward ? 1 : -1;
    await (forward ? next : page.locator(".board-overlay [aria-label='Previous winner']")).click();
    const moved = await waitForResultPage(page, before + step);
    report.expect(moved, `the winner pager did not move from page ${before} to ${before + step}`);
    const confirm = page.locator(".board-overlay .round-end-result__confirm");
    if ((await confirm.count()) === 0) {
        return;
    }
    const count = Number.parseInt(
        /\/\s*(?<count>\d+)/u.exec(
            (await page.locator(".board-overlay .round-end-result__page").textContent()) ?? "",
        )?.groups?.count ?? "",
        10,
    );
    for (let shown = await shownResultPage(page); shown < count; shown += 1) {
        await confirm.click();
        report.expect(
            await waitForResultPage(page, shown + 1),
            `the result's primary button did not turn page ${shown} on`,
        );
    }
    await confirm.click();
    const waits = await page
        .waitForSelector(".board-overlay .round-end-result__waiting", {
            timeout: SELECTOR_TIMEOUT_MS,
        })
        .then(() => true)
        .catch(() => false);
    report.expect(waits, "confirming the last page of the result did not leave the seat waiting");
}

/**
 * A standings row that is a button shows its round's result, and the focus goes back to the page's root (an ancestor
 * of the board), where the keys go on.
 */
async function checkStandingsRound(page: Page, report: PageReport): Promise<void> {
    const row = page.locator(".board-overlay .standings__round--jump").first();
    if ((await row.count()) === 0) {
        return;
    }
    await row.click();
    const shown = await page
        .waitForSelector(".board-overlay .round-end-result", { timeout: SELECTOR_TIMEOUT_MS })
        .then(() => true)
        .catch(() => false);
    report.expect(shown, "a standings row did not show its round's result");
    const focusAtRoot = await page.evaluate(() => {
        const board = document.querySelector(".game-board");
        const focused = document.activeElement;
        return board !== null && focused !== null && focused !== board && focused.contains(board);
    });
    report.expect(focusAtRoot, "after a standings row, the focus is not back on the page's root");
}

async function checkAfterShot(page: Page, report: PageReport): Promise<void> {
    await checkResultPaging(page, report);
    await checkStandingsRound(page, report);
}

function measureStandings(page: Page): Promise<StandingsMeasure | null> {
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
        const panel = document.querySelector(".board-overlay__panel:has(> .standings)");
        const sheet = panel?.querySelector(".standings__sheet");
        if (panel === null || panel === undefined || sheet === null || sheet === undefined) {
            return null;
        }
        const shown = sheet.getBoundingClientRect();
        const rounds = [...sheet.querySelectorAll(".standings__round--jump")].filter((row) => {
            const { bottom, top } = row.getBoundingClientRect();
            return top >= shown.top && bottom <= shown.bottom;
        });
        const totals = sheet.querySelector("tfoot");
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function toneOf(token: string, within: Element): string {
            const probe = document.createElement("span");
            probe.style.color = `var(${token})`;
            within.append(probe);
            const { color } = getComputedStyle(probe);
            probe.remove();
            return color;
        }
        const toneCells = [
            ["round +", "tbody .standings__cell--positive", "--ronin-score-positive"],
            ["round −", "tbody .standings__cell--negative", "--ronin-score-negative"],
            [
                "result +",
                ".standings__foot-row--result .standings__cell--positive",
                "--ronin-score-positive",
            ],
            [
                "result −",
                ".standings__foot-row--result .standings__cell--negative",
                "--ronin-score-negative",
            ],
        ] as const;
        const tones = toneCells.map(([cell, selector, token]) => {
            const found = sheet.querySelector(selector);
            return {
                cell,
                shown: found === null ? null : getComputedStyle(found).color,
                tone: toneOf(token, panel),
            };
        });
        const texts = [
            ...panel.querySelectorAll(
                ".standings th, .standings td, .standings__action, .standings__legend-item",
            ),
        ];
        return {
            controls: [...panel.querySelectorAll(".standings__action"), ...rounds].map(box),
            minFontPx: Math.min(
                ...texts.map((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
            ),
            panel: box(panel),
            sheet: box(sheet),
            sheetClient: { height: sheet.clientHeight, width: sheet.clientWidth },
            sheetOverflowY: getComputedStyle(sheet).overflowY,
            sheetScroll: { height: sheet.scrollHeight, width: sheet.scrollWidth },
            tones,
            totals: totals === null ? null : box(totals),
        };
    });
}

/**
 * The final standings fit their panel: the rounds scroll inside the sheet rather than past the board, and in landscape
 * never sideways (an upright page may scroll), the totals stay in view at the sheet's foot, no text is under the
 * floor, and on a supported landscape screen every control (its ways on, the rounds shown) is on the screen and large
 * enough to tap.
 */
function checkStandings(
    standings: StandingsMeasure | null,
    { screen, viewport }: { readonly screen: Box; readonly viewport: Viewport },
    report: PageReport,
): void {
    if (standings === null) {
        return;
    }
    const scrolls = standings.sheetScroll.height > standings.sheetClient.height + EPSILON;
    report.expect(
        !scrolls || standings.sheetOverflowY === "auto" || standings.sheetOverflowY === "scroll",
        "the standings' rounds overflow their sheet with no way to scroll to them",
    );
    report.expect(
        viewport.portrait || standings.sheetScroll.width <= standings.sheetClient.width + EPSILON,
        `the standings' sheet scrolls sideways: ${describeSize(standings.sheetScroll)} > ${describeSize(standings.sheetClient)}`,
    );
    report.expect(
        contains(standings.panel, standings.sheet),
        `the standings' sheet ${describeBox(standings.sheet)} leaves its panel`,
    );
    report.expect(
        standings.totals !== null && contains(standings.sheet, standings.totals),
        "the standings' totals are not in view at the sheet's foot",
    );
    const toned = standings.tones.filter(({ shown }) => shown !== null);
    const offTone = toned.filter(({ shown, tone }) => shown !== tone);
    report.expect(
        toned.length > 0 && offTone.length === 0,
        `standings cells not in their tone: ${offTone.map(({ cell, shown, tone }) => `${cell} ${shown} for ${tone}`).join(", ") || "none to check"}`,
    );
    report.expect(
        standings.minFontPx >= MIN_TEXT_PX,
        `standings text at ${standings.minFontPx}px, under ${MIN_TEXT_PX}px`,
    );
    if (!viewport.supported || viewport.portrait) {
        return;
    }
    const outside = standings.controls.filter(
        (control) => !contains(screen, control) || !contains(standings.panel, control),
    );
    report.expect(
        outside.length === 0,
        `${outside.length} standings control(s) off the panel or screen`,
    );
    const small = standings.controls.filter(
        (control) =>
            control.width < MIN_ACTION_SIZE - EPSILON || control.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `standings controls under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
}

/** The figures of a result's scores (each change and score) that wrap past one line, by their text. */
function measureWrappedFigures(page: Page): Promise<readonly string[]> {
    return page.evaluate(() =>
        [
            ...document.querySelectorAll(
                ".board-overlay .round-end-result__delta, .board-overlay .round-end-result__score-after",
            ),
        ]
            .filter((figure) => {
                const style = getComputedStyle(figure);
                const line =
                    Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.2;
                return figure.getBoundingClientRect().height > line * 1.5;
            })
            .map((figure) => figure.textContent ?? ""),
    );
}

/** Each name in a result's scores reads as one, standing clear of the next name on its line. */
function checkResultNames(names: readonly Box[], report: PageReport): void {
    const crowded = names.flatMap((name, index) => {
        const next = names[index + 1];
        const sameLine = next !== undefined && Math.abs(next.top - name.top) < name.height / 2;
        const gap = sameLine ? next.left - (name.left + name.width) : Infinity;
        return gap < MIN_RESULT_NAME_GAP ? [`${describeBox(name)} ${gap.toFixed(1)}px`] : [];
    });
    report.expect(
        crowded.length === 0,
        `result name(s) under ${MIN_RESULT_NAME_GAP}px from the next: ${crowded.join(", ")}`,
    );
}

async function checkRotatePanel(
    page: Page,
    countdown: boolean,
    report: PageReport,
): Promise<string> {
    const title = ".rotate-panel__title, .rotate-panel .failure-panel__title";
    const wayBack = [
        ".rotate-panel__leave:not([hidden])",
        ".rotate-panel .leave-confirm__leave",
        ".rotate-panel .failure-panel__leave",
    ].join(", ");
    await checkVisible(page, [title, wayBack], report);
    const seconds = page.locator(".rotate-panel__seconds");
    report.expect(
        (await seconds.count()) === (countdown ? 1 : 0),
        countdown ? "no countdown on the panel" : "a countdown on a panel with no decision",
    );
    return countdown ? `countdown ${await seconds.first().textContent()}` : "no countdown";
}

/**
 * The panels over the board: inside it and clear of the page's corner, a round result scrolling where it does not fit,
 * the standings, and on a landscape board the names of a result's scores apart.
 */
async function checkBoard({
    board,
    options,
    page,
    report,
    screen,
    viewport,
}: BoardRun): Promise<void> {
    checkOverlay(board, viewport, report);
    if (viewport.portrait && board.overlay !== null) {
        await checkUprightNotices(page, board.overlay.box, report);
    }
    if (viewport.supported) {
        checkResultPanel(
            await measureResultPanel(page),
            { desktop: viewport.desktop, mustScroll: options.panelScrolls === true },
            report,
        );
    }
    checkStandings(await measureStandings(page), { screen, viewport }, report);
    const wrapped = await measureWrappedFigures(page);
    report.expect(
        wrapped.length === 0,
        `result score figure(s) wrapped past one line: ${wrapped.join(", ")}`,
    );
    if (viewport.supported && !viewport.portrait) {
        checkResultNames(
            await measureBoxes(page, ".board-overlay .round-end-result__score-name"),
            report,
        );
    }
}

/** The panels: round results, the standings, the seating, the leave question, an end, and the rotate panel. */
export const panelsSurface: Surface = {
    checkAfterShot,
    checkBoard,
    pages: PAGES,
};
