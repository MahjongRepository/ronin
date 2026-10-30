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
    longSide,
    near,
} from "../boxes.ts";
import { ACTION, boardCase, decisionCase, documentCase } from "../cases.ts";
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
    LAPTOPS,
    LARGE_DESKTOP,
    NARROW_DESKTOP,
    SHORT_DESKTOP,
    WIDER_PHONES,
} from "../viewports.ts";

/** The smallest face-up tile of another seat's hand or melds in landscape, in CSS pixels: readable at a glance. */
const MIN_OPPONENT_FACE: Size = { height: 17, width: 13 };

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

const PAGES: readonly PageCase[] = [
    documentCase("storybook", "/play/storybook", ".storybook .tile"),
    documentCase("storybook-hand", "/play/storybook/hand", ".storybook .hand .tile"),
    documentCase("storybook-discards", "/play/storybook/discards", ".storybook .discards .tile"),
    documentCase("storybook-melds", "/play/storybook/melds", ".storybook .meld .tile"),
    boardCase("board-full-rivers", "?state=full_rivers"),
    {
        ...boardCase("board-callouts-riichi", "?state=worst&callout=riichi", [".board-callout"]),
        longNames: true,
    },
    boardCase("board-callouts-tsumo", "?state=full_rivers&callout=tsumo", [".board-callout"]),
    {
        ...boardCase("board-callouts-adjacent", "?state=riichi_latest&callout=riichi&offers=five", [
            ".board-callout",
            ".discard-tile--last.discard-tile-riichi",
            ACTION,
        ]),
        alsoAt: [SHORT_DESKTOP],
    },
    {
        ...boardCase("board-worst", "?state=worst&pin=right", [
            ".board-strip .meld",
            ".board-dora .tile",
            ".board-center__seat--left .board-center__diff--right",
            ".nameplate__ai",
        ]),
        alsoAt: [SHORT_DESKTOP, NARROW_DESKTOP, ...WIDER_PHONES],
        contrast: true,
        longNames: true,
    },
    {
        ...boardCase("board-worst-offers", "?state=worst&offers=five", [
            ACTION,
            ".board-strip .meld",
        ]),
        alsoAt: [NARROW_DESKTOP, ...LAPTOPS, LARGE_DESKTOP, ...WIDER_PHONES],
        longNames: true,
    },
    {
        ...boardCase("board-full-hands", "?state=full_hands&offers=five", [ACTION]),
        alsoAt: [SHORT_DESKTOP, NARROW_DESKTOP, ...LAPTOPS, LARGE_DESKTOP, ...WIDER_PHONES],
    },
    {
        ...boardCase("board-full-hands-riichi", "?state=full_hands&offers=riichi", [
            `${ACTION}[aria-pressed="true"]`,
            ".decision-controls__bank",
        ]),
        alsoAt: [SHORT_DESKTOP, ...LAPTOPS, LARGE_DESKTOP, ...WIDER_PHONES],
    },
    { ...boardCase("board-concealed-hands", "?state=concealed_hands"), alsoAt: [SHORT_DESKTOP] },
    {
        ...boardCase("board-mixed-hands-a", "?state=mixed_hands_a", [".board-strip .meld"]),
        alsoAt: [SHORT_DESKTOP, ...WIDER_PHONES],
    },
    {
        ...boardCase("board-mixed-hands-b", "?state=mixed_hands_b", [".board-strip .meld"]),
        alsoAt: [SHORT_DESKTOP, ...WIDER_PHONES],
    },
    {
        ...boardCase("board-mixed-hands-c", "?state=mixed_hands_c", [".board-strip .meld"]),
        alsoAt: [SHORT_DESKTOP, NARROW_DESKTOP, ...LAPTOPS, ...WIDER_PHONES],
    },
    {
        ...decisionCase("anchor_turn", [".hand-tile--selectable", ".decision-controls__countdown"]),
        fontBlocked: true,
        name: "font-blocked-anchor-turn",
        onlyAt: ["desktop-1440", "phone-se-landscape"],
    },
];

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
    const overlaps = findOverlaps(board.grouped);
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
 * The board stays on the page: on the scrollable page upright, else on the screen, and the aside beside it on the
 * screen, or on the page where a storybook's switches lie below the board.
 */
