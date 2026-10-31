import { type TemplateResult, html, nothing } from "lit-html";

import { type GameEndDisplayState, type GameEndSeat } from "@/entities/table/lib/game-end-display";

import { type PanelAction, PanelActions } from "./panel-actions";
import { PlayerName } from "./player-name";

function SeatRow(seat: GameEndSeat): TemplateResult {
    const classes = seat.isViewer ? "seating__seat seating__seat--viewer" : "seating__seat";
    return html`<li class=${classes}>
        <span class="seating__placement">${seat.placement}</span>
        ${PlayerName(seat.name, "seating__name")}
        <span class="seating__marks">
            ${seat.isAiPlayer ? html`<span class="seating__mark">AI</span>` : nothing}
            ${seat.isViewer ? html`<span class="seating__mark seating__mark--viewer">You</span>` : nothing}
        </span>
        <span class="seating__score">${seat.score}</span>
        <span class="seating__result seating__result--${seat.resultTone}">${seat.result}</span>
    </li>`;
}

/**
 * The game's end on the seating panel: the game's length and how it ended (always as completed), the seats in
 * placement order with their final scores and uma/oka results, the leftover riichi sticks, and its ways on.
 */
export function GameEndDisplay(
    display: GameEndDisplayState,
    actions: readonly PanelAction[],
): TemplateResult {
    return html`<section class="seating seating--end" aria-label="Game over">
        <h2 class="seating__title">${[display.gameType, "Game over"].filter(Boolean).join(" · ")}</h2>
        <p class="seating__ending seating__ending--${display.ending.kind}">${display.ending.text}</p>
        <ol class="seating__seats">
            <li class="seating__seat seating__seat--head" aria-hidden="true">
                <span></span><span></span><span></span>
                <span class="seating__score">Score</span>
                <span class="seating__result">Uma/oka</span>
            </li>
            ${display.seats.map(SeatRow)}
        </ol>
        ${display.leftover === null ? nothing : html`<p class="seating__note">${display.leftover}</p>`}
        ${PanelActions(actions)}
    </section>`;
}
