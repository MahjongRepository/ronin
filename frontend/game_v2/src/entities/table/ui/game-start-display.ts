import { type TemplateResult, html, nothing } from "lit-html";

import {
    type GameStartDisplayState,
    type GameStartSeat,
} from "@/entities/table/lib/game-start-display";

import { type PanelAction, PanelActions } from "./panel-actions";
import { PlayerName } from "./player-name";

function seatClasses(seat: GameStartSeat): string {
    return [
        "seating__seat",
        seat.isViewer ? "seating__seat--viewer" : "",
        seat.isDealer ? "seating__seat--dealer" : "",
    ]
        .filter(Boolean)
        .join(" ");
}

function SeatRow(seat: GameStartSeat): TemplateResult {
    return html`<li class=${seatClasses(seat)}>
        <span class="seating__wind" title=${seat.windName} aria-label=${seat.windName}>${seat.wind}</span>
        ${PlayerName(seat.name, "seating__name")}
        <span class="seating__marks">
            ${seat.isDealer ? html`<span class="seating__mark seating__mark--dealer">Dealer</span>` : nothing}
            ${seat.isAiPlayer ? html`<span class="seating__mark">AI</span>` : nothing}
            ${seat.isViewer ? html`<span class="seating__mark seating__mark--viewer">You</span>` : nothing}
        </span>
        ${seat.score === null ? nothing : html`<span class="seating__score">${seat.score}</span>`}
    </li>`;
}

/**
 * The seating before the first deal: the game's length and first round, each seat's wind and player in wind order
 * (the dealer, the viewer and AI players marked) with its starting score where known, then the game start pause
 * counting down to the deal, or the panel's ways on (a replay's start).
 */
export function GameStartDisplay(
    display: GameStartDisplayState,
    actions: readonly PanelAction[] = [],
): TemplateResult {
    const heading = [display.gameType, display.round].filter(Boolean).join(" · ");
    const scored = display.seats.some((seat) => seat.score !== null);
    return html`<section class=${scored ? "seating seating--scored" : "seating"} aria-label="Seating">
        <h2 class="seating__title">${heading}</h2>
        <ol class="seating__seats">${display.seats.map(SeatRow)}</ol>
        ${display.status === null ? nothing : html`<p class="seating__status">${display.status}</p>`}
        ${PanelActions(actions)}
    </section>`;
}
