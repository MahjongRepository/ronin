import { type Page } from "playwright";

import { RIVER_ROW_SIZE } from "../../../src/entities/tile/lib/river-shape.ts";
import { type BoardMeasure, ownRiverThirdRow } from "../board-measure.ts";
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
    longSide,
    near,
    sameBox,
} from "../boxes.ts";
import { ACTION, boardCase, documentCase } from "../cases.ts";
import {
    type BoardRun,
    type PageCase,
    type PageMeasure,
    PageRecord,
    type PageReport,
    type Surface,
    type TaskResult,
    type Viewport,
} from "../model.ts";
import { MIN_TEXT_PX } from "../text.ts";
import {
    FLOOR,
    FULLSCREEN_PHONE,
    LAPTOPS,
    MID_DESKTOP,
    NARROW_DESKTOP,
    NOTCH_PHONE,
    SHORT_DESKTOP,
    ULTRAWIDE,
    UPRIGHT_PHONE,
    WIDER_PHONES,
    WORST_CASES,
} from "../viewports.ts";
import { checkSeparatedHandDepth } from "./hand-depth.ts";

/**
 * The smallest face-up tile on the table in landscape, in CSS pixels, readable at a glance: a river's, another seat's
 * hand's or melds'. The geometry's own floor is lower (a 2px river tile), which is how a phone's browser box shipped
 * unreadable, so the check pins the face.
 */
const MIN_FACE: Size = { height: 17, width: 13 };

/**
 * The least visible gap between two seats' rivers, and between a river and the centre, in CSS pixels: rivers never touch
 * each other or the centre, so each reads as its seat's block (the composition keeps 0.3 of a river tile, 6px on the
 * 667x375 floor).
 */
const MIN_RIVER_GAP = 3;
/** The least gap between an opponent's strip and any river, so neither reads as a row of the other (8px drawn). */
const MIN_STRIP_GAP = 6;

/** Each badge's fixed point by its seat, where a page measured a board in landscape (`checkBadgePlaces`). */
const BADGE_ANCHORS = new PageRecord<Readonly<Record<string, readonly [number, number]>>>();

const DOCUMENT_AT = { at: [UPRIGHT_PHONE] } as const;

/**
 * The board's worst cases. The full hands with five offers bind the band and the worst case is the densest table, so
 * both stand at the viewports guarding a path of the layout, as the longest strips (four open kans a seat) do where a
 * strip binds and the riichi call at every seat where a call's words do; a story they cover in a harsher form is left
 * out (full rivers, concealed hands, a tsumo at every seat), and every other dense story is checked once at the
 * floor, where density binds, or also where its own path does.
 */
const PAGES: readonly PageCase[] = [
    ...["concealed_hands", "full_hands"].map((state): PageCase => ({
        at: [MID_DESKTOP, FLOOR],
        check: checkSeparatedHandDepth,
        kind: "own",
        name: `board-hand-depth-${state}`,
        path: `/play/storybook/board?state=${state}`,
        required: { visible: [".board-strip--right .hand .tile"] },
    })),
    { ...documentCase("storybook", "/play/storybook", ".storybook .tile"), ...DOCUMENT_AT },
    {
        ...documentCase("storybook-hand", "/play/storybook/hand", ".storybook .hand .tile"),
        ...DOCUMENT_AT,
    },
    {
        ...documentCase(
            "storybook-discards",
            "/play/storybook/discards",
            ".storybook .discards .tile",
        ),
        ...DOCUMENT_AT,
    },
    {
        ...documentCase("storybook-melds", "/play/storybook/melds", ".storybook .meld .tile"),
        ...DOCUMENT_AT,
    },
    {
        ...boardCase("board-callouts-riichi", "?state=worst&callout=riichi", [".board-callout"]),
        at: [FLOOR, MID_DESKTOP, NARROW_DESKTOP],
        longNames: true,
    },
    {
        ...boardCase("board-callouts-adjacent", "?state=riichi_latest&callout=riichi&offers=five", [
            ".board-callout",
            ".discard-tile--last.discard-tile-riichi",
            ACTION,
        ]),
        at: [FLOOR, SHORT_DESKTOP],
    },
    {
        ...boardCase("board-nineteen-discards", "?state=full_rivers&offers=five", [ACTION]),
        at: [FLOOR, MID_DESKTOP],
    },
    {
        ...boardCase("board-worst", "?state=worst&pin=right", [
            ".board-strip .meld",
            ".board-dora .tile",
            ".board-center__seat--left .board-center__diff--right",
            ".nameplate__ai",
        ]),
        at: [FLOOR, NOTCH_PHONE, FULLSCREEN_PHONE, MID_DESKTOP, NARROW_DESKTOP],
        contrast: true,
        longNames: true,
    },
    {
        ...boardCase("board-worst-offers", "?state=worst&offers=five", [
            ACTION,
            ".board-strip .meld",
        ]),
        at: [...WORST_CASES, ULTRAWIDE],
        longNames: true,
    },
    {
        ...boardCase("board-full-hands", "?state=full_hands&offers=five", [ACTION]),
        at: [...WORST_CASES, SHORT_DESKTOP, NARROW_DESKTOP, ...LAPTOPS, ...WIDER_PHONES],
    },
    {
        ...boardCase("board-full-hands-riichi", "?state=full_hands&offers=riichi", [
            `${ACTION}[aria-pressed="true"]`,
            ".decision-controls__bank",
        ]),
        at: [FLOOR, SHORT_DESKTOP],
    },
    boardCase("board-mixed-hands-a", "?state=mixed_hands_a", [".board-strip .meld"]),
    boardCase("board-mixed-hands-b", "?state=mixed_hands_b", [".board-strip .meld"]),
    boardCase("board-mixed-hands-c", "?state=mixed_hands_c", [".board-strip .meld"]),
    {
        ...boardCase("board-kans-a", "?state=kans_a&callout=every&pin=left", [
            ".board-strip .meld",
            ".board-callout",
            ".board-center__diff-label--left",
        ]),
        longNames: true,
    },
    {
        ...boardCase("board-kans-b", "?state=kans_b&callout=triple_ron&pin=bottom", [
            ".board-strip .meld",
            ".board-callout--ron",
            ".discard-tile--last",
        ]),
        longNames: true,
    },
    {
        ...boardCase("board-worst-bank", "?state=worst&offers=bank&pin=left", [
            ACTION,
            ".decision-timer--bank .decision-controls__bank--draining",
        ]),
        longNames: true,
    },
    {
        ...boardCase("board-kans-c", "?state=kans_c&offers=five&pin=top", [
            ACTION,
            ".board-strip .meld",
        ]),
        at: [FLOOR, SHORT_DESKTOP, NARROW_DESKTOP, ...LAPTOPS, ...WIDER_PHONES],
        longNames: true,
    },
];

