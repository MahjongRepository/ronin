import { type TemplateResult, html, nothing } from "lit-html";

import {
    type GameStartDisplayState,
    type GameStartSeat,
} from "@/entities/table/lib/game-start-display";

import { PlayerName } from "./player-name";

function SeatRow(seat: GameStartSeat): TemplateResult {
    const classes = [
        "game-start__seat",
        seat.isViewer ? "game-start__seat--viewer" : "",
        seat.isDealer ? "game-start__seat--dealer" : "",
    ]
        .filter(Boolean)
        .join(" ");
    return html`<li class=${classes}>
        <span class="game-start__wind" title=${seat.windName} aria-label=${seat.windName}>${seat.wind}</span>
        ${PlayerName(seat.name, "game-start__name")}
        <span class="game-start__marks">
            ${seat.isDealer ? html`<span class="game-start__mark game-start__mark--dealer">Dealer</span>` : nothing}
            ${seat.isAiPlayer ? html`<span class="game-start__mark">AI</span>` : nothing}
            ${seat.isViewer ? html`<span class="game-start__mark game-start__mark--viewer">You</span>` : nothing}
        </span>
    </li>`;
}

/**
 * The seating before the first deal: the game's length and first round, each seat's wind and player in wind order
 * (the dealer, the viewer and AI players marked), and the game start pause counting down to the deal.
 */
export function GameStartDisplay(display: GameStartDisplayState): TemplateResult {
    const heading = [display.gameType, display.round].filter(Boolean).join(" · ");
    return html`<div class="game-start">
        <h2 class="game-start__title">${heading}</h2>
        <ol class="game-start__seats">${display.seats.map(SeatRow)}</ol>
        <p class="game-start__status">${display.status}</p>
    </div>`;
}
