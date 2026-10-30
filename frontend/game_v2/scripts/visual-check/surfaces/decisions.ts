import { type Page } from "playwright";

import { type BoardMeasure } from "../board-measure.ts";
import {
    type Box,
    EPSILON,
    MIN_ACTION_SIZE,
    contains,
    describeBox,
    grown,
    intersects,
    sameBox,
} from "../boxes.ts";
import { ACTION, BOARD_VISIBLE, decisionCase } from "../cases.ts";
import {
    type BoardRun,
    GAME_ID,
    type LiveCheckpoint,
    type PageCase,
    PageRecord,
    type PageReport,
    type PageRun,
    SELECTOR_TIMEOUT_MS,
    type Surface,
    type TaskResult,
} from "../model.ts";
import { checkVisible } from "../page-checks.ts";
import {
    LAPTOPS,
    LARGE_DESKTOP,
    NARROW_DESKTOP,
    SHORT_DESKTOP,
    VIEWPORTS,
    WIDER_PHONES,
} from "../viewports.ts";

/** The least room between a decision control and any tile outside the controls, so a tap meant for one never lands on the other. */
const MIN_CONTROL_TILE_GAP = 4;
/**
 * A decision story and the stories of the same decision answered and expired, whose controls and timer must stand
 * where the open one's stand: answering or running out never moves them.
 */
const CONTROL_FAMILIES: readonly string[] = ["decisions-anchor-call"];
/**
 * Pages showing a toggle off and then pressed (riichi in the band; a call's first step, then its choice of tiles, in
 * the column), whose toggle must stand in one place on a phone: pressing it never moves it.
 */
const TOGGLE_FAMILIES: readonly (readonly [string, string])[] = [
    ["decisions-anchor-riichi-off", "decisions-anchor-riichi"],
    ["decisions-kan-offer", "decisions-kan-choice"],
    ["decisions-call-prompt", "decisions-chi-choice"],
];

/** A toggle with a lamp (the riichi toggle): the state it announces and whether its lamp shows the check. */
interface LampMeasure {
    readonly pressed: boolean;
    readonly checked: boolean;
}

/** The decision controls' boxes and then the timer's, where a page showed a decision in landscape. */
const CONTROL_PLACES = new PageRecord<readonly Box[]>();
/** The decision's first toggle's box, or null without one, where a page measured a board in landscape. */
const TOGGLE_PLACES = new PageRecord<Box | null>();

async function switchChecked(page: Page, name: string): Promise<boolean> {
    return (await page.getByRole("switch", { name }).getAttribute("aria-checked")) === "true";
}

/**
 * The play switches by keyboard: Shift+Tab from the hand's first tile reaches one within a few presses (no focus moved
 * for the player), and Space and Enter on the focused Auto win each turn it once, sending nothing; it ends on, as the
 * story opened.
 */
async function checkSwitchKeys(page: Page): Promise<void> {
    await page.waitForSelector(".play-switch", { timeout: SELECTOR_TIMEOUT_MS });
    await page.locator(".board-local .hand-tile").first().focus();
    let reached = false;
    for (let press = 0; press < 4 && !reached; press += 1) {
        await page.keyboard.press("Shift+Tab");
        reached = await page.evaluate(
            () => document.activeElement?.classList.contains("play-switch") ?? false,
        );
    }
    if (!reached) {
        throw new Error("Shift+Tab from the hand never reached a play switch");
    }
    const autoWin = page.getByRole("switch", { name: "Auto win" });
    for (const [key, expected] of [
        [" ", false],
        ["Enter", true],
    ] as const) {
        await autoWin.press(key);
        if ((await switchChecked(page, "Auto win")) !== expected) {
            throw new Error(`${key === " " ? "Space" : key} on Auto win did not turn it once`);
        }
    }
    if ((await page.locator(".decisions-storybook__sent").count()) > 0) {
        throw new Error("turning a play switch sent a message");
    }
    await autoWin.blur();
}

/** The live game at a checkpoint of the seat transcript, on its own route, its socket mocked. */
function gameCase(checkpoint: LiveCheckpoint, shown: string): PageCase {
    return {
        check: checkGame,
        checkpoint,
        kind: "own",
        name: `game-${checkpoint}`,
        path: `/play/${GAME_ID}`,
        required: {
            attached: [
                ".game__rotate .rotate-panel__seconds",
                shown,
                ".game__play .decision-controls__countdown",
            ],
            visible: [],
        },
    };
}

