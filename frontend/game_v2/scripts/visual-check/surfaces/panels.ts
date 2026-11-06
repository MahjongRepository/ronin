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

/** The seating panel over the board (before the first deal or at the game's end): its controls and smallest text. */
interface SeatingMeasure {
    readonly panel: Box;
    readonly controls: readonly Box[];
    readonly minFontPx: number;
    /** A positive and a negative result, where the game's end shows one: the colour each shows and its tone's. */
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

/** An upright board's result panel made as tall as its overlay allows. */
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

const SETTINGS = ".game__play .game-menu__panel";
const SETTINGS_TOGGLE = ".game__play .game-menu__toggle";

async function openSettings(page: Page): Promise<void> {
    await page.locator(SETTINGS_TOGGLE).click();
    await page.waitForSelector(SETTINGS, { timeout: SELECTOR_TIMEOUT_MS });
}

/**
 * The live game's settings, opened from the cog in the page's corner: the menu shows whole in the viewport, and
 * Escape closes it, giving the focus back to the cog. The board is checked before it opens, and the page is shot with
 * it opened again.
 */
async function checkSettings(
    { page, report }: PageRun,
    checkShownBoard: () => Promise<string>,
): Promise<string> {
    const summary = await checkShownBoard();
    await openSettings(page);
    const inView = await page.evaluate((panel) => {
        const shown = document.querySelector(panel)?.getBoundingClientRect();
        return (
            shown !== undefined &&
            shown.left >= 0 &&
            shown.top >= 0 &&
            shown.right <= window.innerWidth &&
            shown.bottom <= window.innerHeight
        );
    }, SETTINGS);
    report.expect(inView, "the settings menu leaves the viewport");
    await page.locator(".game__play .game-menu__sound").focus();
    await page.keyboard.press("Escape");
    const closed = await page
        .waitForFunction((panel) => document.querySelector(panel) === null, SETTINGS, {
            timeout: SELECTOR_TIMEOUT_MS,
        })
        .then(() => true)
        .catch(() => false);
    report.expect(closed, "Escape did not close the settings menu");
    report.expect(
        await page.evaluate(
            (toggle) => document.activeElement?.matches(toggle) === true,
            SETTINGS_TOGGLE,
        ),
        "closing the settings did not give the focus back to the cog",
    );
    await openSettings(page);
    return summary;
}

/**
 * The panels' worst cases: the densest results (pao, a double ron's pager, a hand with its melds) and the game end
 * at the desktops and the notch phone too, a double ron's first page at the small windows, and every other panel
 * once, at the floor or, for the rotate panel, upright. A panel a kept one shows in a harsher form is left out (the
 * round end's reconnected copy, a head bump, an all-noten draw, the last result and its reopened copy, a kick, the
 * leave question after a win, the rotate panel waiting or counting down).
 */
const PAGES: readonly PageCase[] = [
    {
        at: [FLOOR, MID_DESKTOP],
        check: checkSettings,
        checkpoint: "turn",
        kind: "own",
        name: "game-settings",
        path: `/play/${GAME_ID}`,
        required: { visible: [SETTINGS_TOGGLE, ".game__play .hand-tile"] },
    },
    resultCase("yakuman", "", [".round-end-result__limit"]),
    resultCase("triple_ron", "", [".round-end-result__from"]),
    boardCase("board-game-end-stick-lost", "?overlay=game_end&leftover=lost", [".seating__note"]),
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
    }),
    resultStory("kazoe", { ".round-end-result__limit": "Yakuman" }),
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
        [".round-end-result__river .tile", ".round-end-result__tenpai .tile"],
    ),
    resultStory("kyuushu", {
        ".round-end-result__from": "declared by Alice",
        ".round-end-result__title": "Kyuushu Kyuuhai",
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
        ...boardCase("board-game-end", "?overlay=game_end", [
            ".seating__ending--length",
            ".seating__note",
            ".seating__result--positive",
            ".seating__seat--viewer",
        ]),
        at: [...WORST_CASES, NOTCH_PHONE, SHORTEST_REGULAR_DESKTOP, ...SMALL_WINDOWS],
    },
    {
        kind: "board",
        name: "decisions-game-start",
        path: "/play/storybook/decisions?state=game_start",
        required: {
            visible: [
                ".seating__seat--viewer",
                ".seating__score",
                ".seating__countdown",
                ".nameplate",
            ],
        },
    },
    {
        kind: "board",
        name: "decisions-game-start-waiting",
        path: "/play/storybook/decisions?state=game_start_waiting",
        required: {
            visible: [".seating__seat--viewer", ".seating__confirm:disabled", ".nameplate"],
        },
    },
    {
        kind: "board",
        name: "decisions-game-resume",
        path: "/play/storybook/decisions?state=game_resume",
        required: {
            visible: [
                ".seating__seat--viewer",
                ".seating__score",
                ".seating__countdown",
                ".nameplate",
            ],
        },
    },
    {
        ...decisionCase("round_end", [".round-end-result__confirm"]),
        at: [UPRIGHT_PHONE],
        name: "decisions-round-end-tall",
        prepare: forceResultPanelTall,
    },
    decisionCase("round_end", [".round-end-result__confirm", ".round-end-result__countdown"]),
    {
        ...decisionCase("double_ron_first", [
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
    decisionCase("game_end", [
        ".seating__ending--tobi",
        ".seating__result--positive",
        ".seating__actions a[href*='seat=1']",
    ]),
    {
        ...decisionCase("out_of_step_result", [
            ".round-end-result__uncertain",
            ".round-end-result__confirm",
            ".round-end-result__indicator-tiles .tile",
        ]),
        at: [FLOOR, SMALLEST_WINDOW],
    },
    decisionCase("out_of_step_game_end", [".seating__ending", ".seating__actions"]),
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
                "The round's result awaits your OK. Its timer keeps running while this message is shown.",
            ".rotate-panel__seconds": "8",
        },
    }),
    rotateCase("untimed", {
        content: ".rotate-panel__decision",
        countdown: false,
        texts: {
            ".rotate-panel__decision p":
                "It is your turn. Play continues, and your timer keeps running while this message is shown.",
        },
    }),
];

