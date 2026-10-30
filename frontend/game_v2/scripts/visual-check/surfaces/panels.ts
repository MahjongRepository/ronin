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
import { boardCase, decisionCase } from "../cases.ts";
import {
    type BoardRun,
    type PageCase,
    type PageReport,
    SELECTOR_TIMEOUT_MS,
    type Surface,
    type Viewport,
} from "../model.ts";
import { checkVisible } from "../page-checks.ts";
import { MIN_TEXT_PX } from "../text.ts";

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
function resultCase(result: string, query: string, extra: readonly string[]): PageCase {
    return boardCase(
        `board-result-${result.replaceAll("_", "-")}`,
        `?overlay=round_end&result=${result}${query}`,
        [".board-overlay__panel", ...extra],
    );
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

/** A rotate panel story: the panel an upright phone shows in place of the live board. */
function rotateCase(state: string, countdown: boolean, content: string): PageCase {
    return {
        check: ({ page, report }) => checkRotatePanel(page, countdown, report),
        kind: "own",
        name: `rotate-${state}`,
        path: `/play/storybook/rotate?state=${state}`,
        required: { visible: [".rotate-panel", content] },
    };
}

const PAGES: readonly PageCase[] = [
    resultCase("double_ron", "&page=1", [".round-end-result__pager"]),
    { ...resultCase("sanbaiman", "", [".round-end-result__hand .meld"]), contrast: true },
    resultCase("pao", "", [".round-end-result__notes"]),
    resultCase("exhaustive", "", [".round-end-result__tenpai .tile"]),
    boardCase("board-standings", "?overlay=game_end", [
        ".standings__foot-row--leftover",
        ".standings__cell .standings__riichi",
        ".standings__cell .standings__mark--deal-in",
        ".standings__legend",
    ]),
    {
        kind: "board",
        name: "decisions-game-start",
        path: "/play/storybook/decisions?state=game_start",
        required: { visible: [".game-start__seat--viewer", ".game-start__status", ".nameplate"] },
    },
    decisionCase("round_end", [".round-end-result__confirm", ".round-end-result__countdown"]),
    scrollingResultCase("round_end", [
        ".round-end-result__confirm",
        ".round-end-result__countdown",
    ]),
    decisionCase("double_ron_first", [".round-end-result__pager", ".round-end-result__confirm"]),
    scrollingResultCase("double_ron_first", [
        ".round-end-result__pager",
        ".round-end-result__confirm",
        ".round-end-result__countdown",
    ]),
    decisionCase("waiting", [".round-end-result__waiting"]),
    decisionCase("reconnect_owed", [".round-end-result__confirm", ".round-end-result__countdown"]),
    decisionCase("last_result", [".round-end-result__confirm"]),
    decisionCase("standings", [
        ".standings__cell--win",
        ".standings__foot-row--result",
        ".standings__actions a[href*='seat=1']",
    ]),
    decisionCase("last_result_reopened", [".round-end-result__confirm"]),
    decisionCase("kicked", [".failure-panel__leave", ".game-menu__status:not(.status-connected)"]),
    decisionCase("leave_confirm", [".leave-confirm__leave", ".leave-confirm__stay"]),
    decisionCase("leave_after_win", [".leave-confirm__stay"]),
    rotateCase("waiting", false, ".rotate-panel .connection-status"),
    rotateCase("leave", false, ".rotate-panel .leave-confirm__leave"),
    rotateCase("ended", false, ".rotate-panel .failure-panel__reload"),
    rotateCase("countdown", true, ".rotate-panel__seconds"),
];

function checkOverlay(board: BoardMeasure, viewport: Viewport, report: PageReport): void {
    const { overlay } = board;
    if (overlay === null) {
        return;
    }
    report.expect(contains(board.board, overlay.box), "the overlay panel leaves the board");
    const covered = viewport.portrait
        ? []
        : board.menu.filter((control) => intersects(control, overlay.box));
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
 * A case that forces the panel short first proves that it overflows.
 */
function checkResultPanel(
    panel: ResultPanelMeasure | null,
    mustScroll: boolean,
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

/** The winner pager of a double ron's result moves one page: on, or back from the last page. */
async function checkWinnerPaging(page: Page, report: PageReport): Promise<void> {
    if ((await page.locator(".board-overlay .round-end-result__page-btn").count()) === 0) {
        return;
    }
    const label = page.locator(".board-overlay .round-end-result__page");
    const before = Number.parseInt((await label.textContent()) ?? "", 10);
    const next = page.locator(".board-overlay [aria-label='Next winner']");
    const forward = await next.isEnabled();
    const step = forward ? 1 : -1;
    await (forward ? next : page.locator(".board-overlay [aria-label='Previous winner']")).click();
    const moved = await page
        .waitForFunction(
            (expected) =>
                Number.parseInt(
                    document.querySelector(".board-overlay .round-end-result__page")?.textContent ??
                        "",
                    10,
                ) === expected,
            before + step,
            { timeout: SELECTOR_TIMEOUT_MS },
        )
        .then(() => true)
        .catch(() => false);
    report.expect(moved, `the winner pager did not move from page ${before} to ${before + step}`);
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
    if (viewport.supported) {
        checkResultPanel(await measureResultPanel(page), options.panelScrolls === true, report);
    }
    checkStandings(await measureStandings(page), { screen, viewport }, report);
    if (viewport.supported && !viewport.portrait) {
        checkResultNames(
            await measureBoxes(page, ".board-overlay .round-end-result__score-name"),
            report,
        );
    }
}

/** The panels: round results, the standings, the seating, the leave question, an end, and the rotate panel. */
export const panelsSurface: Surface = {
    checkAfterShot: checkWinnerPaging,
    checkBoard,
    pages: PAGES,
};
