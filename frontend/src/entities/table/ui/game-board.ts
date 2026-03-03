import { type TemplateResult, html } from "lit-html";

import {
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardPlayerDisplay,
    type BoardPlayerScore,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import { Discards, Hand, Meld, Tile } from "@/entities/tile";

interface GameBoardProps {
    debug: boolean;
    overlay?: TemplateResult;
    state: BoardDisplayState | null;
}

function PlayerAreas(seat: SeatPosition, player: BoardPlayerDisplay | null): TemplateResult {
    return html`
        <div class="board-area board-area--${seat}-hand" data-area="${seat}-hand">
            ${player ? Hand(player.hand, player.drawnTile) : ""}
        </div>
        <div class="board-area board-area--${seat}-melds" data-area="${seat}-melds">
            ${player ? player.melds.map((m) => Meld(m)) : ""}
        </div>
        <div class="board-area board-area--${seat}-disc" data-area="${seat}-discards">
            ${player ? Discards(player.discards) : ""}
        </div>
    `;
}

function ScoreEntry(player: BoardPlayerScore): TemplateResult {
    const classes = [
        "board-center__score",
        player.isCurrent ? "board-center__score--current" : "",
        player.isDealer ? "board-center__score--dealer" : "",
        player.isRiichi ? "board-center__score--riichi" : "",
    ]
        .filter(Boolean)
        .join(" ");

    return html`
        <div class="${classes}">
            <span class="board-center__wind">${player.wind}</span>
            <span class="board-center__points">${player.score}</span>
        </div>
    `;
}

function CenterInfo(center: BoardCenterInfo): TemplateResult {
    const [bottom, right, top, left] = center.scores;

    return html`
        <div class="board-area board-center" data-area="center">
            <div class="board-center__content">
                ${ScoreEntry(top)}
                <div class="board-center__middle-row">
                    ${ScoreEntry(left)}
                    <div class="board-center__info">
                        <div class="board-center__round">${center.roundDisplay}</div>
                        <div class="board-center__dora">
                            ${center.doraIndicators.map(
                                (face) =>
                                    html`<span class="board-center__dora-tile"
                                        >${Tile(face, "face")}</span
                                    >`,
                            )}
                        </div>
                        <div class="board-center__sticks">
                            ${
                                center.honbaSticks > 0
                                    ? html`<span>H:${center.honbaSticks}</span>`
                                    : ""
                            }
                            ${
                                center.riichiSticks > 0
                                    ? html`<span>R:${center.riichiSticks}</span>`
                                    : ""
                            }
                        </div>
                    </div>
                    ${ScoreEntry(right)}
                </div>
                ${ScoreEntry(bottom)}
            </div>
        </div>
    `;
}

function EmptyCenterArea(): TemplateResult {
    return html`
        <div class="board-area board-center" data-area="center"></div>
    `;
}

function GameBoard(props: GameBoardProps): TemplateResult {
    const boardClass = props.debug ? "game-board game-board--debug" : "game-board";
    const { state } = props;

    return html`
        <div class="${boardClass}">
            ${SEAT_POSITIONS.map((seat, i) => PlayerAreas(seat, state?.players[i] ?? null))}
            ${state ? CenterInfo(state.center) : EmptyCenterArea()}
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
