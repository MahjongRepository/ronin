import { type TemplateResult, html, nothing } from "lit-html";

import {
    type GameStartDisplayState,
    type GameStartSeat,
} from "@/entities/table/lib/game-start-display";
import { t } from "@/shared/i18n";

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
            ${seat.isDealer ? html`<span class="seating__mark seating__mark--dealer">${t("game.dealer")}</span>` : nothing}
            ${seat.isAiPlayer ? html`<span class="seating__mark">${t("game.seat.ai_tag")}</span>` : nothing}
            ${seat.isViewer ? html`<span class="seating__mark seating__mark--viewer">${t("game.seat.you")}</span>` : nothing}
        </span>
        ${seat.score === null ? nothing : html`<span class="seating__score">${seat.score}</span>`}
    </li>`;
}

/**
 * The seating: the game's length and the round, each seat's wind and player in wind order (the dealer, the viewer and
 * AI players marked) with its score where known, then the panel's ways on (a replay's start) or the view's controls
 * (the live opening screen's OK).
 */
export function GameStartDisplay(
    display: GameStartDisplayState,
    actions: readonly PanelAction[] = [],
    controls?: TemplateResult,
): TemplateResult {
    const heading =
        display.gameType === null
            ? display.round
            : t("game.seating.heading", { round: display.round, type: display.gameType });
    const scored = display.seats.some((seat) => seat.score !== null);
    return html`<section class=${scored ? "seating seating--scored" : "seating"} aria-label=${t("game.seating.label")}>
        <h2 class="seating__title">${heading}</h2>
        <ol class="seating__seats">${display.seats.map(SeatRow)}</ol>
        ${PanelActions(actions)}${controls ?? nothing}
    </section>`;
}