const PAGES: readonly PageCase[] = [
    {
        ...decisionCase("anchor_turn", [".hand-tile--selectable", ".decision-controls__countdown"]),
        alsoAt: [SHORT_DESKTOP, NARROW_DESKTOP, ...LAPTOPS, ...WIDER_PHONES],
        contrast: true,
    },
    {
        ...decisionCase("anchor_call", [ACTION, ".decision-controls__countdown"]),
        alsoAt: [SHORT_DESKTOP, NARROW_DESKTOP, ...LAPTOPS, LARGE_DESKTOP, ...WIDER_PHONES],
        contrast: true,
    },
    {
        ...decisionCase("anchor_riichi", [
            `${ACTION}[aria-pressed="true"]`,
            ".hand-tile--disabled",
        ]),
        alsoAt: [SHORT_DESKTOP, NARROW_DESKTOP, ...LAPTOPS, ...WIDER_PHONES],
        contrast: true,
    },
    { ...decisionCase("anchor_riichi_off", [`${ACTION}[aria-pressed="false"]`]), contrast: true },
    decisionCase("anchor_call_sent", [`${ACTION}--chosen`, ".decision-timer--sent"]),
    decisionCase("anchor_call_expired", [ACTION, ".decision-timer--time-up"]),
    {
        ...decisionCase("call_prompt", [ACTION, ".decision-controls__countdown"]),
        alsoAt: [NARROW_DESKTOP],
    },
    {
        ...decisionCase("chi_choice", [`${ACTION}--choice .meld-tile-sideways`, `${ACTION}--pass`]),
        alsoAt: [NARROW_DESKTOP, LARGE_DESKTOP],
    },
    decisionCase("kan_offer", [`${ACTION}[aria-pressed="false"]`, ".decision-controls__countdown"]),
    {
        ...decisionCase("kan_choice", [`${ACTION}--choice .tile-back`, `${ACTION}--pass`]),
        alsoAt: [NARROW_DESKTOP, LARGE_DESKTOP],
    },
    decisionCase("ron_prompt", [ACTION, ".decision-controls__countdown"]),
    decisionCase("chankan_prompt", [ACTION, ".board-strip .meld--source"]),
    decisionCase("kuikae_turn", [".hand-tile--disabled", ".hand-tile--selectable"]),
    decisionCase("riichi_pick", [`${ACTION}[aria-pressed="true"]`, ".hand-tile--disabled"]),
    decisionCase("riichi_turn", [
        ACTION,
        ".board-furiten__word",
        ".hand-tile--selectable",
        ".decision-controls__bank",
    ]),
    {
        ...decisionCase("switches_furiten", [
            ".play-switch--on .play-switch__knob",
            ".board-furiten__word",
        ]),
        alsoAt: WIDER_PHONES,
        contrast: true,
        onlyAt: [
            "desktop",
            "desktop-1440",
            "desktop-wide",
            "phone-notch-landscape",
            "phone-se-landscape",
            "phone-680",
            "phone-700",
        ],
        prepare: checkSwitchKeys,
    },
    decisionCase("turn_in_bank", [".decision-controls__bank--draining", ".decision-timer--bank"]),
    decisionCase("answered", [".hand-tile--selected"]),
    gameCase("prompt", ".game__play .decision-controls__action"),
    {
        ...gameCase("turn", ".game__play .board-local .hand-tile--selectable"),
        alsoAt: [SHORT_DESKTOP, ...LAPTOPS, ...WIDER_PHONES],
    },
];

function measureLamps(page: Page): Promise<readonly LampMeasure[]> {
    return page.evaluate(() => {
        const board = document.querySelector(".game-board");
        return [...(board?.querySelectorAll(".decision-controls__lamp") ?? [])].map((lamp) => {
            const check = getComputedStyle(lamp, "::after");
            return {
                checked:
                    check.content !== "none" &&
                    check.display !== "none" &&
                    Number.parseFloat(check.width) > 0 &&
                    Number.parseFloat(check.height) > 0,
                pressed: lamp.closest("[aria-pressed]")?.getAttribute("aria-pressed") === "true",
            };
        });
    });
}

/**
 * Decision buttons and a round result's confirm sit wholly on the board and the screen, large enough to tap, and every
 * decision button wholly inside its corner, never scrolled or clipped out of it.
 */
