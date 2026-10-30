import { drawName, isAbortiveDraw } from "@/entities/table/lib/draw-name";
import { handLimitName, isYakumanYaku } from "@/entities/table/lib/hand-limit";
import { windName } from "@/entities/table/lib/wind-name";
import { yakuName } from "@/entities/table/lib/yaku-names";
import { RIICHI_STICK_VALUE, roundEndPages } from "@/entities/table/model/handlers/round-end";
import {
    type DrawResult,
    type PlayerState,
    type RoundEndPage,
    type RoundEndResult,
    type TenpaiHandResult,
    type WinnerResult,
} from "@/entities/table/model/types";
import {
    type HandTile,
    type MeldTile,
    type TileFace,
    meldTiles,
    tile136toString,
} from "@/entities/tile";
import { ROUND_RESULT_TYPE, decodeMeldCompact } from "@/shared/protocol";

const DORA_YAKU_IDS = new Set([120, 121, 122]);

/** A hand a result reveals, as faces: its closed tiles sorted, then each meld laid out. */
export interface ResultHandDisplay {
    readonly tiles: readonly HandTile[];
    readonly melds: readonly (readonly MeldTile[])[];
}

export interface ResultYakuLine {
    readonly name: string;
    readonly han: number;
    /** A dora, red five or ura dora line, listed after the yaku. */
    readonly isDora: boolean;
}

export interface ResultScoreRow {
    readonly seat: number;
    readonly wind: string;
    readonly name: string;
    /** For a draw that judges tenpai: Tenpai, Noten or Nagashi; Pao for the seat liable for the page's win; else null. */
    readonly tag: string | null;
    /** The change this page describes. */
    readonly delta: number;
    /** The score after every payment through this page. */
    readonly after: number;
}

export interface WinPageDisplay {
    readonly kind: "win";
    /** Tsumo, Ron or Double ron. */
    readonly title: string;
    readonly winnerName: string;
    readonly winnerWind: string;
    /** The discarder (or the robbed kan's declarer) of a ron, null for a tsumo. */
    readonly fromName: string | null;
    readonly hand: ResultHandDisplay;
    readonly winningTile: HandTile;
    /** How the winning tile came: Tsumo or Ron. */
    readonly winningTileLabel: string;
    readonly yaku: readonly ResultYakuLine[];
    /** The hand's value alone, without honba or riichi sticks. */
    readonly points: number;
    readonly limit: string | null;
    /** "5 han 30 fu"; null for a yakuman, which han and fu do not price. */
    readonly hanFu: string | null;
    readonly doraIndicators: readonly TileFace[];
    readonly uraIndicators: readonly TileFace[];
    readonly notes: readonly string[];
}

export interface DrawPageDisplay {
    readonly kind: "draw";
    readonly title: string;
    readonly subtitle: string | null;
    readonly tenpaiHands: readonly { readonly name: string; readonly hand: ResultHandDisplay }[];
}

/** A round's result with the table it ended on that the panel reads: the players' names and the round's dealer. */
export interface RoundEndTable {
    readonly result: RoundEndResult;
    readonly players: readonly PlayerState[];
    readonly dealerSeat: number;
}

/** One page of a round's result as the panel shows it, with where it stands among the result's pages. */
export interface RoundEndDisplayState {
    /** The page shown: the one asked for, clamped to the result's pages. */
    readonly page: number;
    readonly pageCount: number;
    readonly body: WinPageDisplay | DrawPageDisplay;
    readonly scores: readonly ResultScoreRow[];
    /** The result was read against a table out of step with the server, so its dora and dealer may be wrong. */
    readonly uncertain: boolean;
}

interface SeatNames {
    readonly name: (seat: number) => string;
    readonly wind: (seat: number) => string;
}

function seatNames(players: readonly PlayerState[], dealerSeat: number): SeatNames {
    return {
        name: (seat) => players.find((p) => p.seat === seat)?.name ?? `Seat ${seat}`,
        wind: (seat) => windName((seat - dealerSeat + 4) % 4),
    };
}

