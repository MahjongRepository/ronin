import { type TemplateResult, html } from "lit-html";

import { windName } from "@/entities/table/lib/wind-name";
import { yakuName } from "@/entities/table/lib/yaku-names";
import {
    type PlayerState,
    type RoundEndResult,
    type WinnerResult,
} from "@/entities/table/model/types";
import { Hand, type HandTile, Meld, Tile, tile136toString } from "@/entities/tile";
import { ROUND_RESULT_TYPE } from "@/shared/protocol";
import { decodeMeldCompact } from "@/shared/protocol/decoders/meld";

function toHandTile(tileId: number): HandTile {
    return { face: tile136toString(tileId), show: "face" };
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

const RESULT_TYPE_LABELS: Record<number, string> = {
    [ROUND_RESULT_TYPE.TSUMO]: "Tsumo",
    [ROUND_RESULT_TYPE.RON]: "Ron",
    [ROUND_RESULT_TYPE.DOUBLE_RON]: "Double Ron",
    [ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW]: "Exhaustive Draw",
    [ROUND_RESULT_TYPE.ABORTIVE_DRAW]: "Abortive Draw",
    [ROUND_RESULT_TYPE.NAGASHI_MANGAN]: "Nagashi Mangan",
};

function resultTypeLabel(resultType: number): string {
    return RESULT_TYPE_LABELS[resultType] ?? "Round End";
}

function winnerPoints(result: RoundEndResult): number | null {
    if (result.winners.length === 0) {
        return null;
    }
    let total = 0;
    for (const winner of result.winners) {
        const delta = result.scoreChanges[String(winner.seat)] ?? 0;
        if (delta > 0) {
            total += delta;
        }
    }
    return total > 0 ? total : null;
}

function deltaModifier(delta: number): string {
    if (delta > 0) {
        return " round-end-result__score-delta--positive";
    }
    if (delta < 0) {
        return " round-end-result__score-delta--negative";
    }
    return "";
}

function WinnerSection(
    winner: WinnerResult,
    players: PlayerState[],
    dealerSeat: number,
): TemplateResult {
    const player = players.find((p) => p.seat === winner.seat);
    const name = player?.name ?? `Seat ${winner.seat}`;
    const wind = windName((winner.seat - dealerSeat + 4) % 4);

    const closedHandTiles = [...winner.closedTiles].sort((id1, id2) => id1 - id2).map(toHandTile);
    const drawnTile = toHandTile(winner.winningTile);

    const melds = winner.melds.map(decodeMeldCompact);

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
                        <span class="round-end-result__yaku-name">${yakuName(yk.yakuId)}</span>
                        <span class="round-end-result__yaku-han">${yk.han} han</span>
                    </div>`,
            )}
        </div>
        <div class="round-end-result__totals">
            ${formatTotals(winner.handResult.han, winner.handResult.fu)}
        </div>
    </div>`;
}

function indicatorGroup(label: string, tileIds: number[]): TemplateResult | string {
    if (tileIds.length === 0) {
        return "";
    }
    return html`<div class="round-end-result__indicator-group">
        <span class="round-end-result__indicator-label">${label}</span>
        <span class="round-end-result__indicator-tiles">
            ${tileIds.map((id) => html`<span class="round-end-result__indicator-tile">${Tile(tile136toString(id), "face")}</span>`)}
        </span>
    </div>`;
}

function doraIndicatorSection(doraIds: number[], uraDoraIds: number[]): TemplateResult | string {
    if (doraIds.length === 0 && uraDoraIds.length === 0) {
        return "";
    }

    return html`<div class="round-end-result__indicators">
        ${indicatorGroup("Dora", doraIds)}
        ${indicatorGroup("Ura", uraDoraIds)}
    </div>`;
}

function RoundEndDisplay(
    result: RoundEndResult,
    players: PlayerState[],
    dealerSeat: number,
): TemplateResult {
    const points = winnerPoints(result);

    return html`<div class="round-end-result">
        <div class="round-end-result__header">
            <div class="round-end-result__result-type">${resultTypeLabel(result.resultType)}</div>
            ${
                points !== null
                    ? html`<div class="round-end-result__points">${points.toLocaleString("en-US")} pts</div>`
                    : ""
            }
        </div>
        ${result.winners.length > 0 ? doraIndicatorSection(result.doraIndicators, result.uraDoraIndicators) : ""}
        ${result.winners.map((w) => WinnerSection(w, players, dealerSeat))}
        <div class="round-end-result__scores">
            ${players.map((p) => {
                const delta = result.scoreChanges[String(p.seat)] ?? 0;
                const wind = windName((p.seat - dealerSeat + 4) % 4);
                return html`<div class="round-end-result__score-row">
                    <span class="round-end-result__score-wind">${wind}</span>
                    <span class="round-end-result__score-name">${p.name}</span>
                    <span class="round-end-result__score-value">${p.score.toLocaleString("en-US")}</span>
                    <span class="round-end-result__score-delta${deltaModifier(delta)}">${formatDelta(delta)}</span>
                </div>`;
            })}
        </div>
    </div>`;
}

export { RoundEndDisplay };