function checkOverlay(board: BoardMeasure, viewport: Viewport, report: PageReport): void {
    const { overlay } = board;
    if (overlay === null) {
        return;
    }
    report.expect(contains(board.board, overlay.box), "the overlay panel leaves the board");
    if (viewport.supported) {
        report.expect(
            overlay.scroll.width <= overlay.client.width + EPSILON &&
                overlay.scroll.height <= overlay.client.height + EPSILON,
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

/** What a round result's panel shows. */
interface ResultPanelView {
    /** The panel's visible area, inside its border. */
    readonly shown: Box;
    /** The primary button and its countdown, which stay in view. */
    readonly kept: readonly { readonly name: string; readonly box: Box }[];
    readonly pager: readonly Box[];
    /** The winner's hand row, or a draw's tenpai hands and a nagashi's river: what the result is about, never cut. */
    readonly hands: readonly { readonly box: Box; readonly cut: boolean }[];
    /** The result's other parts (its yaku, value, scores and controls), which a hand row never lies under. */
    readonly parts: readonly Box[];
}

/** A part of the result that scrolls in place: how much it holds against what it shows. */
interface ResultScroller {
    readonly name: string;
    readonly scroll: number;
    readonly client: number;
}

/** A round result's panel as it stands: what it holds against what it shows, and what it shows. */
interface ResultPanelMeasure {
    readonly scroll: Size;
    readonly client: Size;
    readonly scrollers: readonly ResultScroller[];
    readonly view: ResultPanelView;
}

function measureResultPanel(page: Page): Promise<ResultPanelMeasure | null> {
    return page.evaluate(() => {
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
            const hands = [
                ...shownPanel.querySelectorAll(
                    ".round-end-result > :is(.round-end-result__hand, .round-end-result__rivers), .round-end-result__tenpai-hand",
                ),
            ];
            return {
                hands: hands.map((hand) => ({
                    box: box(hand),
                    cut: hand.scrollHeight > hand.clientHeight + 1,
                })),
                kept: [
                    ...shownPanel.querySelectorAll(
                        ".round-end-result__confirm, .round-end-result__countdown",
                    ),
                ].map((element) => ({ box: box(element), name: element.className.split(" ")[0] })),
                pager: [...shownPanel.querySelectorAll(".round-end-result__page-btn")].map(box),
                parts: [
                    ...shownPanel.querySelectorAll(
                        ".round-end-result > :is(.round-end-result__yaku, .round-end-result__value, .round-end-result__foot, .round-end-result__controls)",
                    ),
                ].map(box),
                shown: {
                    height: shownPanel.clientHeight,
                    left: outer.left + shownPanel.clientLeft,
                    top: outer.top + shownPanel.clientTop,
                    width: shownPanel.clientWidth,
                },
            };
        }
        const scrollers = [...panel.querySelectorAll(".round-end-result > *")]
            .filter((part) => part.scrollHeight > part.clientHeight + 1)
            .map((part) => ({
                client: part.clientHeight,
                name: part.className.split(" ")[0] ?? "",
                scroll: part.scrollHeight,
            }));
        return {
            client: { height: panel.clientHeight, width: panel.clientWidth },
            scroll: { height: panel.scrollHeight, width: panel.scrollWidth },
            scrollers,
            view: view(panel),
        };
    });
}

/**
 * A round result fits its panel whole at every supported size, none of its parts scrolling in place, its head's pager
 * and its primary button and countdown in view; the hand row (a draw's tenpai hands, a nagashi's river) lies whole in
 * view under no other part.
 */
function checkResultPanel(panel: ResultPanelMeasure | null, report: PageReport): void {
    if (panel === null) {
        return;
    }
    const panelOverflows = panel.scroll.height > panel.client.height + EPSILON;
    const { scrollers } = panel;
    const held = `${describeSize(panel.scroll)} in ${describeSize(panel.client)}${scrollers.map(({ client, name, scroll }) => `, ${name} ${scroll}px in ${client}px`).join("")}`;
    report.expect(
        !panelOverflows && scrollers.length === 0,
        `a result does not fit its panel: ${held}`,
    );
    const { view } = panel;
    const hidden = view.kept.filter(({ box }) => !contains(view.shown, box));
    report.expect(
        hidden.length === 0,
        `the result's ${hidden.map(({ name }) => name).join(", ")} leave(s) its panel's view`,
    );
    const hiddenPager = view.pager.filter((button) => !contains(view.shown, button));
    report.expect(
        hiddenPager.length === 0,
        `the winner pager leaves the result panel's view: ${hiddenPager.map(describeBox).join(", ")}`,
    );
    const clipped = view.hands.filter(
        ({ box, cut }) =>
            cut || !contains(view.shown, box) || view.parts.some((part) => intersects(part, box)),
    );
    report.expect(
        clipped.length === 0,
        `the result's hand row is clipped: ${clipped.map(({ box }) => describeBox(box)).join(", ")}`,
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

async function checkAfterShot(page: Page, report: PageReport): Promise<void> {
    await checkResultPaging(page, report);
}

function measureSeating(page: Page): Promise<SeatingMeasure | null> {
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
        const panel = document.querySelector(".board-overlay__panel:has(> .seating)");
        if (panel === null) {
            return null;
        }
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
            ["result +", ".seating__result--positive", "--ronin-score-positive"],
            ["result −", ".seating__result--negative", "--ronin-score-negative"],
        ] as const;
        const tones = toneCells.map(([cell, selector, token]) => {
            const found = panel.querySelector(selector);
            return {
                cell,
                shown: found === null ? null : getComputedStyle(found).color,
                tone: toneOf(token, panel),
            };
        });
        const texts = [
            ...panel.querySelectorAll(
                ".seating__seat > *, .seating__action, .seating__ending, .seating__note, .seating__countdown",
            ),
        ];
        return {
            controls: [...panel.querySelectorAll(".seating__action")].map(box),
            minFontPx: Math.min(
                ...texts.map((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
            ),
            panel: box(panel),
            tones,
        };
    });
}

/**
 * The seating panel reads: no text is under the floor, a game end's results show in their tones, and on a supported
 * landscape screen every way on is on the screen, inside the panel and large enough to tap.
 */
function checkSeating(
    seating: SeatingMeasure | null,
    { screen, viewport }: { readonly screen: Box; readonly viewport: Viewport },
    report: PageReport,
): void {
    if (seating === null) {
        return;
    }
    const offTone = seating.tones.filter(({ shown, tone }) => shown !== null && shown !== tone);
    report.expect(
        offTone.length === 0,
        `seating results not in their tone: ${offTone.map(({ cell, shown, tone }) => `${cell} ${shown} for ${tone}`).join(", ")}`,
    );
    report.expect(
        seating.minFontPx >= MIN_TEXT_PX,
        `seating text at ${seating.minFontPx}px, under ${MIN_TEXT_PX}px`,
    );
    if (!viewport.supported || viewport.portrait) {
        return;
    }
    const outside = seating.controls.filter(
        (control) => !contains(screen, control) || !contains(seating.panel, control),
    );
    report.expect(
        outside.length === 0,
        `${outside.length} seating control(s) off the panel or screen`,
    );
    const small = seating.controls.filter(
        (control) =>
            control.width < MIN_ACTION_SIZE - EPSILON || control.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `seating controls under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
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
 * The panels over the board: inside it (over the cog), a round result fitting it whole,
 * the seating, and on a landscape board the names of a result's scores apart.
 */
async function checkBoard({ board, page, report, screen, viewport }: BoardRun): Promise<void> {
    checkOverlay(board, viewport, report);
    if (viewport.portrait && board.overlay !== null) {
        await checkUprightNotices(page, board.overlay.box, report);
    }
    if (viewport.supported) {
        checkResultPanel(await measureResultPanel(page), report);
    }
    checkSeating(await measureSeating(page), { screen, viewport }, report);
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

/** The panels: round results, the seating (and the game's end on it), the leave question, an end, and the rotate panel. */
export const panelsSurface: Surface = {
    checkAfterShot,
    checkBoard,
    pages: PAGES,
};
