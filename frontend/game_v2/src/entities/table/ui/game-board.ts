import { type TemplateResult, html } from "lit-html";

import {
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardNameplate,
    type BoardPlayerDisplay,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import { Discards, Hand, Meld, Tile, type TileFace } from "@/entities/tile";

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
    return html`<div class="board-area board-area--${seat}-disc" data-area="${seat}-discards">
        ${player ? Discards(player.discards) : ""}
    </div>`;
}

/**
 * The table's areas for a seat: its river, and for another seat its strip along its edge, where the melds share the
 * hand's track at its right; the bottom seat's hand and melds sit in the local strip instead.
 */
function TableAreas(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    if (seat === "bottom") {
        return DiscardsArea(seat, player);
    }
    return html`<div class="board-strip board-strip--${seat}">
            ${HandArea(seat, player)}${MeldsArea(seat, player)}
        </div>
        ${DiscardsArea(seat, player)}`;
}

/** The seat's riichi stick laid on the table on its side of the centre, once its riichi stands. */
function RiichiStick(plate: BoardNameplate, position: SeatPosition): TemplateResult {
    if (!plate.isRiichi) {
        return html``;
    }
    return html`<span class="board-center__riichi-stick board-center__riichi-stick--${position}">${RiichiStickIcon()}</span>`;
}

function DoraDisplay(indicators: readonly TileFace[]): TemplateResult {
    if (indicators.length === 0) {
        return html``;
    }
    return html`
        <div class="board-dora">
            <span class="board-dora__label">DORA</span>
            <div class="board-dora__tiles">
                ${indicators.map(
                    (face) => html`<span class="board-dora__tile">${Tile(face, "face")}</span>`,
                )}
            </div>
        </div>
    `;
}

/**
 * The centre: the round, the wall's count and the table's honba and riichi sticks, each seat's riichi stick on its
 * side, and a bar on the side of the seat whose turn it is. Names, winds and scores are on the nameplates.
 */
function CenterInfo(
    center: BoardCenterInfo,
    plates: BoardDisplayState["nameplates"],
): TemplateResult {
    const current = SEAT_POSITIONS.find((_position, index) => plates[index].isCurrent);
    return html`
        <div class="board-area board-center" data-area="center">
            ${SEAT_POSITIONS.map((position, index) => RiichiStick(plates[index], position))}
            ${current === undefined ? "" : html`<span class="board-center__turn board-center__turn--${current}"></span>`}
            <div class="board-center__info">
                <div class="board-center__round">${center.roundDisplay}</div>
                <div class="board-center__sticks">
                    <span class="board-center__wall">${center.tilesRemaining}</span>
                    <span class="board-center__stick">
                        ${HonbaStickIcon()}<span class="board-center__stick-x">&times;</span>${center.honbaSticks}
                    </span>
                    <span class="board-center__stick">
                        ${RiichiStickIcon()}<span class="board-center__stick-x">&times;</span>${center.riichiSticks}
                    </span>
                </div>
            </div>
        </div>
    `;
}

function EmptyCenterArea(): TemplateResult {
    return html`
        <div class="board-area board-center" data-area="center"></div>
    `;
}

/**
 * The board, sized from its own box: the table (the other seats, every river and the centre) above the local strip
 * (the bottom seat's hand and melds), which spans the board's width so its tiles stay large enough to tap, the
 * dora in a corner of their own, beside the table on a wide board and above it otherwise, and the decision's
 * controls, when given, in the corner opposite them. Each seat's nameplate sits in the table beside its strip; a
 * pinned plate unpins on a click anywhere else on the board or on Escape.
 */
function GameBoard(props: GameBoardProps): TemplateResult {
    const { scoreDiff, state } = props;
    const boardClass = [
        "game-board",
        props.debug ? "game-board--debug" : "",
        scoreDiff.pinned === null ? "" : `game-board--diff-${scoreDiff.pinned}`,
    ]
        .filter(Boolean)
        .join(" ");
    const bottom = state?.players[0] ?? null;
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
                    ${state ? Nameplates(state.nameplates, scoreDiff) : ""}
                    ${props.notices ? BoardNotices(props.notices) : ""}
                </div>
                <div class="board-local">${HandArea("bottom", bottom, props.localHand)}${MeldsArea("bottom", bottom)}</div>
                ${state ? DoraDisplay(state.center.doraIndicators) : ""}
                ${props.actions ? html`<div class="board-actions" data-area="actions">${props.actions}</div>` : ""}
            </div>
            ${
                props.overlay
                    ? html`<div class="board-overlay">
                      <div class="board-overlay__panel">${props.overlay}</div>
                  </div>`
                    : ""
            }
        </div>
    `;
}

export { GameBoard };
export type { GameBoardProps, LocalHandInput };