const OWN_DISCARDS_THIRD_ROW = "bottom-discards-third-row";
/**
 * The spec's accepted rare overlap: a decision control over the own river's third row.
 */
const ACCEPTED_OVERLAPS: ReadonlySet<string> = new Set(
    [["actions", OWN_DISCARDS_THIRD_ROW]].map((pair) => pair.toSorted().join(" x ")),
);

/** The areas that overlap, but for the spec's accepted rare overlap over a river's far discards. */
function findAreaOverlaps(board: BoardMeasure): string[] {
    const ownThirdRow = ownRiverThirdRow(board);
    const grouped = board.grouped.map((entry) => {
        if (
            entry.group === "bottom-discards" &&
            ownThirdRow.some((tile) => sameBox(tile, entry.box))
        ) {
            return { ...entry, group: OWN_DISCARDS_THIRD_ROW };
        }
        return entry;
    });
    return findOverlaps(grouped).filter((pair) => !ACCEPTED_OVERLAPS.has(pair));
}

function checkBoardContent(board: BoardMeasure, report: PageReport): void {
    const { boardClient: client, boardScroll: scroll } = board;
    report.expect(
        scroll.width <= client.width + EPSILON && scroll.height <= client.height + EPSILON,
        `board content overflows its box: scroll ${describeSize(scroll)} > client ${describeSize(client)}`,
    );
    report.expect(
        board.tiles.length > 0 && board.hiddenTiles === 0,
        `${board.hiddenTiles} hidden tile(s)`,
    );
    const outside = board.tiles.filter((tile) => !contains(board.board, tile));
    report.expect(outside.length === 0, `${outside.length} tile(s) outside the board`);
    const strayPlates = board.nameplates.filter((plate) => !contains(board.board, plate));
    report.expect(strayPlates.length === 0, `${strayPlates.length} nameplate(s) outside the board`);
    const overlaps = findAreaOverlaps(board);
    report.expect(overlaps.length === 0, `areas overlap: ${overlaps.join(", ")}`);
    report.expect(
        board.clippedWords.length === 0,
        `text cut short: ${board.clippedWords.join(", ")}`,
    );

    const small = board.fonts.filter((font) => font.px < MIN_TEXT_PX);
    report.expect(board.fonts.length > 0, "no board text measured");
    report.expect(
        small.length === 0,
        `text under ${MIN_TEXT_PX}px: ${small.map((font) => `${font.name} ${font.px}px`).join(", ")}`,
    );
}

function checkAside(board: BoardMeasure, frame: Box, report: PageReport): void {
    const { aside } = board;
    if (aside === null) {
        return;
    }
    report.expect(!intersects(aside.box, board.board), "the aside overlaps the board");
    report.expect(
        contains(frame, aside.box),
        `the aside ${describeBox(aside.box)} leaves the page`,
    );
    const scrolls = aside.scroll.height > aside.box.height + EPSILON;
    report.expect(
        !scrolls || aside.overflowY === "auto" || aside.overflowY === "scroll",
        "the aside's controls overflow it with no way to scroll to them",
    );
}

/**
 * The board stays on the screen, and the aside beside it on the screen, or on the page where a storybook's switches lie below the board.
 */
function checkPlacement(
    board: BoardMeasure,
    { measure, screen }: { readonly measure: PageMeasure; readonly screen: Box },
    report: PageReport,
): void {
    const pageExtent = { height: measure.scrollHeight, left: 0, top: 0, width: measure.innerWidth };
    report.expect(
        contains(screen, board.board),
        `the board ${describeBox(board.board)} leaves the viewport`,
    );
    const asideBelow =
        board.aside !== null &&
        board.aside.story &&
        board.aside.box.top >= board.board.top + board.board.height - EPSILON;
    checkAside(board, asideBelow ? pageExtent : screen, report);
}

/**
 * The local hand stays on the screen, at least the viewport's floor where it has one (a phone's tap target), and its
 * tiles are never smaller than any river, other seat's hand or meld, or dora tile. Its sizes are the
 * tiles' slots, the tap targets, so a held-back face's recess inside its slot does not count, but a smaller slot does.
 */
