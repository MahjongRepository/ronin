import { type TemplateResult, html } from "lit-html";
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

import { type BoardNotice, BoardNotices } from "./board-notices";
import { HonbaStickIcon } from "./honba-stick-icon";
import { Nameplates, type ScoreDiffPin } from "./nameplate";
import { PlayerName } from "./player-name";
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
    /** The nameplate pinned to show the others' score differences, and where pressing a plate goes. */
    readonly scoreDiff: ScoreDiffPin;
    /** The page's own controls (the way back, the connection), in the board's top-right corner. */
    readonly menu?: TemplateResult;
    /** The calls shown by their seats for a moment, over the table and never over the local hand; they take no input. */
    readonly callouts?: BoardCallouts | null;
    /** The overlay's panel is a round's result, which waits until a win's call has been seen; any other shows at once. */
    readonly overlayIsResult?: boolean;
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

/** A seat's melds, newest first from the hand outward, so the first meld lies farthest right. */
function MeldsArea(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    return html`<div class="board-area board-melds board-area--${seat}-melds" data-area="${seat}-melds">
        ${player ? player.melds.toReversed().map((tiles) => Meld(tiles)) : ""}
    </div>`;
}

/** A seat's river, in its frame turned to the seat; a side river wraps past its third row, a top or bottom one runs on. */
function River(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    const overflow = seat === "left" || seat === "right" ? "wrap" : "run-on";
    return html`<div class="board-area board-river board-river--${seat}" data-area="${seat}-discards">
        ${player ? Discards(player.discards, overflow) : ""}
    </div>`;
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
 * along its edge marks whose turn it is.
 */
function CenterSeat(plate: BoardNameplate, position: SeatPosition): TemplateResult {
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
    return html`<div class=${classes}>
        <span class="board-center__riichi ${plate.isRiichi ? "" : "board-center__riichi--none"}"></span>
        <span class="board-center__score-line"
            ><span class="board-center__wind">${plate.wind}</span
            ><span class="board-center__score">${plate.score}</span>${diffs}</span
        >
    </div>`;
}

/**
 * While a badge's differences show, the label naming whose they are, beside the wall's count, which stays: one per
 * seat, which the board's stylesheet shows for the hovered or pinned badge.
 */
function DiffLabels(plates: BoardDisplayState["nameplates"]): TemplateResult {
    return html`${SEAT_POSITIONS.map(
        (position, index) =>
            html`<div class="board-center__diff-label board-center__diff-label--${position}">
                vs ${PlayerName(plates[index].name, "board-center__diff-name")}
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
): TemplateResult {
    return html`
        <div class="board-area board-center" data-area="center">
            ${SEAT_POSITIONS.map((position, index) => CenterSeat(plates[index], position))}
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

function Callout({ kind, label, position }: BoardCallout): TemplateResult {
    return html`<div class="board-callout board-callout--${position} board-callout--${kind}">
        <span class="board-callout__word">${label}</span>
    </div>`;
}

/**
 * The calls by their seats; a new showing (a new key) is drawn afresh, so its animation plays from the start, over the
 * time a live call shows.
 */
function Callouts(callouts: BoardCallouts): TemplateResult {
    return html`${keyed(
        callouts.key,
        html`<div class="board-callouts" style="--callout-ms: ${CALLOUT_MS}ms">${callouts.items.map(Callout)}</div>`,
    )}`;
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
 * seat's badge, hand and melds with the decision's controls, when given, by the hand; a board the viewer plays
 * (`localHand`) also keeps the furiten's slot beside the hand. A pinned badge unpins on a click anywhere else on the
 * board or on Escape. Calls show over their seats' rivers for a moment, and a win's call shows before the panel over
 * the board does.
 */
function GameBoard(props: GameBoardProps): TemplateResult {
    const { scoreDiff, state } = props;
    const boardClass = [
        "game-board",
        props.localHand ? "game-board--play" : "",
        props.debug ? "game-board--debug" : "",
        scoreDiff.pinned === null ? "" : `game-board--diff-${scoreDiff.pinned}`,
    ]
        .filter(Boolean)
        .join(" ");
    const bottom = state?.players[0] ?? null;
    const plates = state ? Nameplates(state.nameplates, scoreDiff) : null;
    function unpinOnClickElsewhere(event: MouseEvent): void {
        const { target } = event;
        const onPlate = target instanceof Element && target.closest(".nameplate") !== null;
        if (scoreDiff.pinned !== null && !onPlate) {
            scoreDiff.onPin(null);
        }
    }
    function unpinOnEscape(event: KeyboardEvent): void {
        if (event.key === "Escape" && scoreDiff.pinned !== null) {
            scoreDiff.onPin(null);
        }
    }

    return html`
        <div class="${boardClass}" @click=${unpinOnClickElsewhere} @keydown=${unpinOnEscape}>
            <div class="board-layout" ?inert=${props.inert ?? false}>
                ${Zones()}
                <div class="board-table">
                    ${SEAT_POSITIONS.map((seat, i) => River(seat, state?.players[i] ?? null))}
                    ${state ? CenterInfo(state.center, state.nameplates) : EmptyCenterArea()}
                    ${STRIP_SEATS.map((seat) => Strip(seat, state?.players[SEAT_POSITIONS.indexOf(seat)] ?? null))}
                    ${state ? DoraDisplay(state.center) : ""}
                    ${plates ? html`${plates.right}${plates.top}${plates.left}` : ""}
                    ${props.menu ? html`<div class="board-menu">${props.menu}</div>` : ""}
                    ${props.actions ? html`<div class="board-actions" data-area="actions">${props.actions}</div>` : ""}
                    ${props.notices ? BoardNotices(props.notices) : ""}
                    ${props.callouts ? Callouts(props.callouts) : ""}
                </div>
                <div class="board-local">
                    ${plates?.bottom ?? ""}${HandArea("bottom", bottom, props.localHand)}${MeldsArea("bottom", bottom)}
                </div>
            </div>
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