function checkPlacement(
    board: BoardMeasure,
    {
        measure,
        screen,
        viewport,
    }: { readonly measure: PageMeasure; readonly screen: Box; readonly viewport: Viewport },
    report: PageReport,
): void {
    const pageExtent = { height: measure.scrollHeight, left: 0, top: 0, width: measure.innerWidth };
    if (viewport.portrait) {
        report.expect(
            contains(pageExtent, board.board),
            "the board is outside the scrollable page",
        );
        checkAside(board, pageExtent, report);
        return;
    }
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
 * tiles are the board's largest: larger than any river, other seat's hand or meld, or dora tile.
 */
function checkLocalHand(
    board: BoardMeasure,
    { floor, screen }: { readonly floor: Size | undefined; readonly screen: Box },
    report: PageReport,
): void {
    const hidden = board.localTiles.filter((tile) => !contains(screen, tile));
    report.expect(hidden.length === 0, `${hidden.length} local hand tile(s) outside the viewport`);
    if (floor !== undefined) {
        const small = board.localTiles.filter(
            (tile) => tile.width < floor.width - EPSILON || tile.height < floor.height - EPSILON,
        );
        report.expect(
            small.length === 0,
            `local hand tiles under ${describeSize(floor)}: ${small.map(describeBox).join(", ")}`,
        );
    }
    const smallestOwn = Math.min(...board.localTiles.map(longSide));
    const largestOther = Math.max(0, ...board.otherTiles.map(longSide));
    report.expect(
        smallestOwn > largestOther + EPSILON,
        `a local hand tile (${smallestOwn.toFixed(1)}px) is no larger than another tile on the board (${largestOther.toFixed(1)}px)`,
    );
}

/**
 * A side strip's full hand, as its place reserves it whatever the seat holds, stays clear of the play switches, the
 * page's corner and the decision's controls and timer: a full concealed hand is the strips' binding capacity.
 */
function checkHandReach(board: BoardMeasure, report: PageReport): void {
    const controls = [
        ...board.switches.map((control) => control.box),
        ...board.menu,
        ...board.actions,
        ...(board.timer === null ? [] : [board.timer]),
    ];
    const unread = board.handReach.filter(
        (reach) => !Number.isFinite(reach.box.width) || !Number.isFinite(reach.box.height),
    );
    report.expect(
        unread.length === 0,
        `a side hand's full reach could not be read (--full-reach, --bh): ${unread.map((reach) => reach.group).join(", ")}`,
    );
    const crowded = board.handReach.filter((reach) =>
        controls.some((control) => intersects(reach.box, control)),
    );
    report.expect(
        crowded.length === 0,
        `a side hand's full reach meets a switch, the page's corner or a decision control: ${crowded.map((reach) => `${reach.group} ${describeBox(reach.box)}`).join(", ")}`,
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

/** Another seat's face-up tiles stay readable in landscape. */
function checkOpponentFaces(board: BoardMeasure, report: PageReport): void {
    const small = board.opponentFaces.filter(
        (tile) =>
            Math.min(tile.width, tile.height) < MIN_OPPONENT_FACE.width - EPSILON ||
            longSide(tile) < MIN_OPPONENT_FACE.height - EPSILON,
    );
    report.expect(
        small.length === 0,
        `face-up tiles of other seats under ${describeSize(MIN_OPPONENT_FACE)}: ${small.slice(0, 3).map(describeBox).join(", ")}`,
    );
}

/** The page's way back sits on the board and the screen, large enough to tap. */
function checkLeave(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { leave } = board;
    if (leave === null) {
        return;
    }
    report.expect(
        contains(board.board, leave) && contains(screen, leave),
        `the leave button ${describeBox(leave)} is off the board or screen`,
    );
    report.expect(
        leave.width >= MIN_ACTION_SIZE - EPSILON && leave.height >= MIN_ACTION_SIZE - EPSILON,
        `the leave button is under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${describeBox(leave)}`,
    );
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

/** Each badge's fixed point: the side of its box toward its seat's edge, and its top (the own badge's foot). */
function badgeAnchors(board: BoardMeasure): Readonly<Record<string, readonly [number, number]>> {
    return Object.fromEntries(
        board.badges.map(({ box, group }) => {
            const right = box.left + box.width;
            const bottom = box.top + box.height;
            const point: readonly [number, number] =
                group === "right"
                    ? [right, box.top]
                    : [box.left, group === "bottom" ? bottom : box.top];
            return [group, point];
        }),
    );
}

/**
 * A call shown by its seat stays on the board and never lies over the local hand's tiles, which take the taps, over a
 * decision control or the timer, or over what an open offer refers to (the latest discard, a kan a chankan may rob).
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
    const overSource = board.callouts.filter((callout) =>
        board.actionSources.some((source) => intersects(callout, source)),
    );
    report.expect(
        overSource.length === 0,
        `call(s) over the latest discard or an offered kan: ${overSource.map(describeBox).join(", ")}`,
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

/**
 * The board as a whole: its content inside its box and readable, the table's surface clear of the aside, the board on
 * the page, and in landscape on a supported screen the own hand, the rivers' and strips' gaps, the badges, the page's
 * corner and the side hands' reserved reach.
 */
function checkBoard({ board, measure, options, report, screen, viewport }: BoardRun): void {
    checkBoardContent(board, report);
    report.expect(
        board.aside === null || board.zones === null || !intersects(board.zones, board.aside.box),
        `the table's surface ${board.zones === null ? "" : describeBox(board.zones)} reaches under the aside`,
    );
    if (viewport.supported) {
        const crowded = findOverlaps(board.centerTexts);
        report.expect(crowded.length === 0, `centre pieces overlap: ${crowded.join(", ")}`);
    }
    checkCallouts(board, report);
    checkPlacement(board, { measure, screen, viewport }, report);
    if (!viewport.supported || viewport.portrait) {
        return;
    }
    checkLocalHand(board, { floor: viewport.ownTileFloor, screen }, report);
    checkRiverGaps(board, report);
    checkStripsApart(board, report);
    BADGE_ANCHORS.keep(report, badgeAnchors(board));
    checkLeave(board, screen, report);
    checkOpponentFaces(board, report);
    checkHandReach(board, report);
    checkHandScale(board, report);
    if (options.longNames !== true) {
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