function checkActions(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { decisionCorner } = board;
    if (decisionCorner !== null) {
        const cut = decisionCorner.buttons.filter(
            (button) => !contains(decisionCorner.box, button),
        );
        report.expect(
            cut.length === 0,
            `decision button(s) outside their corner ${describeBox(decisionCorner.box)}: ${cut.map(describeBox).join(", ")}`,
        );
    }
    const outside = [...board.actions, ...(board.timer ? [board.timer] : [])].filter(
        (action) => !contains(board.board, action) || !contains(screen, action),
    );
    report.expect(
        outside.length === 0,
        `${outside.length} decision button(s) or the timer off the board or screen`,
    );
    const small = board.actions.filter(
        (action) =>
            action.width < MIN_ACTION_SIZE - EPSILON || action.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `decision buttons under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
    const buttons = decisionCorner?.buttons ?? [];
    const overlapping = buttons.filter((button, index) =>
        buttons.some((other, otherIndex) => otherIndex !== index && intersects(button, other)),
    );
    report.expect(
        overlapping.length === 0,
        `decision buttons over each other: ${overlapping.map(describeBox).join(", ")}`,
    );
    const { timer } = board;
    const overTimer = timer === null ? [] : buttons.filter((button) => intersects(button, timer));
    report.expect(
        overTimer.length === 0,
        `decision button(s) over the timer: ${overTimer.map(describeBox).join(", ")}`,
    );
    const tiles = [...board.otherTiles, ...board.localTiles];
    const crowded = (decisionCorner?.buttons ?? []).filter((button) =>
        tiles.some((tile) => intersects(grown(button, MIN_CONTROL_TILE_GAP), tile)),
    );
    report.expect(
        crowded.length === 0,
        `decision button(s) within ${MIN_CONTROL_TILE_GAP}px of a tile: ${crowded.map(describeBox).join(", ")}`,
    );
}

/**
 * The play switches sit wholly on the board and the screen, each large enough to tap, clear of every tile by the gap
 * a decision control keeps and off every decision control and the timer, and each shows the state it announces apart
 * from colour (its knob's side) and by its fill.
 */
function checkSwitches(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { switches } = board;
    if (switches.length === 0) {
        return;
    }
    const boxes = switches.map((control) => control.box);
    const outside = boxes.filter((box) => !contains(board.board, box) || !contains(screen, box));
    report.expect(
        outside.length === 0,
        `${outside.length} play switch(es) off the board or screen`,
    );
    const small = boxes.filter(
        (box) => box.width < MIN_ACTION_SIZE - EPSILON || box.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `play switches under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
    const tiles = [...board.otherTiles, ...board.localTiles];
    const controls = [...board.actions, ...(board.timer ? [board.timer] : [])];
    const crowded = boxes.filter(
        (box) =>
            tiles.some((tile) => intersects(grown(box, MIN_CONTROL_TILE_GAP), tile)) ||
            controls.some((control) => intersects(box, control)),
    );
    report.expect(
        crowded.length === 0,
        `play switch(es) within ${MIN_CONTROL_TILE_GAP}px of a tile or over a decision control: ${crowded.map(describeBox).join(", ")}`,
    );
    const misread = switches.filter(
        (control) => control.knobRight !== control.checked || control.filled !== control.checked,
    );
    report.expect(
        misread.length === 0,
        `play switch(es) whose knob or fill does not show their state: ${misread.map((control) => describeBox(control.box)).join(", ")}`,
    );
}

/** A toggle's lamp shows its check exactly while the toggle is pressed, so its state never reads by colour alone. */
function checkLamps(lamps: readonly LampMeasure[], report: PageReport): void {
    const misread = lamps.filter((lamp) => lamp.checked !== lamp.pressed);
    report.expect(
        misread.length === 0,
        `${misread.length} toggle lamp(s) whose check does not match the toggle's state`,
    );
}

async function isShown(page: Page, selector: string): Promise<boolean> {
    return page.locator(selector).first().isVisible();
}

async function checkGame(run: PageRun, checkLiveBoard: () => Promise<string>): Promise<string> {
    const { measure, page, report, viewport } = run;
    const seconds = Number(
        await page.locator(".game__rotate .rotate-panel__seconds").textContent(),
    );
    report.expect(seconds > 0, `the open decision's countdown reads ${seconds}`);
    const { rotates } = viewport;
    report.expect(
        (await isShown(page, ".game__rotate")) === rotates,
        rotates ? "the rotate panel is hidden on an upright phone" : "the rotate panel shows",
    );
    report.expect(
        (await isShown(page, ".game__play")) === !rotates,
        rotates ? "the table shows on an upright phone" : "the table is hidden",
    );
    if (!rotates) {
        await checkVisible(
            page,
            [...BOARD_VISIBLE, ".game__play .decision-controls__countdown"],
            report,
        );
        return `countdown ${seconds}, ${await checkLiveBoard()}`;
    }
    await checkVisible(
        page,
        [".game__rotate .rotate-panel__seconds", ".game__rotate .rotate-panel__leave"],
        report,
    );
    const panel = await page.evaluate(() => {
        const element = document.querySelector(".game__rotate");
        if (element === null) {
            return null;
        }
        const { height, left, top, width } = element.getBoundingClientRect();
        return {
            clientHeight: element.clientHeight,
            rect: { height, left, top, width },
            scrollHeight: element.scrollHeight,
        };
    });
    report.expect(panel !== null, "no .game__rotate");
    if (panel !== null) {
        const screen = { height: measure.innerHeight, left: 0, top: 0, width: measure.innerWidth };
        report.expect(
            contains(panel.rect, screen) && contains(screen, panel.rect),
            `the rotate panel ${describeBox(panel.rect)} does not cover the viewport`,
        );
        report.expect(
            panel.scrollHeight <= panel.clientHeight + EPSILON,
            "the rotate panel's content needs scrolling",
        );
    }
    return `countdown ${seconds}, rotate panel shown`;
}

/**
 * A decision's controls and timer stand where they stood while it was open once it is answered or has run out
 * (`CONTROL_FAMILIES`), at each viewport.
 */
function checkControlPlaces(results: readonly TaskResult[]): string[] {
    return CONTROL_FAMILIES.flatMap((family) => {
        const members = results.flatMap(({ page, report, viewport }) => {
            const places = CONTROL_PLACES.read(report);
            return (page === family || page.startsWith(`${family}-`)) && places !== undefined
                ? [{ page, places, viewport }]
                : [];
        });
        return members.flatMap(({ page, places, viewport }) => {
            const open = members.find(
                (member) => member.page === family && member.viewport === viewport,
            );
            const expected = open?.places;
            if (page === family || expected === undefined) {
                return [];
            }
            const moved =
                places.length !== expected.length ||
                places.some(
                    (place, index) =>
                        Math.abs(place.left - expected[index].left) > EPSILON ||
                        Math.abs(place.top - expected[index].top) > EPSILON ||
                        Math.abs(place.width - expected[index].width) > EPSILON ||
                        Math.abs(place.height - expected[index].height) > EPSILON,
                );
            return moved
                ? [
                      `${viewport}: ${page}'s controls or timer stand apart from ${family}'s: ${places.map(describeBox).join(", ")}`,
                  ]
                : [];
        });
    });
}

/** The landscape phones, whose column and band the toggle pin is about; an upright board lays its controls in rows. */
const LANDSCAPE_PHONES: ReadonlySet<string> = new Set(
    VIEWPORTS.filter((viewport) => !viewport.desktop && !viewport.portrait).map(({ name }) => name),
);

/** A landscape phone's toggle stands where it stood before it was pressed (`TOGGLE_FAMILIES`). */
function checkTogglePlaces(results: readonly TaskResult[]): string[] {
    return TOGGLE_FAMILIES.flatMap(([off, on]) =>
        results
            .filter(({ page, viewport }) => page === on && LANDSCAPE_PHONES.has(viewport))
            .flatMap(({ report, viewport }) => {
                const before = results.find(
                    (result) => result.page === off && result.viewport === viewport,
                );
                const [was, is] = [
                    before === undefined ? undefined : TOGGLE_PLACES.read(before.report),
                    TOGGLE_PLACES.read(report) ?? null,
                ];
                if (was === undefined || was === null || is === null) {
                    return before === undefined
                        ? []
                        : [`${viewport}: ${on} or ${off} shows no toggle`];
                }
                return sameBox(was, is)
                    ? []
                    : [
                          `${viewport}: the toggle moves when pressed, ${describeBox(was)} on ${off}, ${describeBox(is)} on ${on}`,
                      ];
            }),
    );
}

/**
 * A decision's controls on a landscape board: its buttons and timer on the board and the screen and clear of the tiles,
 * the play switches, the toggles' lamps, and where the controls and the toggle stand, for the checks across pages.
 */
async function checkBoard({ board, page, report, screen, viewport }: BoardRun): Promise<void> {
    if (!viewport.supported || viewport.portrait) {
        return;
    }
    TOGGLE_PLACES.keep(report, board.toggle);
    if (board.timer !== null) {
        CONTROL_PLACES.keep(report, [...(board.decisionCorner?.buttons ?? []), board.timer]);
    }
    checkActions(board, screen, report);
    checkSwitches(board, screen, report);
    checkLamps(await measureLamps(page), report);
}

function checkResults(results: readonly TaskResult[]): readonly string[] {
    return [...checkControlPlaces(results), ...checkTogglePlaces(results)];
}

/** The live board's decisions: the stories at each checkpoint of the generated seat transcripts, and the live route. */
export const decisionsSurface: Surface = {
    checkBoard,
    checkResults,
    pages: PAGES,
};
