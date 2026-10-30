import { type TemplateResult, html, nothing } from "lit-html";
import { keyed } from "lit-html/directives/keyed.js";

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
import { Discards, Hand, Meld, Tile, TileBack } from "@/entities/tile";

import { type BoardNotice, BoardNotices } from "./board-notices";
import { HonbaStickIcon } from "./honba-stick-icon";
import { Nameplates, type ScoreDiffPin } from "./nameplate";
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
    /** The decision's controls (its countdown, offers and pass), in the board's own corner beside the table. */
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
    /** What the bottom seat is to play now, which the board cues along its hand: its turn, or a call prompt. */
    readonly yourMove?: "turn" | "call" | null;
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

function MeldsArea(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    return html`<div class="board-area board-melds board-area--${seat}-melds" data-area="${seat}-melds">
        ${player ? player.melds.toReversed().map((tiles) => Meld(tiles)) : ""}
    </div>`;
}

function DiscardsArea(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    return html`<div class="board-area board-river board-river--${seat}" data-area="${seat}-discards">
        ${player ? Discards(player.discards) : ""}
    </div>`;
}

/** A seat's strip: its hand, then its melds, led by its plate when the plate rides the strip (the top seat's). */
function Strip(
    seat: SeatPosition,
    player: BoardPlayerDisplay | null,
    plate: TemplateResult | typeof nothing = nothing,
): TemplateResult {
    return html`<div class="board-strip board-strip--${seat}">${plate}${HandArea(seat, player)}${MeldsArea(seat, player)}</div>`;
}

/**
 * The table's areas for a seat: its river, and for a side seat its strip in its column's slot, where the melds follow
 * the hand. The top seat's strip and the local strip are the board's own.
 */
function TableAreas(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    if (seat === "bottom" || seat === "top") {
        return DiscardsArea(seat, player);
    }
    return html`<div class="board-side board-side--${seat}">${Strip(seat, player)}</div>${DiscardsArea(seat, player)}`;
}

const DORA_SLOTS = 5;

/** The dora indicators turned so far, a back in each slot still to turn, and the table's honba and riichi sticks. */
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
                <span class="board-dora__stick">
                    <span class="board-dora__label">Honba</span>
                    <span class="board-dora__count">${HonbaStickIcon()}${center.honbaSticks}</span>
                </span>
                <span class="board-dora__stick">
                    <span class="board-dora__label">Riichi</span>
                    <span class="board-dora__count">${RiichiStickIcon()}${center.riichiSticks}</span>
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
 * The centre: each seat's wind and score on its side, its riichi stick beside them, whose turn it is, the round and
 * the wall.
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

const YOUR_MOVE_LABELS: Readonly<Record<"turn" | "call", string>> = {
    call: "Your call",
    turn: "Your turn",
};

function EmptyCenterArea(): TemplateResult {
    return html`
        <div class="board-area board-center" data-area="center"></div>
    `;
}

/**
 * The board, sized from its own box: the table (every river round the centre, the other seats' strips, each side
 * seat's plate beside its hand's start, the dora and sticks in the top-left corner, the page's own controls (`menu`)
 * in the top-right, and the decision's controls, when given, right of the table above the hand) over the local strip
 * (the bottom seat's plate, hand and melds), which spans the board's width so its tiles stay the largest on the
 * board. The top seat's plate leads its strip. A pinned plate unpins on a click anywhere else on the board or on
 * Escape. Calls show by their seats inside the table for a moment, and a win's call shows before the panel over the
 * board does.
 */
function GameBoard(props: GameBoardProps): TemplateResult {
    const { scoreDiff, state } = props;
    const boardClass = [
        "game-board",
        props.debug ? "game-board--debug" : "",
        scoreDiff.pinned === null ? "" : `game-board--diff-${scoreDiff.pinned}`,
        props.yourMove ? `game-board--your-${props.yourMove}` : "",
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
                <div class="board-table">
                    ${SEAT_POSITIONS.map((seat, i) => TableAreas(seat, state?.players[i] ?? null))}
                    ${state ? CenterInfo(state.center, state.nameplates) : EmptyCenterArea()}
                    ${state ? DoraDisplay(state.center) : ""}
                    ${plates ? html`${plates.right}${plates.left}` : ""}
                    ${Strip("top", state?.players[2] ?? null, plates?.top ?? nothing)}
                    ${props.menu ? html`<div class="board-menu">${props.menu}</div>` : ""}
                    ${props.actions ? html`<div class="board-actions" data-area="actions">${props.actions}</div>` : ""}
                    ${props.notices ? BoardNotices(props.notices) : ""}
                    ${props.callouts ? Callouts(props.callouts) : ""}
                </div>
                <div class="board-local">
                    ${props.yourMove ? html`<span class="board-cue">${YOUR_MOVE_LABELS[props.yourMove]}</span>` : ""}
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