function checkLocalHand(
    board: BoardMeasure,
    { floor, screen }: { readonly floor: Size | undefined; readonly screen: Box },
    report: PageReport,
): void {
    const hidden = board.localTiles.filter((tile) => !contains(screen, tile));
    report.expect(hidden.length === 0, `${hidden.length} local hand tile(s) outside the viewport`);
    const unread = board.localTileSizes.filter(
        (tile) => !Number.isFinite(tile.width) || !Number.isFinite(tile.height),
    );
    report.expect(
        unread.length === 0,
        `${unread.length} local hand tile(s) whose slot could not be measured (no .hand-tile)`,
    );
    if (floor !== undefined) {
        const small = board.localTileSizes.filter(
            (tile) => tile.width < floor.width - EPSILON || tile.height < floor.height - EPSILON,
        );
        report.expect(
            small.length === 0,
            `local hand tiles under ${describeSize(floor)}: ${small.map(describeSize).join(", ")}`,
        );
    }
    const smallestOwn = Math.min(
        ...board.localTileSizes.map((tile) => Math.max(tile.width, tile.height)),
    );
    const largestOther = Math.max(0, ...board.otherTiles.map(longSide));
    report.expect(
        smallestOwn >= largestOther - EPSILON,
        `a local hand tile (${smallestOwn.toFixed(1)}px) is smaller than another tile on the board (${largestOther.toFixed(1)}px)`,
    );
}

/**
 * A side strip's full hand, as its place reserves it whatever the seat holds, stays clear of the play switches and the
 * decision's controls and timer (the cog reserves no room): a full concealed hand is the strips' binding capacity.
 */
function checkHandReach(board: BoardMeasure, report: PageReport): void {
    const controls = [
        ...board.switches.map((control) => control.box),
        ...board.actions,
        ...(board.timer === null ? [] : [board.timer]),
    ];
    const unread = board.handReach.filter(
        (reach) => !Number.isFinite(reach.box.width) || !Number.isFinite(reach.box.height),
    );
    report.expect(
        unread.length === 0,
        `a side hand's full reach could not be read (--geo-full-reach, --bh): ${unread.map((reach) => reach.group).join(", ")}`,
    );
    const crowded = board.handReach.filter((reach) =>
        controls.some((control) => intersects(reach.box, control)),
    );
    report.expect(
        crowded.length === 0,
        `a side hand's full reach meets a switch or a decision control: ${crowded.map((reach) => `${reach.group} ${describeBox(reach.box)}`).join(", ")}`,
    );
}

/** An opponent's concealed hand stands at the river tile's size (the spec's Proportions). */
function checkHandScale(board: BoardMeasure, report: PageReport): void {
    const { hands, river } = board.tileScale;
    if (river === null) {
        return;
    }
    const off = hands.filter((width) => Math.abs(width - river) > 0.5);
    report.expect(
        off.length === 0,
        `opponent hand tiles off the river tile's ${river}px width: ${off.slice(0, 3).join(", ")}px`,
    );
}

/** The derived proportions the gate holds at a reference viewport, as the spec's Proportions table gives them. */
interface DerivedProportions {
    /** River tile width over own hand tile width: the own hand leads the river by this ratio. */
    readonly riverToOwn: number;
    /** The pinwheel's gap, in river tiles, between a river and the centre and between neighbouring rivers. */
    readonly riverGap: number;
}

/**
 * The derived proportions the gate holds, at the three reference viewports the spec derives them for (Proportions),
 * each within `DERIVED_TOLERANCE`: a drift past it changes the approved composition. The spec's other ratios are left to
 * review; the opponent's hand at the river tile holds everywhere (`checkHandScale`).
 */
const DERIVED: ReadonlyMap<string, DerivedProportions> = new Map([
    [FLOOR, { riverGap: 0.29, riverToOwn: 0.44 }],
    [NOTCH_PHONE, { riverGap: 0.3, riverToOwn: 0.45 }],
    [MID_DESKTOP, { riverGap: 0.31, riverToOwn: 0.63 }],
]);
const DERIVED_TOLERANCE = 0.02;

/** How far apart two boxes stand: the larger of their gaps across and down, 0 where they touch or overlap. */
function separation(first: Box, second: Box): number {
    const across = Math.max(
        second.left - (first.left + first.width),
        first.left - (second.left + second.width),
    );
    const down = Math.max(
        second.top - (first.top + first.height),
        first.top - (second.top + second.height),
    );
    return Math.max(0, across, down);
}

/** Each seat's river that holds a settled tile, by its nearest one's distance from the centre, in pixels. */
function riverGapsFromCenter(board: BoardMeasure, center: Box): ReadonlyMap<string, number> {
    const gaps = new Map<string, number>();
    for (const { box, group } of board.settledRiverTiles) {
        gaps.set(group, Math.min(gaps.get(group) ?? Infinity, separation(box, center)));
    }
    return gaps;
}

/**
 * At a reference viewport, the own hand tile leads the river tile by the spec's ratio, every seat's river that holds a
 * tile stands the pinwheel's gap from the centre, and no two seats' rivers stand closer than that gap (a sparse river
 * stands farther from its neighbour, so that gap has no upper bound).
 */