export function formatPoints(points: number): string {
    const digits = Math.abs(points).toLocaleString("en-US");
    return points < 0 ? `−${digits}` : digits;
}

export function formatDelta(delta: number): string {
    return delta > 0 ? `+${formatPoints(delta)}` : formatPoints(delta);
}

/** A result's page at `page` clamped to its pages, with its index and the page count. */
export function roundEndPageAt(
    result: RoundEndResult,
    page: number,
): { readonly page: RoundEndPage; readonly index: number; readonly count: number } {
    const pages = roundEndPages(result);
    const index = Math.min(Math.max(0, Math.trunc(page)), pages.length - 1);
    const shown = pages[index];
    if (shown === undefined) {
        throw new Error("A round result has neither a winner nor a draw");
    }
    return { count: pages.length, index, page: shown };
}

function handTile(tileId: number): HandTile {
    return { face: tile136toString(tileId), show: "face", tileId };
}

function resultHand(closedTiles: readonly number[], melds: readonly number[]): ResultHandDisplay {
    return {
        melds: melds.map((meld) => meldTiles(decodeMeldCompact(meld))),
        tiles: closedTiles.toSorted((first, second) => first - second).map(handTile),
    };
}

function yakuLines(winner: WinnerResult): ResultYakuLine[] {
    const yaku = winner.handResult.yaku
        .filter((entry) => !DORA_YAKU_IDS.has(entry.yakuId))
        .map((entry) => ({ han: entry.han, isDora: false, name: yakuName(entry.yakuId) }));
    const dora = [
        { han: winner.doraHan.dora, isDora: true, name: "Dora" },
        { han: winner.doraHan.aka, isDora: true, name: "Red Five" },
        { han: winner.doraHan.ura, isDora: true, name: "Ura Dora" },
    ].filter((entry) => entry.han > 0);
    return [...yaku, ...dora];
}

function hanFuLabel(winner: WinnerResult): string | null {
    const { fu, han, yaku } = winner.handResult;
    if (yaku.some((entry) => isYakumanYaku(entry.yakuId))) {
        return null;
    }
    return fu > 0 ? `${han} han ${fu} fu` : `${han} han`;
}

function winTitle(result: RoundEndResult): string {
    switch (result.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            return "Tsumo";
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return "Double ron";
        }
        default: {
            return "Ron";
        }
    }
}

function headBumpNote(result: RoundEndResult, names: SeatNames): string | null {
    const { headBumpedSeats, winners } = result;
    if (headBumpedSeats.length === 0) {
        return null;
    }
    const won = winners.map((winner) => names.name(winner.seat)).join(" and ");
    const bumped = headBumpedSeats.map((seat) => `${names.name(seat)}'s`).join(" and ");
    return `${won} won over ${bumped} ron (head bump)`;
}

function winNotes(result: RoundEndResult, winner: WinnerResult, names: SeatNames): string[] {
    const sticks = winner.riichiSticksCollected;
    const notes = [
        winner.honbaBonus > 0 ? `Honba ${formatDelta(winner.honbaBonus)}` : null,
        sticks > 0 ? `Riichi ×${sticks} ${formatDelta(sticks * RIICHI_STICK_VALUE)}` : null,
        winner.paoSeat === null ? null : `Pao: ${names.name(winner.paoSeat)} is liable`,
        headBumpNote(result, names),
    ];
    return notes.filter((note) => note !== null);
}

