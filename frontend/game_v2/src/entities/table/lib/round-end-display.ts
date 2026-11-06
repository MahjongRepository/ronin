import { buildDiscardTiles } from "@/entities/table/lib/board-mapper";
import { drawName, isAbortiveDraw } from "@/entities/table/lib/draw-name";
import { handLimitName, isYakumanHand, yakumanName } from "@/entities/table/lib/hand-limit";
import { windName } from "@/entities/table/lib/wind-name";
import { yakuName } from "@/entities/table/lib/yaku-names";
import { roundEndPages } from "@/entities/table/model/handlers/round-end";
import { seatEntry } from "@/entities/table/model/helpers";
import {
    type DrawResult,
    type MeldRecord,
    type PlayerState,
    type RoundEndPage,
    type RoundEndResult,
    type TenpaiHandResult,
    type WinnerResult,
} from "@/entities/table/model/types";
import {
    type DiscardTile,
    type HandTile,
    type MeldTile,
    type TileFace,
    meldTiles,
    tile136toString,
} from "@/entities/tile";
import { type MessageKey, formatList, formatNumber, t } from "@/shared/i18n";
import {
    DORA_YAKU_ID,
    PAO_SHARE,
    type PaoShare,
    ROUND_RESULT_TYPE,
    seatDistance,
} from "@/shared/protocol";

const DORA_YAKU_IDS = new Set<number>(Object.values(DORA_YAKU_ID));

/** A hand a result reveals, as faces: its closed tiles sorted, then each meld laid out. */
export interface ResultHandDisplay {
    readonly tiles: readonly HandTile[];
    readonly melds: readonly (readonly MeldTile[])[];
}

export interface ResultYakuLine {
    readonly name: string;
    /** Its han; null for a yakuman yaku, which han do not price. */
    readonly han: number | null;
    readonly yakuman: string | null;
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
    readonly from: string | null;
    readonly hand: ResultHandDisplay;
    readonly winningTile: HandTile;
    /** How the winning tile came: Tsumo or Ron. */
    readonly winningTileLabel: string;
    readonly yaku: readonly ResultYakuLine[];
    /** The hand's value alone, without honba or riichi sticks. */
    readonly points: number;
    readonly limit: string | null;
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
    /** A nagashi mangan's proof: each seat that made it, with its river as the server names it. */
    readonly rivers: readonly NagashiRiverDisplay[];
}

export interface NagashiRiverDisplay {
    readonly name: string;
    /** The river as the board lays it, its riichi declaration's discard sideways. */
    readonly tiles: readonly DiscardTile[];
}

/** A round's result with the table it ended on that the panel reads: the players' names. */
export interface RoundEndTable {
    readonly result: RoundEndResult;
    readonly players: readonly PlayerState[];
}

/** One page of a round's result as the panel shows it, with where it stands among the result's pages. */
export interface RoundEndDisplayState {
    /** The page shown: the one asked for, clamped to the result's pages. */
    readonly page: number;
    readonly pageCount: number;
    readonly body: WinPageDisplay | DrawPageDisplay;
    readonly scores: readonly ResultScoreRow[];
}

interface SeatNames {
    readonly name: (seat: number) => string;
    readonly wind: (seat: number) => string;
}

function seatNames(players: readonly PlayerState[], dealerSeat: number): SeatNames {
    return {
        name: (seat) =>
            players.find((p) => p.seat === seat)?.name ?? t("game.seat.fallback_name", { seat }),
        wind: (seat) => windName(seatDistance(dealerSeat, seat)),
    };
}