function checkDerivedProportions(board: BoardMeasure, viewport: string, report: PageReport): void {
    const derived = DERIVED.get(viewport);
    const { own, river } = board.tileScale;
    if (derived === undefined || river === null || own === null) {
        return;
    }
    const ratio = river / own;
    report.expect(
        Math.abs(ratio - derived.riverToOwn) <= DERIVED_TOLERANCE,
        `the river tile is ${ratio.toFixed(3)} of the own tile (${river}px / ${own.toFixed(1)}px), not ${derived.riverToOwn}`,
    );
    if (board.center !== null) {
        const off = [...riverGapsFromCenter(board, board.center)].filter(
            ([, gap]) => Math.abs(gap / river - derived.riverGap) > DERIVED_TOLERANCE,
        );
        report.expect(
            off.length === 0,
            `rivers off the pinwheel's ${derived.riverGap} of a river tile from the centre: ${off.map(([seat, gap]) => `${seat} ${(gap / river).toFixed(3)} (${gap.toFixed(1)}px)`).join(", ")}`,
        );
    }
    const least = (derived.riverGap - DERIVED_TOLERANCE) * river;
    const crowded = new Set<string>();
    for (const [index, first] of board.riverTiles.entries()) {
        for (const second of board.riverTiles.slice(index + 1)) {
            if (first.group !== second.group && separation(first.box, second.box) < least) {
                crowded.add([first.group, second.group].toSorted().join(" x "));
            }
        }
    }
    report.expect(
        crowded.size === 0,
        `rivers closer than ${derived.riverGap} of a river tile (${least.toFixed(1)}px): ${[...crowded].join(", ")}`,
    );
}

/**
 * Every river's tiles and another seat's face-up tiles stay readable in landscape: at the face floor, or on a browser
 * box with its bars shown at the river tile its geometry test pins for it, so a regression under that still fails.
 */
function checkFaces(board: BoardMeasure, viewport: Viewport, report: PageReport): void {
    const floor: Size = viewport.barsShown?.riverFloor ?? MIN_FACE;
    function underFloor(tile: Box): boolean {
        return (
            Math.min(tile.width, tile.height) < floor.width - EPSILON ||
            longSide(tile) < floor.height - EPSILON
        );
    }
    const smallRiver = board.riverTiles.filter(({ box }) => underFloor(box));
    report.expect(
        smallRiver.length === 0,
        `river tiles under ${describeSize(floor)} (${board.tileScale.river}px river tile): ${smallRiver
            .slice(0, 3)
            .map(({ box, group }) => `${group} ${describeBox(box)}`)
            .join(", ")}`,
    );
    const small = board.opponentFaces.filter((tile) => underFloor(tile));
    report.expect(
        small.length === 0,
        `face-up tiles of other seats under ${describeSize(floor)}: ${small.slice(0, 3).map(describeBox).join(", ")}`,
    );
}

/** The settings cog sits on the board and the screen, large enough to tap. */
function checkSettingsCog(board: BoardMeasure, screen: Box, report: PageReport): void {
    for (const cog of board.menu) {
        report.expect(
            contains(board.board, cog) && contains(screen, cog),
            `the settings cog ${describeBox(cog)} is off the board or screen`,
        );
        report.expect(
            cog.width >= MIN_ACTION_SIZE - EPSILON && cog.height >= MIN_ACTION_SIZE - EPSILON,
            `the settings cog is under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${describeBox(cog)}`,
        );
    }
}

/** Every badge is a control: its tap area, the plate's button, meets the control floor whatever its pill's size. */
function checkBadgeTaps(board: BoardMeasure, report: PageReport): void {
    const expected = board.family === "phone" ? 3 : 4;
    const small = board.nameplates.filter(
        (plate) =>
            plate.width < MIN_ACTION_SIZE - EPSILON || plate.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        board.nameplates.length === expected && small.length === 0,
        `badge tap areas under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE} (${board.nameplates.length} of ${expected} shown): ${small.map(describeBox).join(", ")}`,
    );
}

/**
 * The seats the board cues as in turn, as painted, never by their state's class: the centre's edge lit on their side
 * (shown, its edge's line opaque and of some width), and their badge's pill underlined (an opaque inset shadow, the pill shown).
 */
interface TurnCues {
    readonly bars: readonly string[];
    readonly badges: readonly string[];
    readonly ownBadgeShown: boolean;
    /** A panel says no round plays: a replay's seating, a round's result or the game's end, never the opening screen. */
    readonly roundOver: boolean;
}

