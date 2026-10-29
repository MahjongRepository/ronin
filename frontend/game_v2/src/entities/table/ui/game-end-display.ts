import { type TemplateResult, html } from "lit-html";

import { formatScore } from "@/entities/table/lib/board-mapper";
import { type GameEndResult, type PlayerState } from "@/entities/table/model/types";

function formatFinalScore(finalScore: number): string {
    if (finalScore > 0) {
        return `+${finalScore.toFixed(1)}`;
    }
    if (finalScore < 0) {
        return `\u2212${Math.abs(finalScore).toFixed(1)}`;
    }
    return finalScore.toFixed(1);
}

/** The riichi sticks the game ended with, which the winner's score holds; nothing when none were left. */
function leftoverRiichiNote(
    result: GameEndResult,
    players: readonly PlayerState[],
): TemplateResult | string {
    if (result.leftoverRiichiBonus === 0) {
        return "";
    }
    const winner = players.find((p) => p.seat === result.winnerSeat);
    const name = winner?.name ?? `Seat ${result.winnerSeat}`;
    return html`<div class="game-end-result__leftover">
        Leftover riichi sticks: +${result.leftoverRiichiBonus.toLocaleString("en-US")} to ${name}
    </div>`;
}

function GameEndDisplay(result: GameEndResult, players: readonly PlayerState[]): TemplateResult {
    return html`<div class="game-end-result">
        <div class="game-end-result__title">Final Standings</div>
        ${result.standings.map((standing, index) => {
            const player = players.find((p) => p.seat === standing.seat);
            const name = player?.name ?? `Seat ${standing.seat}`;
            const rank = index + 1;

            return html`<div class="game-end-result__row">
                <span class="game-end-result__rank">${rank}.</span>
                <span class="game-end-result__name">${name}</span>
                <span class="game-end-result__score">${formatScore(standing.score)}</span>
                <span class="game-end-result__final-score">${formatFinalScore(standing.finalScore)}</span>
            </div>`;
        })}
        ${leftoverRiichiNote(result, players)}
    </div>`;
}

export { GameEndDisplay };