export function formatPoints(points: number): string {
    const digits = formatNumber(Math.abs(points));
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

function handTile(tileId: number, hasAkadora: boolean): HandTile {
    return { face: tile136toString(tileId, hasAkadora), show: "face", tileId };
}

function resultHand(
    closedTiles: readonly number[],
    melds: readonly MeldRecord[],
    hasAkadora: boolean,
): ResultHandDisplay {
    return {
        melds: melds.map((meld) => meldTiles(meld, hasAkadora)),
        tiles: closedTiles
            .toSorted((first, second) => first - second)
            .map((tile) => handTile(tile, hasAkadora)),
    };
}

function yakuLines(winner: WinnerResult): ResultYakuLine[] {
    const yaku = winner.handResult.yaku
        .filter((entry) => !DORA_YAKU_IDS.has(entry.yakuId))
        .map((entry) => {
            const name = yakuName(entry.yakuId);
            if (entry.yakumanCount === 0) {
                return { han: entry.han, isDora: false, name, yakuman: null };
            }
            return {
                han: null,
                isDora: false,
                name,
                yakuman: entry.yakumanCount > 1 ? yakumanName(entry.yakumanCount) : null,
            };
        });
    const dora = [
        { han: winner.doraHan.dora, isDora: true, name: t("yaku.120"), yakuman: null },
        { han: winner.doraHan.aka, isDora: true, name: t("yaku.121"), yakuman: null },
        { han: winner.doraHan.ura, isDora: true, name: t("yaku.122"), yakuman: null },
    ].filter((entry) => entry.han > 0);
    return [...yaku, ...dora];
}

function hanFuLabel(winner: WinnerResult): string | null {
    const { fu, han } = winner.handResult;
    if (isYakumanHand(winner.handResult)) {
        return null;
    }
    return fu > 0 ? t("game.result.fu_han", { fu, han }) : t("game.result.han", { han });
}

function winTitle(result: RoundEndResult): string {
    switch (result.resultType) {
        case ROUND_RESULT_TYPE.TSUMO: {
            return t("game.call.tsumo");
        }
        case ROUND_RESULT_TYPE.DOUBLE_RON: {
            return t("game.result.double_ron");
        }
        default: {
            return t("game.call.ron");
        }
    }
}

function headBumpNote(result: RoundEndResult, names: SeatNames): string | null {
    const { headBumpedSeats, winners } = result;
    if (headBumpedSeats.length === 0) {
        return null;
    }
    return t("game.result.head_bump", {
        bumped: formatList(headBumpedSeats.map(names.name)),
        winners: formatList(winners.map((winner) => names.name(winner.seat))),
    });
}

const PAO_NOTES: Readonly<
    Record<PaoShare, { readonly withHonba: MessageKey; readonly withoutHonba: MessageKey }>
> = {
    [PAO_SHARE.ALL]: {
        withHonba: "game.result.pao_all_honba",
        withoutHonba: "game.result.pao_all",
    },
    [PAO_SHARE.HALF]: {
        withHonba: "game.result.pao_half_honba",
        withoutHonba: "game.result.pao_half",
    },
};

/**
 * What the seat liable (pao) for a winner's yakuman pays, worded from the server's liability: the yakuman it covers, all
 * or half of them, and whether the honba too; a liable seat that dealt in pays it all as the discarder.
 */
function paoNote(result: RoundEndResult, winner: WinnerResult, names: SeatNames): string | null {
    const { pao } = winner;
    if (pao === null) {
        return null;
    }
    const name = names.name(pao.seat);
    if (result.loserSeat === pao.seat) {
        return t("game.result.pao_dealt_in", { name });
    }
    const key = PAO_NOTES[pao.share][pao.paysHonba ? "withHonba" : "withoutHonba"];
    return t(key, { name, yaku: formatList(pao.yakuIds.map(yakuName)) });
}

function winNotes(result: RoundEndResult, winner: WinnerResult, names: SeatNames): string[] {
    const notes = [
        winner.honbaBonus > 0
            ? t("game.result.honba_bonus", { points: formatDelta(winner.honbaBonus) })
            : null,
        winner.riichiSticksCollected > 0
            ? t("game.result.riichi_bonus", { points: formatDelta(winner.riichiBonus) })
            : null,
        paoNote(result, winner, names),
        headBumpNote(result, names),
    ];
    return notes.filter((note) => note !== null);
}

function fromPhrase(result: RoundEndResult, names: SeatNames): string | null {
    if (result.loserSeat === null) {
        return null;
    }
    const name = names.name(result.loserSeat);
    return result.kanRobbed
        ? t("game.result.robbed_kan", { name })
        : t("game.result.from", { name });
}

function winPage(
    result: RoundEndResult,
    winner: WinnerResult,
    viewing: { names: SeatNames; hasAkadora: boolean },
): WinPageDisplay {
    const { names, hasAkadora } = viewing;
    return {
        doraIndicators: result.doraIndicators.map((tile) => tile136toString(tile, hasAkadora)),
        from: fromPhrase(result, names),
        hanFu: hanFuLabel(winner),
        hand: resultHand(winner.closedTiles, winner.melds, hasAkadora),
        kind: "win",
        limit: handLimitName(winner.handResult),
        notes: winNotes(result, winner, names),
        points: winner.handResult.points,
        title: winTitle(result),
        uraIndicators: winner.uraDoraIndicators.map((tile) => tile136toString(tile, hasAkadora)),
        winnerName: names.name(winner.seat),
        winningTile: handTile(winner.winningTile, hasAkadora),
        winningTileLabel:
            result.resultType === ROUND_RESULT_TYPE.TSUMO
                ? t("game.call.tsumo")
                : t("game.call.ron"),
        yaku: yakuLines(winner),
    };
}

function drawSubtitle(draw: DrawResult, names: SeatNames): string | null {
    if (draw.nagashiSeats.length > 0) {
        return t("game.result.nagashi_by", {
            names: formatList(draw.nagashiSeats.map(names.name)),
        });
    }
    if (draw.declarerSeat !== null) {
        return t("game.result.declared_by", { name: names.name(draw.declarerSeat) });
    }
    if (draw.ronSeats.length > 0) {
        return t("game.result.ron_called_by", { names: formatList(draw.ronSeats.map(names.name)) });
    }
    return isAbortiveDraw(draw.kind) ? t("draw.abortive") : evenDrawSubtitle(draw);
}

/** An exhaustive draw where every seat or none was tenpai, which moves no points, says so rather than nothing. */
function evenDrawSubtitle(draw: DrawResult): string | null {
    if (draw.tenpaiSeats.length === 0) {
        return t("game.result.all_noten");
    }
    return draw.notenSeats.length === 0 ? t("game.result.all_tenpai") : null;
}

function tenpaiHand(
    hand: TenpaiHandResult,
    names: SeatNames,
    hasAkadora: boolean,
): DrawPageDisplay["tenpaiHands"][number] {
    return {
        hand: resultHand(hand.closedTiles, hand.melds, hasAkadora),
        name: names.name(hand.seat),
    };
}

function nagashiRiver(
    river: DrawResult["nagashiRivers"][number],
    names: SeatNames,
): NagashiRiverDisplay {
    return { name: names.name(river.seat), tiles: buildDiscardTiles(river.discards, false) };
}

function drawPage(draw: DrawResult, names: SeatNames, hasAkadora: boolean): DrawPageDisplay {
    return {
        kind: "draw",
        rivers: draw.nagashiRivers.map((river) => nagashiRiver(river, names)),
        subtitle: drawSubtitle(draw, names),
        tenpaiHands: draw.tenpaiHands.map((hand) => tenpaiHand(hand, names, hasAkadora)),
        title: drawName(draw.kind),
    };
}

function winTag(winner: WinnerResult | undefined, seat: number): string | null {
    return winner !== undefined && winner.pao?.seat === seat ? t("game.state.pao") : null;
}

function drawTag(draw: DrawResult, seat: number): string | null {
    if (isAbortiveDraw(draw.kind)) {
        return null;
    }
    if (draw.nagashiSeats.includes(seat)) {
        return t("game.state.nagashi");
    }
    return draw.tenpaiSeats.includes(seat) ? t("game.state.tenpai") : t("game.state.noten");
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
    const pageChanges = changeMaps[changeMaps.length - 1];
    if (pageChanges === undefined) {
        throw new Error(`A round result has no payments for page ${index}`);
    }
    return players.map(({ seat }) => {
        const before = seatEntry(result.scoresBeforePayment, seat);
        return {
            after: changeMaps.reduce((sum, changeMap) => sum + seatEntry(changeMap, seat), before),
            delta: seatEntry(pageChanges, seat),
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
export function roundEndDisplay(
    table: RoundEndTable,
    page: number,
    hasAkadora = true,
): RoundEndDisplayState {
    const { players, result } = table;
    const names = seatNames(players, result.dealerSeat);
    const shown = roundEndPageAt(result, page);
    const body =
        shown.page.kind === "draw"
            ? drawPage(shown.page.draw, names, hasAkadora)
            : winPage(result, shown.page.winner, { hasAkadora, names });
    return {
        body,
        page: shown.index,
        pageCount: shown.count,
        scores: scoreRows(table, names, shown.index),
    };
}