function measureTurnCues(page: Page): Promise<TurnCues> {
    return page.evaluate(() => {
        const board = document.querySelector(".game-board");
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function seatOf(element: Element, block: string): string {
            return (
                new RegExp(`${block}--(?<seat>bottom|right|top|left)\\b`, "u").exec(
                    element.className,
                )?.groups?.seat ?? "?"
            );
        }
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function opaque(colour: string): boolean {
            const channels = (/\((?<inner>[^)]*)\)/u.exec(colour)?.groups?.inner ?? "")
                .split(/[\s,/]+/u)
                .filter((channel) => channel !== "");
            const alpha = channels.length >= 4 ? Number.parseFloat(channels[3]) : 1;
            return colour !== "" && colour !== "transparent" && alpha > 0;
        }
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function shown(element: Element): boolean {
            return element.checkVisibility({ opacityProperty: true, visibilityProperty: true });
        }
        const bars = [...(board?.querySelectorAll(".board-center__seat") ?? [])].filter((seat) => {
            const bar = getComputedStyle(seat, "::after");
            return (
                shown(seat) &&
                bar.content !== "none" &&
                bar.display !== "none" &&
                bar.visibility === "visible" &&
                Number.parseFloat(bar.opacity) > 0 &&
                Number.parseFloat(bar.width) > 0 &&
                Number.parseFloat(bar.height) > 0 &&
                Number.parseFloat(bar.borderBottomWidth) > 0 &&
                opaque(bar.borderBottomColor)
            );
        });
        const underlined = [...(board?.querySelectorAll(".nameplate") ?? [])].filter((plate) => {
            const pill = plate.querySelector(".nameplate__pill");
            if (pill === null || !shown(pill)) {
                return false;
            }
            const cue = getComputedStyle(pill, "::after");
            return (
                cue.visibility === "visible" &&
                Number.parseFloat(cue.width) > 0 &&
                Number.parseFloat(cue.height) > 0 &&
                opaque(cue.backgroundColor)
            );
        });
        const ownPlate = board?.querySelector(".nameplate--bottom");
        return {
            badges: underlined.map((plate) => seatOf(plate, "nameplate")),
            bars: bars.map((seat) => seatOf(seat, "board-center__seat")),
            ownBadgeShown: ownPlate?.checkVisibility() === true,
            roundOver:
                board?.querySelector(
                    ".board-overlay :is(.round-end-result, .seating:not(:has(.seating__confirm)))",
                ) !== null,
        };
    });
}

/**
 * One cue for the seat in turn: at most one seat's bar drawn on the centre, the same seat's badge underlined and no
 * other's, exactly one while a decision is open on the board with no panel over it (a round plays), and none under
 * a replay's seating, a round's result or the game's end (no round plays); the live opening screen stands over a
 * round in play, its dealer cued.
 */
function checkTurnCue(cues: TurnCues, board: BoardMeasure, report: PageReport): void {
    const cuedByBadge = cues.bars.filter((seat) => seat !== "bottom" || cues.ownBadgeShown);
    report.expect(
        cues.bars.length <= 1 && cuedByBadge.join(", ") === cues.badges.join(", "),
        `turn cues on more than one seat or apart: bars ${cues.bars.join(", ") || "none"}, badges ${cues.badges.join(", ") || "none"}`,
    );
    if (cues.roundOver) {
        report.expect(
            cues.bars.length + cues.badges.length === 0,
            `a seat cued in turn under a panel where no round plays: bars ${cues.bars.join(", ") || "none"}, badges ${cues.badges.join(", ") || "none"}`,
        );
    }
    if (board.timer !== null && board.overlay === null) {
        report.expect(
            cues.bars.length === 1,
            `a round plays with ${cues.bars.length} seat(s) cued in turn, not one`,
        );
    }
}

/**
 * The rivers keep their pinwheel's gaps: no river's tile comes within a few pixels of another seat's river or of the
 * centre, so a dense board still reads as four blocks, never one pile (look spec, Rivers).
 */
function checkRiverGaps(board: BoardMeasure, report: PageReport): void {
    const touching = new Set<string>();
    for (const [index, first] of board.riverTiles.entries()) {
        for (const second of board.riverTiles.slice(index + 1)) {
            if (first.group !== second.group && near(first.box, second.box, MIN_RIVER_GAP)) {
                touching.add([first.group, second.group].toSorted().join(" x "));
            }
        }
        if (board.center !== null && near(first.box, board.center, MIN_RIVER_GAP)) {
            touching.add(`${first.group} x center`);
        }
    }
    report.expect(
        touching.size === 0,
        `rivers within ${MIN_RIVER_GAP}px of each other or the centre: ${[...touching].join(", ")}`,
    );
}

/** An opponent's strip stands apart from the rivers, so its backs or faces never read as a river's row (look spec). */
function checkStripsApart(board: BoardMeasure, report: PageReport): void {
    const adjacent = new Set<string>();
    for (const strip of board.stripTiles) {
        for (const river of board.riverTiles) {
            if (near(strip.box, river.box, MIN_STRIP_GAP)) {
                adjacent.add(`${strip.group} strip x ${river.group} river`);
            }
        }
    }
    report.expect(
        adjacent.size === 0,
        `strips within ${MIN_STRIP_GAP}px of a river: ${[...adjacent].join(", ")}`,
    );
}

/** Each badge's fixed point: its box's side its place is set from, and its top (the own badge's foot). */
function badgeAnchors(board: BoardMeasure): Readonly<Record<string, readonly [number, number]>> {
    return Object.fromEntries(
        board.badges.map(({ box, group }) => {
            const right = box.left + box.width;
            const bottom = box.top + box.height;
            const point: readonly [number, number] =
                group === "right" || group === "top"
                    ? [right, box.top]
                    : [box.left, group === "bottom" ? bottom : box.top];
            return [group, point];
        }),
    );
}

/**
 * A call shown by its seat stays on the board and never lies over the local hand's tiles, which take the taps, or over a
 * decision control or the timer; it may cover what an open offer refers to, for the moment it shows.
 */