function winPage(result: RoundEndResult, winner: WinnerResult, names: SeatNames): WinPageDisplay {
    return {
        doraIndicators: result.doraIndicators.map(tile136toString),
        fromName: result.loserSeat === null ? null : names.name(result.loserSeat),
        hanFu: hanFuLabel(winner),
        hand: resultHand(winner.closedTiles, winner.melds),
        kind: "win",
        limit: handLimitName(winner.handResult, winner.isDealer),
        notes: winNotes(result, winner, names),
        points: winner.handResult.points,
        title: winTitle(result),
        uraIndicators: winner.uraDoraIndicators.map(tile136toString),
        winnerName: names.name(winner.seat),
        winnerWind: names.wind(winner.seat),
        winningTile: handTile(winner.winningTile),
        winningTileLabel: result.resultType === ROUND_RESULT_TYPE.TSUMO ? "Tsumo" : "Ron",
        yaku: yakuLines(winner),
    };
}

function drawSubtitle(draw: DrawResult, names: SeatNames): string | null {
    if (draw.nagashiSeats.length > 0) {
        return `by ${draw.nagashiSeats.map(names.name).join(", ")}`;
    }
    if (draw.declarerSeat !== null) {
        return `declared by ${names.name(draw.declarerSeat)}`;
    }
    if (draw.ronSeats.length > 0) {
        return `ron called by ${draw.ronSeats.map(names.name).join(", ")}`;
    }
    return isAbortiveDraw(draw.kind) ? "Abortive draw" : null;
}

function tenpaiHand(
    hand: TenpaiHandResult,
    names: SeatNames,
): DrawPageDisplay["tenpaiHands"][number] {
    return { hand: resultHand(hand.closedTiles, hand.melds), name: names.name(hand.seat) };
}

function drawPage(draw: DrawResult, names: SeatNames): DrawPageDisplay {
    return {
        kind: "draw",
        subtitle: drawSubtitle(draw, names),
        tenpaiHands: draw.tenpaiHands.map((hand) => tenpaiHand(hand, names)),
        title: drawName(draw.kind),
    };
}

function winTag(winner: WinnerResult | undefined, seat: number): string | null {
    return winner !== undefined && winner.paoSeat === seat ? "Pao" : null;
}

function drawTag(draw: DrawResult, seat: number): string | null {
    if (isAbortiveDraw(draw.kind)) {
        return null;
    }
    if (draw.nagashiSeats.includes(seat)) {
        return "Nagashi";
    }
    return draw.tenpaiSeats.includes(seat) ? "Tenpai" : "Noten";
}

/**
 * The seats' scores a page shows: the changes it describes and the scores they lead to. A double ron's pages settle
 * one winner at a time, so its last page ends at the scores the table settled.
 */
function scoreRows(
    { players, result }: RoundEndTable,
    names: SeatNames,
    index: number,
): ResultScoreRow[] {
    const settled = result.winners.slice(0, index + 1);
    const changeMaps =
        settled.length === 0 ? [result.scoreChanges] : settled.map((winner) => winner.scoreChanges);
    return players.map(({ seat }) => {
        const changes = changeMaps.map((changeMap) => changeMap[String(seat)] ?? 0);
        const before = result.scoresBeforePayment[String(seat)] ?? 0;
        return {
            after: changes.reduce((sum, change) => sum + change, before),
            delta: changes.at(-1) ?? 0,
            name: names.name(seat),
            seat,
            tag:
                result.draw === null
                    ? winTag(result.winners[index], seat)
                    : drawTag(result.draw, seat),
            wind: names.wind(seat),
        };
    });
}

/**
 * A round's result at a page, as the result panel shows it: a winner's hand, value and payments, or the draw with
 * its tenpai hands, and every seat's change and score through that page. A double ron has a page per winner
 * (`roundEndPages`); a page out of range shows the nearest.
 */
export function roundEndDisplay(table: RoundEndTable, page: number): RoundEndDisplayState {
    const { dealerSeat, players, result } = table;
    const names = seatNames(players, dealerSeat);
    const shown = roundEndPageAt(result, page);
    const body =
        shown.page.kind === "draw"
            ? drawPage(shown.page.draw, names)
            : winPage(result, shown.page.winner, names);
    return {
        body,
        page: shown.index,
        pageCount: shown.count,
        scores: scoreRows(table, names, shown.index),
        uncertain: !result.inStep,
    };
}
