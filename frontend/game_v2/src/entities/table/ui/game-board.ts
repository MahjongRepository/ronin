import { type TemplateResult, html } from "lit-html";

import {
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardPlayerDisplay,
    type BoardPlayerScore,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import { Discards, Hand, Meld, Tile, type TileFace } from "@/entities/tile";

import { HonbaStickIcon } from "./honba-stick-icon";
import { RiichiStickIcon } from "./riichi-stick-icon";

interface GameBoardProps {
    debug: boolean;
    overlay?: TemplateResult;
    state: BoardDisplayState | null;
}

function HandArea(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    return html`<div class="board-area board-area--${seat}-hand" data-area="${seat}-hand">
        ${player ? Hand(player.hand, player.drawnTile) : ""}
    </div>`;
}

function MeldsArea(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    return html`<div class="board-area board-melds board-area--${seat}-melds" data-area="${seat}-melds">
        ${player ? player.melds.toReversed().map((m) => Meld(m)) : ""}
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

function ScoreEntry(player: BoardPlayerScore, position: SeatPosition): TemplateResult {
    const classes = [
        "board-center__score",
        `board-center__score--${position}`,
        player.isCurrent ? "board-center__score--current" : "",
    ]
        .filter(Boolean)
        .join(" ");

    return html`
        <div class="${classes}">
            <span class="board-center__points">${player.score}</span>
        </div>
    `;
}

function RiichiStick(player: BoardPlayerScore, position: SeatPosition): TemplateResult {
    if (!player.isRiichi) {
        return html``;
    }
    return html`<span class="board-center__riichi-stick board-center__riichi-stick--${position}">${RiichiStickIcon()}</span>`;
}

type CornerPosition = "top-left" | "top-right" | "bottom-left" | "bottom-right";

function WindBadge(player: BoardPlayerScore, corner: CornerPosition): TemplateResult {
    const classes = [
        "board-center__wind-badge",
        `board-center__wind-badge--${corner}`,
        player.isDealer ? "board-center__wind-badge--dealer" : "",
    ]
        .filter(Boolean)
        .join(" ");

    return html`<span class="${classes}">${player.wind}</span>`;
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

function CenterInfo(center: BoardCenterInfo): TemplateResult {
    const [bottom, right, top, left] = center.scores;

    return html`
        <div class="board-area board-center" data-area="center">
            ${WindBadge(left, "top-left")}
            ${WindBadge(top, "top-right")}
            ${WindBadge(bottom, "bottom-left")}
            ${WindBadge(right, "bottom-right")}
            ${RiichiStick(left, "left")}
            ${RiichiStick(right, "right")}
            ${RiichiStick(top, "top")}
            ${RiichiStick(bottom, "bottom")}
            ${ScoreEntry(left, "left")}
            ${ScoreEntry(right, "right")}
            <div class="board-center__content">
                ${ScoreEntry(top, "top")}
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
                ${ScoreEntry(bottom, "bottom")}
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
 * (the bottom seat's hand and melds), which spans the board's width so its tiles stay large enough to tap, and the
 * dora in a corner of their own, beside the table on a wide board and above it otherwise.
 */
function GameBoard(props: GameBoardProps): TemplateResult {
    const boardClass = props.debug ? "game-board game-board--debug" : "game-board";
    const { state } = props;
    const bottom = state?.players[0] ?? null;

    return html`
        <div class="${boardClass}">
            <div class="board-layout">
                <div class="board-table">
                    ${SEAT_POSITIONS.map((seat, i) => TableAreas(seat, state?.players[i] ?? null))}
                    ${state ? CenterInfo(state.center) : EmptyCenterArea()}
                </div>
                <div class="board-local">${HandArea("bottom", bottom)}${MeldsArea("bottom", bottom)}</div>
                ${state ? DoraDisplay(state.center.doraIndicators) : ""}
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
export type { GameBoardProps };