function checkCallouts(board: BoardMeasure, report: PageReport): void {
    const outside = board.callouts.filter((callout) => !contains(board.board, callout));
    report.expect(outside.length === 0, `${outside.length} call(s) off the board`);
    const overHand = board.callouts.filter((callout) =>
        board.localTiles.some((tile) => intersects(callout, tile)),
    );
    report.expect(
        overHand.length === 0,
        `call(s) over the local hand: ${overHand.map(describeBox).join(", ")}`,
    );
    const controls = [
        ...(board.decisionCorner?.buttons ?? []),
        ...(board.timer ? [board.timer] : []),
    ];
    const overControl = board.callouts.filter((callout) =>
        controls.some((control) => intersects(callout, control)),
    );
    report.expect(
        overControl.length === 0,
        `call(s) over a decision control or the timer: ${overControl.map(describeBox).join(", ")}`,
    );
}

/** One piece of the label: its text, whether it shows, its box and the part of it its clipping ancestors leave. */
interface LabelPiece {
    readonly text: string;
    readonly shown: boolean;
    readonly box: Box;
    readonly visible: Box | null;
}

/**
 * The centre's label for the badge whose differences show (a hovered badge's on a hovering screen, else the pinned
 * one's): that badge's name and wind letter, the label's pieces, its font size and the name's width on one line.
 */
interface DiffLabelMeasure {
    readonly seat: string;
    readonly name: string;
    readonly windLetter: string;
    readonly fontPx: number;
    readonly nameWidth: number;
    readonly label: LabelPiece;
    readonly vs: LabelPiece;
    readonly slot: LabelPiece;
    readonly nameText: LabelPiece;
    readonly wind: LabelPiece;
    readonly otherLabelsShown: number;
    readonly center: Box;
    readonly centerPieces: readonly Box[];
}

type DiffLabelRead =
    | { readonly kind: "none"; readonly labelsShown: number }
    | { readonly kind: "unreadable"; readonly why: string }
    | ({ readonly kind: "label" } & DiffLabelMeasure);

function measureDiffLabel(page: Page): Promise<DiffLabelRead> {
    return page.evaluate(() => {
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function box(rect: DOMRect | Box): Box {
            return {
                height: rect.height,
                left: rect.left + window.scrollX,
                top: rect.top + window.scrollY,
                width: rect.width,
            };
        }
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function shown(element: Element): boolean {
            const rect = element.getBoundingClientRect();
            return (
                rect.width >= 1 &&
                rect.height >= 1 &&
                element.checkVisibility({ opacityProperty: true, visibilityProperty: true })
            );
        }
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function piece(element: Element | null): LabelPiece {
            if (element === null) {
                return {
                    box: { height: 0, left: 0, top: 0, width: 0 },
                    shown: false,
                    text: "",
                    visible: null,
                };
            }
            const rect = element.getBoundingClientRect();
            let { bottom, left, right, top } = rect;
            for (let above = element.parentElement; above !== null; above = above.parentElement) {
                const style = getComputedStyle(above);
                if (style.overflowX !== "visible" || style.overflowY !== "visible") {
                    const outer = above.getBoundingClientRect();
                    left = Math.max(left, outer.left);
                    top = Math.max(top, outer.top);
                    right = Math.min(right, outer.right);
                    bottom = Math.min(bottom, outer.bottom);
                }
            }
            return {
                box: box(rect),
                shown: shown(element),
                text: element.textContent.replaceAll(/\s+/gu, " ").trim(),
                visible:
                    right - left >= 1 && bottom - top >= 1
                        ? box({ height: bottom - top, left, top, width: right - left })
                        : null,
            };
        }
        const labels = [...document.querySelectorAll(".board-center__diff-label")];
        const hovered = matchMedia("(hover: hover)").matches
            ? document.querySelector(".nameplate:hover")
            : null;
        const plate = hovered ?? document.querySelector(".nameplate[aria-pressed='true']");
        if (plate === null) {
            return { kind: "none" as const, labelsShown: labels.filter(shown).length };
        }
        const seat = /nameplate--(?<seat>bottom|right|top|left)\b/u.exec(plate.className)?.groups
            ?.seat;
        const label = document.querySelector(`.board-center__diff-label--${seat ?? "none"}`);
        const name = label?.querySelector(".board-center__diff-name") ?? null;
        const center = document.querySelector(".board-center");
        const context = document.createElement("canvas").getContext("2d");
        if (
            seat === undefined ||
            label === null ||
            name === null ||
            center === null ||
            context === null
        ) {
            return {
                kind: "unreadable" as const,
                why: "no label, name or centre for the shown badge",
            };
        }
        const nameStyle = getComputedStyle(name);
        context.font = `${nameStyle.fontStyle} ${nameStyle.fontWeight} ${nameStyle.fontSize} ${nameStyle.fontFamily}`;
        return {
            center: box(center.getBoundingClientRect()),
            centerPieces: [
                ...center.querySelectorAll(
                    ".board-center__round, .board-center__counts, .board-center__score-line",
                ),
            ]
                .filter(shown)
                .map((element) => box(element.getBoundingClientRect())),
            fontPx: Number.parseFloat(getComputedStyle(label).fontSize),
            kind: "label" as const,
            label: piece(label),
            name: plate.getAttribute("title") ?? "",
            nameText: piece(name),
            nameWidth: context.measureText(name.textContent).width,
            otherLabelsShown: labels.filter((other) => other !== label && shown(other)).length,
            seat,
            slot: piece(label.querySelector(".board-center__diff-slot")),
            vs: piece(label.querySelector(".board-center__diff-vs")),
            wind: piece(label.querySelector(".board-center__diff-wind")),
            windLetter:
                center
                    .querySelector(`.board-center__seat--${seat} .board-center__wind`)
                    ?.textContent.trim() ?? "",
        };
    });
}

