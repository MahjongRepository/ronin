import { type TemplateResult, html } from "lit-html";

import { windName } from "@/entities/table/lib/wind-name";
import { yakuName } from "@/entities/table/lib/yaku-names";
import {
    type PlayerState,
    type RoundEndResult,
    type WinnerResult,
} from "@/entities/table/model/types";
import { Hand, type HandTile, Meld, tile136toString } from "@/entities/tile";
import { type DecodedMeld, decodeMeldCompact } from "@/shared/protocol/decoders/meld";

function toHandTile(tileId: number): HandTile {
    return { face: tile136toString(tileId), show: "face" };
}

function safeDecodeMeld(immeValue: number): DecodedMeld | null {
    try {
        return decodeMeldCompact(immeValue);
    } catch {
        return null;
    }
}

function formatDelta(delta: number): string {
    if (delta > 0) {
        return `+${delta.toLocaleString("en-US")}`;
    }
    if (delta < 0) {
        return `\u2212${Math.abs(delta).toLocaleString("en-US")}`;
    }
    return "0";
}

const YAKUMAN_LABELS: Record<number, string> = {
    1: "Yakuman",
    2: "Double Yakuman",
    3: "Triple Yakuman",
    4: "Quadruple Yakuman",
    5: "Quintuple Yakuman",
    6: "Sextuple Yakuman",
};

function formatTotals(han: number, fu: number): string {
    if (han >= 13) {
        const multiplier = Math.floor(han / 13);
        return YAKUMAN_LABELS[multiplier] ?? `${multiplier}x Yakuman`;
    }
    return `${han} han / ${fu} fu`;
}

function WinnerSection(
    winner: WinnerResult,
    players: PlayerState[],
    dealerSeat: number,
): TemplateResult {
    const player = players.find((p) => p.seat === winner.seat);
    const name = player?.name ?? `Seat ${winner.seat}`;
    const wind = windName((winner.seat - dealerSeat + 4) % 4);

    const closedHandTiles = winner.closedTiles.map(toHandTile);
    const drawnTile = toHandTile(winner.winningTile);

    const melds = winner.melds.map(safeDecodeMeld).filter((m): m is DecodedMeld => m !== null);

    return html`<div class="round-end-result__winner">
        <div class="round-end-result__winner-name">${name} (${wind})</div>
        <div class="round-end-result__hand">
            ${Hand(closedHandTiles, drawnTile)}
            ${melds.map((m) => Meld(m))}
        </div>
        <div class="round-end-result__yaku-list">
            ${winner.handResult.yaku.map(
                (yk) =>
                    html`<div class="round-end-result__yaku-item">
                        ${yakuName(yk.yakuId)}: ${yk.han} han
                    </div>`,
            )}
        </div>
        <div class="round-end-result__totals">
            ${formatTotals(winner.handResult.han, winner.handResult.fu)}
        </div>
    </div>`;
}

function RoundEndDisplay(
    result: RoundEndResult,
    players: PlayerState[],
    dealerSeat: number,
): TemplateResult {
    return html`<div class="round-end-result">
        ${result.winners.map((w) => WinnerSection(w, players, dealerSeat))}
        <div class="round-end-result__scores">
            ${players.map((p) => {
                const delta = result.scoreChanges[String(p.seat)] ?? 0;
                return html`<div class="round-end-result__score-row">
                    <span class="round-end-result__score-name">${p.name}</span>
                    <span class="round-end-result__score-delta">${formatDelta(delta)}</span>
                </div>`;
            })}
        </div>
    </div>`;
}

export { RoundEndDisplay };
