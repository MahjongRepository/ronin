import { type TemplateResult, html, nothing } from "lit-html";

import {
    type GameStartDisplayState,
    type GameStartSeat,
} from "@/entities/table/lib/game-start-display";
import { t } from "@/shared/i18n";

import { type PanelAction, PanelActions } from "./panel-actions";
import { PlayerName } from "./player-name";

/** What a view adds under and to the seating: its own controls, and a replay's pick of the seat to view from. */
export interface GameStartControls {
    readonly controls?: TemplateResult;
    readonly onPickSeat?: (seat: number) => void;
}

function seatClasses(seat: GameStartSeat): string {
    return [
        "seating__seat",
        seat.isViewer || seat.isViewpoint ? "seating__seat--viewer" : "",
        seat.isDealer ? "seating__seat--dealer" : "",
    ]
        .filter(Boolean)
        .join(" ");
}

/** A seat's name, a replay's a switch that views the board from the seat. */
function seatName(
    seat: GameStartSeat,
    onPickSeat: ((seat: number) => void) | undefined,
): TemplateResult {
    const name = PlayerName(seat.name, "seating__name");
    if (onPickSeat === undefined) {
        return name;
    }
    return html`<button
        type="button"
        class="seating__pick"
        aria-label=${t("replay.links.view_from", { player: seat.name })}
        aria-pressed=${String(seat.isViewpoint)}
        @click=${() => onPickSeat(seat.seat)}
    >${name}</button>`;
}

function seatRow(
    seat: GameStartSeat,
    onPickSeat: ((seat: number) => void) | undefined,
): TemplateResult {
    return html`<li class=${seatClasses(seat)}>
        <span class="seating__wind" title=${seat.windName} aria-label=${seat.windName}>${seat.wind}</span>
        ${seatName(seat, onPickSeat)}
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
 * (the live opening screen's OK). A replay's marks the seat its board is seen from and takes a press of a name as
 * that seat's view.
 */
export function GameStartDisplay(
    display: GameStartDisplayState,
    actions: readonly PanelAction[] = [],
    { controls, onPickSeat }: GameStartControls = {},
): TemplateResult {
    const heading =
        display.gameType === null
            ? display.round
            : t("game.seating.heading", { round: display.round, type: display.gameType });
    const scored = display.seats.some((seat) => seat.score !== null);
    return html`<section class=${scored ? "seating seating--scored" : "seating"} aria-label=${t("game.seating.label")}>
        <h2 class="seating__title">${heading}</h2>
        <ol class="seating__seats">${display.seats.map((seat) => seatRow(seat, onPickSeat))}</ol>
        ${PanelActions(actions)}${controls ?? nothing}
    </section>`;
}