/**
 * How far, in CSS pixels, the name's width measured on a canvas may part from its line's width before the label's
 * choice between the name and the wind is held to it: within it, the layout's own choice stands.
 */
const NAME_FIT_TOLERANCE = 1;

/** Each seat wind's name by the letter its side of the centre shows. */
const WIND_NAMES: ReadonlyMap<string, string> = new Map([
    ["E", "East"],
    ["S", "South"],
    ["W", "West"],
    ["N", "North"],
]);

/** Whether `inner` lies inside `outer`, within a pixel. */
function within(outer: Box, inner: Box): boolean {
    const grownOuter = {
        height: outer.height + 2,
        left: outer.left - 1,
        top: outer.top - 1,
        width: outer.width + 2,
    };
    return contains(grownOuter, inner);
}

/** Whether a piece shows whole: displayed, and no clipping ancestor cuts any of it. */
function wholeShown(piece: LabelPiece): boolean {
    return piece.shown && piece.visible !== null && within(piece.visible, piece.box);
}

/**
 * While a badge's differences show, the centre shows that badge's label alone, at a readable size: "vs" and, on the
 * line under it, the seat's whole name where it fits that line, else the seat's own wind, each wholly shown, inside
 * the centre and clear of the wall's count and every score. With no badge's differences showing, no label shows.
 */
async function checkDiffLabel(page: Page, report: PageReport): Promise<void> {
    const read = await measureDiffLabel(page);
    if (read.kind === "none") {
        report.expect(
            read.labelsShown === 0,
            `${read.labelsShown} differences label(s) show with no badge pinned`,
        );
        return;
    }
    if (read.kind === "unreadable") {
        report.expect(false, `the pinned label could not be read: ${read.why}`);
        return;
    }
    const where = `the ${read.seat} badge's label`;
    report.expect(read.otherLabelsShown === 0, `another seat's label shows beside ${where}`);
    report.expect(
        wholeShown(read.label),
        `${where} is not shown whole: ${describeBox(read.label.box)}`,
    );
    report.expect(
        read.fontPx >= MIN_TEXT_PX,
        `${where} is ${read.fontPx}px, under ${MIN_TEXT_PX}px`,
    );
    report.expect(
        read.vs.text === "vs" && wholeShown(read.vs),
        `${where} does not show "vs" whole`,
    );
    const spare = read.slot.box.width - read.nameWidth;
    const fits = Math.abs(spare) <= NAME_FIT_TOLERANCE ? read.wind.visible === null : spare > 0;
    const expected = fits ? read.nameText : read.wind;
    const expectedText = fits
        ? read.name
        : (WIND_NAMES.get(read.windLetter) ?? `wind "${read.windLetter}"`);
    report.expect(
        expected.text === expectedText &&
            wholeShown(expected) &&
            within(read.slot.box, expected.box),
        `${where} does not show "${expectedText}" whole on its line (name ${read.nameWidth.toFixed(1)}px, line ${read.slot.box.width.toFixed(1)}px): it shows "${expected.text}" at ${describeBox(expected.box)}`,
    );
    const other = fits ? read.wind : read.nameText;
    report.expect(
        other.visible === null,
        `${where} shows "${other.text}" beside "${expectedText}"`,
    );
    report.expect(
        contains(read.center, read.label.box),
        `${where} ${describeBox(read.label.box)} leaves the centre ${describeBox(read.center)}`,
    );
    const crowded = read.centerPieces.filter((piece) => intersects(piece, read.label.box));
    report.expect(
        crowded.length === 0,
        `${where} ${describeBox(read.label.box)} meets the centre's ${crowded.map(describeBox).join(", ")}`,
    );
}

/**
 * Every badge keeps one place at a viewport, whatever the seats hold: the live board's decisions stories (an anchor's
 * three checkpoints, the dense prompts, panels over it) all put each seat's badge at the same point.
 */
function checkBadgePlaces(results: readonly TaskResult[]): string[] {
    const live = results.flatMap(({ page, report, viewport }) => {
        const anchors = BADGE_ANCHORS.read(report);
        return page.startsWith("decisions-") && anchors !== undefined
            ? [{ anchors, page, viewport }]
            : [];
    });
    const viewports = [...new Set(live.map(({ viewport }) => viewport))];
    return viewports.flatMap((viewport) => {
        const pages = live.filter((result) => result.viewport === viewport);
        const placed = pages.flatMap(({ anchors, page }) =>
            Object.entries(anchors).map(([seat, point]) => ({
                page,
                point,
                seat,
            })),
        );
        return [...new Set(placed.map(({ seat }) => seat))].flatMap((seat) => {
            const [first, ...rest] = placed.filter((place) => place.seat === seat);
            if (first === undefined) {
                return [];
            }
            return rest
                .filter(
                    ({ point }) =>
                        Math.abs(point[0] - first.point[0]) > EPSILON ||
                        Math.abs(point[1] - first.point[1]) > EPSILON,
                )
                .map(
                    ({ page, point }) =>
                        `${viewport}: the ${seat} badge stands at ${Math.round(point[0])},${Math.round(point[1])} on ${page}, at ${Math.round(first.point[0])},${Math.round(first.point[1])} on ${first.page}`,
                );
        });
    });
}

/** A landscape phone's centre at its least, whatever its river tile asks (`board-constants.ts`'s, not importable here). */
const PHONE_CENTRE_LEAST: Size = { height: 68, width: 100 };

