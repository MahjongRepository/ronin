import { type TemplateResult, html } from "lit-html";

import { windName } from "@/entities/table/lib/wind-name";
import { type PlayerState } from "@/entities/table/model/types";

function windIndex(seat: number, dealerSeat: number): number {
    return (seat - dealerSeat + 4) % 4;
}

function sortByWind(players: PlayerState[], dealerSeat: number): PlayerState[] {
    return [...players].sort(
        (p1, p2) => windIndex(p1.seat, dealerSeat) - windIndex(p2.seat, dealerSeat),
    );
}

function GameStartDisplay(players: PlayerState[], dealerSeat: number): TemplateResult {
    const sorted = sortByWind(players, dealerSeat);
    return html`<div class="game-start-result">
        <div class="game-start-result__title">Game Start</div>
        ${sorted.map((player) => {
            const wind = windName((player.seat - dealerSeat + 4) % 4);
            return html`<div class="game-start-result__row">
                <span class="game-start-result__wind">${wind}</span>
                <span class="game-start-result__name">${player.name}</span>
            </div>`;
        })}
    </div>`;
}

export { GameStartDisplay };
