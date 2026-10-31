import { type TemplateResult, html, nothing } from "lit-html";
import { keyed } from "lit-html/directives/keyed.js";
import { styleMap } from "lit-html/directives/style-map.js";

import { CALLOUT_MS } from "@/entities/table/lib/callouts";
import {
    type BoardCallout,
    type BoardCallouts,
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardNameplate,
    type BoardPlayerDisplay,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import { Discards, Hand, Meld, type MeldTile, Tile, TileBack } from "@/entities/tile";

import { type BoardNotice, BoardNotices, NoticeAnnouncements } from "./board-notices";
import { HonbaStickIcon } from "./honba-stick-icon";
import { Nameplates, type PlatePress, pinnedPlate } from "./nameplate";
import { RiichiStickIcon } from "./riichi-stick-icon";

/** How the bottom seat's hand is played: what a selectable tile does and where its tap goes. */
interface LocalHandInput {
    readonly onTile: (tileId: number) => void;
    readonly tileAction: string;
}

interface GameBoardProps {
    readonly debug: boolean;
    readonly overlay?: TemplateResult;
    readonly state: BoardDisplayState | null;
    /** The decision's controls (its countdown, offers and pass), by the bottom seat's hand. */
    readonly actions?: TemplateResult;
    readonly localHand?: LocalHandInput;
    /** The notices over the table; given, even empty, the board keeps their live region for the next one. */
    readonly notices?: readonly BoardNotice[];
    /** The overlay's panel blocks the board: everything under it takes no input, by keyboard or pointer. */
    readonly inert?: boolean;
    /** What pressing a plate does: pin it to show the others' score differences, or view the table from its seat. */
    readonly platePress: PlatePress;
    /** The page's own controls (the way back, the connection), in the board's top-right corner. */
    readonly menu?: TemplateResult;
    /** The calls shown by their seats for a moment, over the table and never over the local hand; they take no input. */
    readonly callouts?: BoardCallouts | null;
    /** Each new showing of calls is read out once, by its seats' names (a live board's). */
    readonly announceCalls?: boolean;
    /** The overlay's panel is a round's result, which waits until a win's call has been seen; any other shows at once. */
    readonly overlayIsResult?: boolean;
    /** The bottom seat is furiten: its mark shows in the slot by the hand that a played board keeps for it. */
    readonly furiten?: boolean;
    /** The play switches, in their slot on the foreground band's side away from the decisions. */
    readonly switches?: TemplateResult;
    /**
     * A replay's controls, over the foreground band in the switches' and the decisions' places (a board that shows
     * them plays no hand), and what it shows in the notices' place under any notice (its position).
     */
    readonly replay?: { readonly controls: TemplateResult; readonly status: TemplateResult };
    /**
     * What Escape does once no badge is pinned (stepping back from a decision's step), given the board; none when it
     * does nothing. An Escape something on the board already took (a panel's) is left alone.
     */
    readonly onEscape?: (board: HTMLElement) => void;
}

function HandArea(
    seat: SeatPosition,
    player: BoardPlayerDisplay | null,
    input?: LocalHandInput,
): TemplateResult {
    return html`<div class="board-area board-area--${seat}-hand" data-area="${seat}-hand">
        ${player ? Hand({ drawnTile: player.drawnTile, tiles: player.hand, ...input }) : ""}
    </div>`;
}

/**
 * A seat's melds, newest first from the hand outward, so the first meld lies farthest right; the one an offer refers to
 * marked as its source.
 */
function MeldsArea(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    const melds = player?.melds ?? [];
    return html`<div class="board-area board-melds board-area--${seat}-melds" data-area="${seat}-melds">
        ${melds.toReversed().map((tiles, index) => Meld(tiles, melds.length - 1 - index === player?.sourceMeld))}
    </div>`;
}

/** A seat's river, in its frame turned to the seat; a side river wraps past its third row, a top or bottom one runs on. */
function River(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    const overflow = seat === "left" || seat === "right" ? "wrap" : "run-on";
    return html`<div class="board-area board-river board-river--${seat}" data-area="${seat}-discards">
        ${player ? Discards(player.discards, overflow) : ""}${LatestMark(seat, player)}
    </div>`;
}

/**
 * The latest discard's ring and pointer, laid over its slot beside the river's tiles rather than among them, so the
 * tiles' shared edge and shadow never extrude them: its column and row, and whether it or a tile before it on its row
 * lies sideways.
 */
function LatestMark(
    seat: SeatPosition,
    player: BoardPlayerDisplay | null,
): TemplateResult | typeof nothing {
    const latest = latestSlot(seat, player);
    if (latest === null || player === null) {
        return nothing;
    }
    const rowStart = latest.row * RIVER_ROW;
    const index = rowStart + latest.col;
    const wideBefore = player.discards.slice(rowStart, index).some((tile) => tile.riichi === true);
    const wide = player.discards[index]?.riichi === true;
    return html`<span
        class="board-river__latest"
        style="--latest-col: ${latest.col}; --latest-row: ${latest.row}; --latest-wide-before: ${Number(wideBefore)}; --latest-wide: ${Number(wide)}"
        aria-hidden="true"
    ></span>`;
}

const STRIP_SEATS: readonly SeatPosition[] = ["right", "top", "left"];
const MAX_MELDS = 4;
const SIDEWAYS_UNITS = 4 / 3;
const UPRIGHT_DEPTH = 4 / 3;
const STACKED_DEPTH = 2;

/** How long a laid meld is, in its tiles' widths: a sideways or stacked tile lies as long as a tile is tall. */
function meldUnits(tiles: readonly MeldTile[]): number {
    return tiles.reduce(
        (sum, tile) =>
            sum + (tile.kind === "sideways" || tile.kind === "stacked" ? SIDEWAYS_UNITS : 1),
        0,
    );
}

/** How deep a laid meld stands from its seat's edge, in its tiles' widths: an added kan's stack is two tiles deep. */
function meldDepth(tiles: readonly MeldTile[]): number {
    return tiles.some((tile) => tile.kind === "stacked") ? STACKED_DEPTH : UPRIGHT_DEPTH;
}

/** How far past every place a missing meld's end is pushed, so it never counts as overflowing its line. */
const ABSENT_MELD = "99999px";

/**
 * What a strip's stylesheet places its tiles from: how many tiles its hand holds and whether one is drawn apart, and
 * its melds newest first: how long they are before each and from each on, and the deepest, so a side strip can tell
 * which melds fit its line.
 */
function stripStyle(player: BoardPlayerDisplay | null): Readonly<Record<string, string>> {
    const melds = (player?.melds ?? []).toReversed();
    const units = melds.map(meldUnits);
    const drawn = player?.drawnTile === undefined ? 0 : 1;
    const deepest = Math.max(UPRIGHT_DEPTH, ...melds.map(meldDepth));
    function sum(from: number, to: number): number {
        return units.slice(from, to).reduce((total, unit) => total + unit, 0);
    }
    const perMeld = Array.from({ length: MAX_MELDS }, (_unused, index) => [
        [`--mp-${index}`, String(sum(0, index))],
        [`--ms-${index}`, String(Math.max(1, sum(index, MAX_MELDS)))],
        [`--mg-${index}`, index < melds.length ? "0px" : ABSENT_MELD],
    ]).flat();
    return Object.fromEntries([
        ["--hand-n", String((player?.hand.length ?? 0) + drawn)],
        ["--drawn", String(drawn)],
        ["--meld-n", String(melds.length)],
        ["--meld-units", String(sum(0, MAX_MELDS))],
        [`--mp-${MAX_MELDS}`, String(sum(0, MAX_MELDS))],
        ["--meld-deep", String(deepest)],
        ...perMeld,
    ]);
}

/**
 * What the places beside a side strip read of it (the decisions, the replay's options and an upright board's notices
 * beside the right strip, the notices beside the left), handed to the table holding them all: its hand's and melds'
 * lengths, its deepest meld and its oldest, which a second line of its melds starts with, so a place stays clear of
 * that line.
 */
function sideStripStyle(
    side: "left" | "right",
    player: BoardPlayerDisplay | null,
): Readonly<Record<string, string>> {
    const style = stripStyle(player);
    const oldest = player?.melds[0];
    return Object.fromEntries([
        ...["--hand-n", "--drawn", "--meld-n", "--meld-units", "--meld-deep"].map((name) => [
            `--${side}${name.slice(1)}`,
            style[name],
        ]),
        [`--${side}-oldest-deep`, String(oldest === undefined ? 0 : meldDepth(oldest))],
    ]);
}

function seatPlayer(
    state: BoardDisplayState | null,
    seat: SeatPosition,
): BoardPlayerDisplay | null {
    return state?.players[SEAT_POSITIONS.indexOf(seat)] ?? null;
}

/** What the own row's melds scale from to end before the board's edge: how many there are and how long, in tiles. */
function ownMeldStyle(player: BoardPlayerDisplay | null): Readonly<Record<string, string>> {
    const style = stripStyle(player);
    return { "--meld-n": style["--meld-n"], "--meld-units": style["--meld-units"] };
}

/** An opponent's strip in its zone toward its edge: its hand, then its melds beyond the hand's right end. */
function Strip(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    return html`<div class="board-strip board-strip--${seat}" style=${styleMap(stripStyle(player))}>
        ${HandArea(seat, player)}${MeldsArea(seat, player)}
    </div>`;
}

/** The faint lines from the centre's corners and the side fields' tint that make the four zones perceptible. */
function Zones(): TemplateResult {
    return html`<div class="board-zones" aria-hidden="true">
        <span class="board-zones__field board-zones__field--left"></span>
        <span class="board-zones__field board-zones__field--right"></span>
        <span class="board-zones__field board-zones__field--top"></span>
        <span class="board-zones__line board-zones__line--top-left"></span>
        <span class="board-zones__line board-zones__line--top-right"></span>
        <span class="board-zones__line board-zones__line--bottom-right"></span>
        <span class="board-zones__line board-zones__line--bottom-left"></span>
    </div>`;
}

const DORA_SLOTS = 5;

/**
 * The pooled counters: the dora indicators turned so far, a back in each slot still to turn, and the table's honba and
 * riichi sticks as icon and number, which the centre does not repeat.
 */
function DoraDisplay(center: BoardCenterInfo): TemplateResult {
    const indicators = center.doraIndicators;
    const backs = Math.max(0, DORA_SLOTS - indicators.length);
    return html`
        <div class="board-dora">
            <div class="board-dora__tiles" role="group" aria-label="Dora indicators">
                ${indicators.map((face) => html`<span class="board-dora__tile">${Tile(face, "face")}</span>`)}
                ${Array.from({ length: backs }, () => html`<span class="board-dora__tile">${TileBack()}</span>`)}
            </div>
            <div class="board-dora__sticks">
                <span class="board-dora__stick" title="Honba">
                    ${HonbaStickIcon()}<span class="board-dora__label">Honba </span
                    ><span class="board-dora__count">${center.honbaSticks}</span>
                </span>
                <span class="board-dora__stick" title="Riichi sticks on the table">
                    ${RiichiStickIcon()}<span class="board-dora__label">Riichi sticks </span
                    ><span class="board-dora__count">${center.riichiSticks}</span>
                </span>
            </div>
        </div>
    `;
}

/**
 * A seat's side of the centre, turned to face it: its wind (the dealer's marked) and score, or while a plate is hovered
 * or pinned its difference from that plate's seat, and above them its riichi stick once its riichi stands. A bar
 * along its edge marks whose turn it is. Where pressing a plate views from its seat, so does a pointer's press of
 * another seat's score; the keyboard's is the plate's.
 */
function CenterSeat(
    plate: BoardNameplate,
    position: SeatPosition,
    onView: ((seat: SeatPosition) => void) | null,
): TemplateResult {
    const classes = [
        "board-center__seat",
        `board-center__seat--${position}`,
        plate.isCurrent ? "board-center__seat--current" : "",
        plate.isDealer ? "board-center__seat--dealer" : "",
    ]
        .filter(Boolean)
        .join(" ");
    const diffs = SEAT_POSITIONS.filter((other) => other !== position).map(
        (other) =>
            html`<span class="board-center__diff board-center__diff--${other}">${plate.scoreDiffs[other]}</span>`,
    );
    const viewable = onView !== null && position !== "bottom";
    return html`<div class=${classes}>
        <span class="board-center__riichi ${plate.isRiichi ? "" : "board-center__riichi--none"}"></span>
        <span
            class="board-center__score-line ${viewable ? "board-center__score-line--view" : ""}"
            title=${viewable ? `View from ${plate.name}` : nothing}
            @click=${viewable ? () => onView(position) : nothing}
            ><span class="board-center__wind">${plate.wind}</span
            ><span class="board-center__score">${plate.score}</span>${diffs}</span
        >
    </div>`;
}

/**
 * While a badge's differences show, the label naming whose they are, beside the wall's count, which stays: one per
 * seat, which the board's stylesheet shows for the hovered or pinned badge, naming the seat whole where its name fits
 * the line, else by its wind, which assistive technology skips for the whole name.
 */
function DiffLabels(plates: BoardDisplayState["nameplates"]): TemplateResult {
    return html`${SEAT_POSITIONS.map(
        (position, index) =>
            html`<div class="board-center__diff-label board-center__diff-label--${position}">
                <span class="board-center__diff-vs">vs</span>
                <span class="board-center__diff-slot"
                    ><span class="board-center__diff-names"
                        ><span class="board-center__diff-name">${plates[index].name}</span
                        ><span class="board-center__diff-wind" aria-hidden="true">${plates[index].windName}</span></span
                    ></span
                >
            </div>`,
    )}`;
}

/**
 * The centre: each seat's wind and score on its side, its riichi stick inside the edge, the turn's bar on it, and in
 * its middle the round and the wall's count.
 */
function CenterInfo(
    center: BoardCenterInfo,
    plates: BoardDisplayState["nameplates"],
    press: PlatePress,
): TemplateResult {
    const onView = press.kind === "view" ? press.onView : null;
    return html`
        <div class="board-area board-center" data-area="center">
            ${SEAT_POSITIONS.map((position, index) => CenterSeat(plates[index], position, onView))}
            <div class="board-center__info">
                <div class="board-center__round">${center.roundDisplay}</div>
                <div class="board-center__wall">
                    <span class="board-center__wall-label">Wall</span>
                    <span class="board-center__wall-count">${center.tilesRemaining}</span>
                </div>
                ${DiffLabels(plates)}
            </div>
        </div>
    `;
}

const RIVER_ROW = 6;

/**
 * Where a call's chip may lie in its caller's river, in the river's frame (along its rows in river tiles, away from the
 * centre in river rows), first choice first: a top or bottom river's chip lies along one row, a side river's, upright,
 * across every row over two columns.
 */
const CALLOUT_SPOTS: Readonly<Record<SeatPosition, readonly (readonly [number, number])[]>> = {
    bottom: [
        [3, 1.5],
        [3, 0.5],
        [3, 2.5],
    ],
    left: [
        [3, 2],
        [1, 2],
        [5, 2],
    ],
    right: [
        [3, 2],
        [1, 2],
        [5, 2],
    ],
    top: [
        [3, 2.5],
        [3, 1.5],
        [3, 0.5],
    ],
};

/** The latest discard's place in a river, its column along its row and its row, or null when it lies elsewhere. */
function latestSlot(
    seat: SeatPosition,
    player: BoardPlayerDisplay | null,
): { col: number; row: number } | null {
    const index = player?.discards.findIndex((tile) => tile.last === true) ?? -1;
    if (index === -1) {
        return null;
    }
    const lastRow = seat === "left" || seat === "right" ? 3 : 2;
    const row = Math.min(lastRow, Math.floor(index / RIVER_ROW));
    return { col: index - row * RIVER_ROW, row };
}

/**
 * The first spot for a call's chip over its caller's river that leaves the latest discard, the action source, in view:
 * a top or bottom chip off the latest discard's row, a side chip off its column pair.
 */
function calloutSpot(
    seat: SeatPosition,
    player: BoardPlayerDisplay | null,
): readonly [number, number] {
    const spots = CALLOUT_SPOTS[seat];
    const latest = latestSlot(seat, player);
    const side = seat === "left" || seat === "right";
    const clear = spots.find(([along, across]) => {
        if (latest === null) {
            return true;
        }
        return side
            ? latest.col < along - 1 || latest.col >= along + 1
            : latest.row !== Math.floor(across);
    });
    return clear ?? spots[0];
}

function Callout(
    { kind, label, position }: BoardCallout,
    players: BoardDisplayState["players"] | null,
): TemplateResult {
    const [along, across] = calloutSpot(
        position,
        players?.[SEAT_POSITIONS.indexOf(position)] ?? null,
    );
    return html`<div
        class="board-callout board-callout--${position} board-callout--${kind}"
        style="--spot-along: ${along}; --spot-across: ${across}"
    >
        <span class="board-callout__word">${label}</span>
    </div>`;
}

/**
 * The calls by their seats, each over its caller's river clear of the latest discard; a new showing (a new key) is
 * drawn afresh, so its animation plays from the start, over the time a live call shows.
 */
function Callouts(callouts: BoardCallouts, state: BoardDisplayState | null): TemplateResult {
    const players = state?.players ?? null;
    return html`${keyed(
        callouts.key,
        html`<div class="board-callouts" style="--callout-ms: ${CALLOUT_MS}ms" aria-hidden="true">${callouts.items.map(
            (item) => Callout(item, players),
        )}</div>`,
    )}`;
}

/** What a showing of calls reads out: each caller's name and call, `Bob: Pon`. */
function calloutWords(callouts: BoardCallouts, state: BoardDisplayState | null): string {
    return callouts.items
        .map(({ label, position }) => {
            const name = state?.nameplates[SEAT_POSITIONS.indexOf(position)].name;
            return name === undefined ? label : `${name}: ${label}`;
        })
        .join(", ");
}

/** The calls as a polite live region of their own, each showing read once: a new showing is a new key, a redraw none. */
function CalloutAnnouncements(
    callouts: BoardCallouts | null | undefined,
    state: BoardDisplayState | null,
): TemplateResult {
    return html`<div
        class="board-announce board-announce--calls"
        aria-live="polite"
        aria-atomic="false"
        aria-relevant="additions"
    >${
        callouts ? keyed(callouts.key, html`<p>${calloutWords(callouts, state)}</p>`) : nothing
    }</div>`;
}

/** The furiten mark's slot by the hand, kept on a played board so the hand never moves: a dot and the word. */
function FuritenSlot(furiten: boolean): TemplateResult {
    return html`<span class="board-furiten" title=${furiten ? "Furiten: you cannot win on a discard" : nothing}
        >${
            furiten
                ? html`<span class="board-furiten__dot" aria-hidden="true"></span
                      ><span class="board-furiten__word">Furiten</span>`
                : ""
        }</span
    >`;
}

/** Whether the calls shown are a win's (ron, tsumo), whose result panel waits until they have been seen. */
function callsAWin(callouts: BoardCallouts | null | undefined): boolean {
    return callouts?.items.some((item) => item.kind === "ron" || item.kind === "tsumo") ?? false;
}

function EmptyCenterArea(): TemplateResult {
    return html`
        <div class="board-area board-center" data-area="center"></div>
    `;
}

/**
 * The board, sized from its own box (docs/game-client-look.md, Composition): the core of the centre and the four
 * rivers in their pinwheel, the other seats' strips and badges in their zones toward the edges, the pooled counters in
 * the top-left corner and the page's own controls (`menu`) in the top-right, and over the foreground band the bottom
 * seat's badge, hand and melds with the decision's controls and the play switches, when given, by the hand; a board
 * the viewer plays (`localHand`) also keeps the furiten mark's slot beside the hand. A pinned badge unpins on a click anywhere else on
 * the board or on Escape (a replay's badges pin nothing: pressing one, or another seat's score, views from its seat); with none pinned, Escape steps back from a decision's step. Calls show over their seats' rivers for a
 * moment, clear of the latest discard, and a win's call shows before the panel over the board does.
 */
function GameBoard(props: GameBoardProps): TemplateResult {
    const { platePress, state } = props;
    const pinned = pinnedPlate(platePress);
    const boardClass = [
        "game-board",
        props.localHand ? "game-board--play" : "",
        props.replay ? "game-board--replay" : "",
        props.debug ? "game-board--debug" : "",
        pinned === null ? "" : `game-board--diff-${pinned}`,
    ]
        .filter(Boolean)
        .join(" ");
    const bottom = state?.players[0] ?? null;
    const plates = state ? Nameplates(state.nameplates, platePress) : null;
    function unpinOnClickElsewhere(event: MouseEvent): void {
        const { target } = event;
        const onPlate = target instanceof Element && target.closest(".nameplate") !== null;
        if (platePress.kind === "pin" && pinned !== null && !onPlate) {
            platePress.onPin(null);
        }
    }
    function onKey(event: KeyboardEvent): void {
        if (event.key !== "Escape" || event.defaultPrevented) {
            return;
        }
        if (platePress.kind === "pin" && pinned !== null) {
            platePress.onPin(null);
            return;
        }
        if (event.currentTarget instanceof HTMLElement) {
            props.onEscape?.(event.currentTarget);
        }
    }

    return html`
        <div class="${boardClass}" @click=${unpinOnClickElsewhere} @keydown=${onKey}>
            <div class="board-layout" ?inert=${props.inert ?? false}>
                ${Zones()}
                <div class="board-table" style=${styleMap({ ...sideStripStyle("left", seatPlayer(state, "left")), ...sideStripStyle("right", seatPlayer(state, "right")) })}>
                    ${SEAT_POSITIONS.map((seat, i) => River(seat, state?.players[i] ?? null))}
                    ${state ? CenterInfo(state.center, state.nameplates, platePress) : EmptyCenterArea()}
                    ${STRIP_SEATS.map((seat) => Strip(seat, state?.players[SEAT_POSITIONS.indexOf(seat)] ?? null))}
                    ${state ? DoraDisplay(state.center) : ""}
                    ${plates ? html`${plates.right}${plates.top}${plates.left}` : ""}
                    ${props.menu ? html`<div class="board-menu">${props.menu}</div>` : ""}
                    ${props.actions ? html`<div class="board-actions" data-area="actions">${props.actions}</div>` : ""}
                    ${props.switches ?? ""}
                    ${props.replay ? html`<div class="board-replay">${props.replay.controls}</div>` : ""}
                    ${props.notices || props.replay ? BoardNotices(props.notices ?? [], props.replay?.status) : ""}
                    ${props.callouts ? Callouts(props.callouts, state) : ""}
                </div>
                <div class="board-local" style=${styleMap(ownMeldStyle(bottom))}>
                    ${plates?.bottom ?? ""}${props.localHand ? FuritenSlot(props.furiten ?? false) : ""}${HandArea("bottom", bottom, props.localHand)}${MeldsArea("bottom", bottom)}
                </div>
            </div>
            ${props.notices ? NoticeAnnouncements(props.notices) : ""}
            ${props.announceCalls === true ? CalloutAnnouncements(props.callouts, state) : ""}
            ${
                props.overlay
                    ? html`<div class="board-overlay ${props.overlayIsResult === true && callsAWin(props.callouts) ? "board-overlay--after-call" : ""}">
                      <div class="board-overlay__panel">${props.overlay}</div>
                  </div>`
                    : ""
            }
        </div>
    `;
}

export { GameBoard };
export type { GameBoardProps, LocalHandInput };