function isLandscapePhone(viewport: Viewport): boolean {
    return !viewport.desktop && !viewport.portrait;
}

function checkCenterScale(board: BoardMeasure, viewport: Viewport, report: PageReport): void {
    const { center, tileScale } = board;
    report.expect(center !== null, "the centre is measurable");
    if (center === null || tileScale.river === null) {
        return;
    }
    const riverRow = RIVER_ROW_SIZE * tileScale.river;
    if (isLandscapePhone(viewport)) {
        const leastWidth = Math.max(riverRow, PHONE_CENTRE_LEAST.width);
        report.expect(
            center.width + EPSILON >= leastWidth,
            `centre ${describeSize(center)} is narrower than ${leastWidth}px`,
        );
        report.expect(
            center.height + EPSILON >= PHONE_CENTRE_LEAST.height,
            `centre ${describeSize(center)} is shorter than ${PHONE_CENTRE_LEAST.height}px`,
        );
        return;
    }
    report.expect(
        Math.abs(center.width - center.height) <= EPSILON,
        `centre is not square: ${describeSize(center)}`,
    );
    report.expect(
        Math.min(center.width, center.height) + EPSILON >= riverRow,
        `centre ${describeSize(center)} is smaller than a six-tile row (${riverRow}px)`,
    );
}

/** How tall a single line of the counts stands at most, in its own font size. */
const ONE_LINE_EMS = 1.6;

/** A centre narrower than this (px, the next six river tiles past 108) may wrap its counts: they need about 48px. */
const ONE_LINE_LEAST_CENTRE_WIDTH = 114;

/**
 * A landscape phone's centre holds its round and counts inside its box, and the counts stay on one line unless the
 * centre is among the narrowest, which may wrap them.
 */
function checkCenterContent(board: BoardMeasure, viewport: Viewport, report: PageReport): void {
    const { center, centerTexts, fonts } = board;
    if (center === null || !isLandscapePhone(viewport)) {
        return;
    }
    const shown = centerTexts.filter(({ box }) => box.width > 0);
    const round = shown.find(({ group }) => group.startsWith("board-center__round"));
    const counts = shown.find(({ group }) => group.startsWith("board-center__counts"));
    for (const piece of [round, counts]) {
        report.expect(
            piece === undefined || contains(center, piece.box),
            `${piece?.group ?? "a centre text"} ${piece === undefined ? "" : describeBox(piece.box)} is outside the centre ${describeBox(center)}`,
        );
    }
    const countsPx = fonts.find(({ name }) => name === "board-center__counts")?.px;
    if (
        center.width < ONE_LINE_LEAST_CENTRE_WIDTH ||
        counts === undefined ||
        countsPx === undefined
    ) {
        return;
    }
    report.expect(
        counts.box.height < ONE_LINE_EMS * countsPx,
        `the centre's counts wrap: ${counts.box.height.toFixed(1)}px tall at ${countsPx}px text`,
    );
}

/**
 * The board as a whole: its content inside its box and readable, the table's surface clear of the aside, the board on
 * the page, the pinned badge's label, every badge's tap area on a supported screen, and in landscape on a supported screen the own hand, the rivers' and strips'
 * gaps, the badges, the page's corner and the side hands' reserved reach.
 */
/** Below this width a desktop window is best-effort (the spec's support tiers), and a whole name may not fit its lane. */
const PRIMARY_DESKTOP_WIDTH = 1100;

function keepsNamesWhole(viewport: Viewport, screen: Box): boolean {
    return !viewport.desktop || screen.width >= PRIMARY_DESKTOP_WIDTH;
}

async function checkBoard({
    board,
    measure,
    options,
    page,
    report,
    screen,
    viewport,
}: BoardRun): Promise<void> {
    checkBoardContent(board, report);
    await checkDiffLabel(page, report);
    report.expect(
        board.aside === null || board.zones === null || !intersects(board.zones, board.aside.box),
        `the table's surface ${board.zones === null ? "" : describeBox(board.zones)} reaches under the aside`,
    );
    if (viewport.supported) {
        checkCenterScale(board, viewport, report);
        checkCenterContent(board, viewport, report);
        const crowded = findOverlaps(board.centerTexts);
        report.expect(crowded.length === 0, `centre pieces overlap: ${crowded.join(", ")}`);
    }
    checkCallouts(board, report);
    checkPlacement(board, { measure, screen }, report);
    checkTurnCue(await measureTurnCues(page), board, report);
    if (viewport.supported) {
        checkBadgeTaps(board, report);
    }
    if (!viewport.supported) {
        return;
    }
    checkLocalHand(board, { floor: viewport.ownTileFloor, screen }, report);
    checkRiverGaps(board, report);
    checkStripsApart(board, report);
    BADGE_ANCHORS.keep(report, badgeAnchors(board));
    checkSettingsCog(board, screen, report);
    checkFaces(board, viewport, report);
    checkHandReach(board, report);
    checkHandScale(board, report);
    checkDerivedProportions(board, viewport.name, report);
    if (options.longNames !== true && keepsNamesWhole(viewport, screen)) {
        report.expect(
            board.cutNames.length === 0,
            `badge name(s) shortened though ordinary: ${board.cutNames.join(", ")}`,
        );
    }
}

/** The table: the storybooks of tiles and boards, dense and sparse, and the face's fallback. */
export const boardSurface: Surface = {
    checkBoard,
    checkResults: checkBadgePlaces,
    pages: PAGES,
};
