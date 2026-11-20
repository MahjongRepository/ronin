import { drawName, isAbortiveDraw } from "@/entities/table/lib/draw-name";
import { handLimitName, isYakumanHand, yakumanName } from "@/entities/table/lib/hand-limit";
import { formatRoundName } from "@/entities/table/lib/round-name";
import { windLetter, windName } from "@/entities/table/lib/wind-name";
import { yakuName } from "@/entities/table/lib/yaku-names";
import { yakumanKanji, yakumanSeal } from "@/entities/table/lib/yakuman-seal";
import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table/model/board-types";
import { roundEndPages } from "@/entities/table/model/handlers/round-end";
import { seatEntry } from "@/entities/table/model/helpers";
import {
    type DrawResult,
    type MeldRecord,
    type PlayerState,
    type RoundEndPage,
    type RoundEndResult,
    type ShownHandResult,
    type TableState,
    type WinnerResult,
    type YakuResult,
} from "@/entities/table/model/types";
import {
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

const CHANKAN_YAKU_ID = 4;

const RANK_NAMES: readonly MessageKey[] = [
    "game.summary.rank_1",
    "game.summary.rank_2",
    "game.summary.rank_3",
    "game.summary.rank_4",
];

/** A hand a result reveals, as faces: its closed tiles sorted, then each meld laid out. */
export interface ResultHandDisplay {
    readonly tiles: readonly HandTile[];
    readonly melds: readonly (readonly MeldTile[])[];
}

/** A named yakuman's line: its seal, its name in kanji and its count's name past one (Double yakuman). */
export interface ResultYakuman {
    readonly seal: string;
    readonly kanji: string | null;
    readonly multiple: string | null;
}

export interface ResultYakuLine {
    readonly name: string;
    /** Its han; null for a yakuman yaku, which han do not price. */
    readonly han: number | null;
    readonly yakuman: ResultYakuman | null;
    /** A dora, red five or ura dora line, listed after the yaku. */
    readonly isDora: boolean;
}

/**
 * Where a seat's card stands in the result's diamond: as the seat sits at the table seen from the board's bottom seat.
 * Its role colours its change: what it gained or paid on this page.
 */
export interface ResultSeat {
    readonly seat: number;
    readonly position: SeatPosition;
    /** The seat wind's letter, in the script the player picked; its name is for a screen reader. */
    readonly wind: string;
    readonly windName: string;
    readonly name: string;
    /**
     * What the page's change alone does not say: Pao for the seat liable for the page's win, Tenpai or Noten for a
     * draw's seat that moved no points while others did; else null.
     */
    readonly tag: string | null;
    readonly role: "gain" | "loss" | "none";
    /** The change this page describes. */
    readonly delta: number;
    /** The score after every payment through this page. */
    readonly after: number;
    /** The seat's placement at that score. */
    readonly rank: string;
}

/**
 * The honba and riichi sticks a winner collected and what they paid it over the hand's value. The honba count is the
 * table's, so a result shown out of step names none.
 */
export interface ResultSticks {
    readonly honba: number | null;
    readonly riichi: number;
    readonly bonus: number;
}

export interface WinPageDisplay {
    /** Tsumo, Ron or Double ron, with whom it was won from, for a screen reader: the seats' changes show it. */
    readonly title: string;
    readonly winnerName: string;
    readonly winnerSeat: number;
    readonly from: string | null;
    /** The seat that dealt in or whose kan was robbed; null for a tsumo. */
    readonly fromSeat: number | null;
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
    readonly sticks: ResultSticks;
    readonly notes: readonly string[];
}

/** A win's result: every winner's page, so the panel holds the largest of them whichever shows. */
export interface WinBodyDisplay {
    readonly kind: "win";
    readonly pages: readonly WinPageDisplay[];
}

export interface DrawPageDisplay {
    readonly kind: "draw";
    readonly title: string;
    readonly subtitle: string | null;
    /** The hands the draw shows under their players' names: the tenpai hands, or the hands an abort shows. */
    readonly hands: readonly { readonly name: string; readonly hand: ResultHandDisplay }[];
}

/**
 * A nagashi mangan, shown as a win's value: the hand's name and limit, who made it, and, made by one seat alone, what
 * it collected. Several seats each settle a mangan and pay each other's, so their changes are net, left to the seats.
 */
export interface NagashiPageDisplay {
    readonly kind: "nagashi";
    readonly title: string;
    readonly limit: string;
    readonly makers: readonly string[];
    readonly points: number | null;
}

/** A round's result with the table it ended on that the panel reads: the names, the round and the first dealer. */
export interface RoundEndTable extends Pick<
    TableState,
    "players" | "firstDealerSeat" | "roundWind" | "roundInWind" | "honbaSticks" | "inStep"
> {
    readonly result: RoundEndResult;
}

/** How the panel reads a result: at which page, and from which seat, the diamond's bottom. */
export interface RoundEndView {
    readonly page: number;
    readonly bottomSeat: number;
}

/** One page of a round's result as the panel shows it, with where it stands among the result's pages. */
export interface RoundEndDisplayState {
    /** The page shown: the one asked for, clamped to the result's pages. */
    readonly page: number;
    readonly pageCount: number;
    /** Whose each page is, which the buttons between pages name: a winner's name, a draw's title. */
    readonly pageNames: readonly string[];
    /** The round the result ends, with its honba; null on a table out of step, which may name another round. */
    readonly round: string | null;
    readonly body: WinBodyDisplay | DrawPageDisplay | NagashiPageDisplay;
    /** Every seat, in `SEAT_POSITIONS` order from the bottom seat. */
    readonly seats: readonly ResultSeat[];
}

interface SeatNames {
    readonly name: (seat: number) => string;
    readonly wind: (seat: number) => number;
}

function seatNames(players: readonly PlayerState[], dealerSeat: number): SeatNames {
    return {
        name: (seat) =>
            players.find((p) => p.seat === seat)?.name ?? t("game.seat.fallback_name", { seat }),
        wind: (seat) => seatDistance(dealerSeat, seat),
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

function yakumanLine(entry: YakuResult): ResultYakuman {
    return {
        kanji: yakumanKanji(entry.yakuId),
        multiple: entry.yakumanCount > 1 ? yakumanName(entry.yakumanCount) : null,
        seal: yakumanSeal(entry.yakumanCount),
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
            return { han: null, isDora: false, name, yakuman: yakumanLine(entry) };
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
        default: {
            return result.winners.length > 1 ? t("game.result.double_ron") : t("game.call.ron");
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
 * What the seat liable (pao) for a winner's yakuman pays, worded from the server's liability: the yakuman that made it
 * liable, all or half of the whole hand, and whether the honba too; a liable seat that dealt in pays it all as the discarder.
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

/**
 * A robbed kan the yaku do not name (a closed kan robbed for kokushi, which lists only the yakuman): the result has no
 * headline to say it, so a note does.
 */
function robbedKanNote(
    result: RoundEndResult,
    winner: WinnerResult,
    names: SeatNames,
): string | null {
    if (!result.kanRobbed || result.loserSeat === null) {
        return null;
    }
    const named = winner.handResult.yaku.some((entry) => entry.yakuId === CHANKAN_YAKU_ID);
    return named ? null : t("game.result.robbed_kan_note", { name: names.name(result.loserSeat) });
}

function winNotes(result: RoundEndResult, winner: WinnerResult, names: SeatNames): string[] {
    return [
        robbedKanNote(result, winner, names),
        paoNote(result, winner, names),
        headBumpNote(result, names),
    ].filter((note) => note !== null);
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

/**
 * The sticks a winner collected: the round's honba where the server paid it any honba bonus (a head-bumped double
 * ron's second winner collects none), and the riichi sticks it took.
 */
function winnerSticks(winner: WinnerResult, honbaSticks: number | null): ResultSticks {
    return {
        bonus: winner.honbaBonus + winner.riichiBonus,
        honba: winner.honbaBonus > 0 ? honbaSticks : 0,
        riichi: winner.riichiSticksCollected,
    };
}

interface Viewing {
    readonly names: SeatNames;
    readonly hasAkadora: boolean;
    readonly honbaSticks: number | null;
}

function winPage(result: RoundEndResult, winner: WinnerResult, viewing: Viewing): WinPageDisplay {
    const { names, hasAkadora } = viewing;
    return {
        doraIndicators: result.doraIndicators.map((tile) => tile136toString(tile, hasAkadora)),
        from: fromPhrase(result, names),
        fromSeat: result.loserSeat,
        hanFu: hanFuLabel(winner),
        hand: resultHand(winner.closedTiles, winner.melds, hasAkadora),
        limit: handLimitName(winner.handResult),
        notes: winNotes(result, winner, names),
        points: winner.handResult.points,
        sticks: winnerSticks(winner, viewing.honbaSticks),
        title: winTitle(result),
        uraIndicators: winner.uraDoraIndicators.map((tile) => tile136toString(tile, hasAkadora)),
        winnerName: names.name(winner.seat),
        winnerSeat: winner.seat,
        winningTile: handTile(winner.winningTile, hasAkadora),
        winningTileLabel:
            result.resultType === ROUND_RESULT_TYPE.TSUMO
                ? t("game.call.tsumo")
                : t("game.call.ron"),
        yaku: yakuLines(winner),
    };
}

function drawSubtitle(draw: DrawResult, names: SeatNames): string | null {
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

function shownHand(
    hand: ShownHandResult,
    names: SeatNames,
    hasAkadora: boolean,
): DrawPageDisplay["hands"][number] {
    return {
        hand: resultHand(hand.closedTiles, hand.melds, hasAkadora),
        name: names.name(hand.seat),
    };
}

function drawPage(draw: DrawResult, names: SeatNames, hasAkadora: boolean): DrawPageDisplay {
    return {
        hands: draw.shownHands.map((hand) => shownHand(hand, names, hasAkadora)),
        kind: "draw",
        subtitle: drawSubtitle(draw, names),
        title: drawName(draw.kind),
    };
}

/** A nagashi mangan made by one seat pays as a mangan tsumo with no honba, so that seat's change is its value. */
function nagashiPage(
    result: RoundEndResult,
    draw: DrawResult,
    names: SeatNames,
): NagashiPageDisplay {
    const [single, ...others] = draw.nagashiSeats;
    return {
        kind: "nagashi",
        limit: t("game.score.mangan"),
        makers: draw.nagashiSeats.map((seat) => names.name(seat)),
        points:
            single === undefined || others.length > 0
                ? null
                : seatEntry(result.scoreChanges, single),
        title: drawName(draw.kind),
    };
}

function resultBody(
    table: RoundEndTable,
    shown: RoundEndPage,
    viewing: Viewing,
): RoundEndDisplayState["body"] {
    const { result } = table;
    if (shown.kind === "win") {
        return {
            kind: "win",
            pages: result.winners.map((winner) => winPage(result, winner, viewing)),
        };
    }
    if (shown.draw.nagashiSeats.length > 0) {
        return nagashiPage(result, shown.draw, viewing.names);
    }
    return drawPage(shown.draw, viewing.names, viewing.hasAkadora);
}

function drawTag(draw: DrawResult, seat: number): string | null {
    if (isAbortiveDraw(draw.kind) || draw.nagashiSeats.length > 0) {
        return null;
    }
    return draw.tenpaiSeats.includes(seat) ? t("game.state.tenpai") : t("game.state.noten");
}

/**
 * The tag a seat's card shows: a liable seat's Pao, or a draw's Tenpai or Noten on a seat its change does not explain
 * (one that moved no points); no tag where every seat would show the same one.
 */
function seatTags(
    table: RoundEndTable,
    index: number,
    changes: readonly number[],
): (string | null)[] {
    const { draw, winners } = table.result;
    const tags = table.players.map(({ seat }) => {
        if (draw === null) {
            return winners[index]?.pao?.seat === seat ? t("game.state.pao") : null;
        }
        return changes[seat] === 0 ? drawTag(draw, seat) : null;
    });
    return tags.every((tag) => tag === tags[0]) ? tags.map(() => null) : tags;
}

/** Each seat's placement at `scores`, ties ranked by seat distance from the game's first dealer. */
function ranks(scores: readonly number[], firstDealerSeat: number): number[] {
    const order = scores
        .map((score, seat) => ({ score, seat }))
        .toSorted(
            (first, second) =>
                second.score - first.score ||
                seatDistance(firstDealerSeat, first.seat) -
                    seatDistance(firstDealerSeat, second.seat),
        )
        .map((entry) => entry.seat);
    return scores.map((_score, seat) => order.indexOf(seat));
}

/** The entry at `index` of a list a seat's index always falls in; one outside it is a client bug. */
function listed<Entry>(list: readonly Entry[], index: number): Entry {
    const entry = list[index];
    if (entry === undefined) {
        throw new Error(`No entry ${index} in a list of ${list.length}`);
    }
    return entry;
}

function role(delta: number): ResultSeat["role"] {
    if (delta > 0) {
        return "gain";
    }
    return delta < 0 ? "loss" : "none";
}

/**
 * Each seat's change on a page and its score after it, in seat order. A double ron's pages settle one winner at a time,
 * so its last page ends at the scores the table settled.
 */
function settledScores(
    { players, result }: RoundEndTable,
    index: number,
): { readonly changes: readonly number[]; readonly after: readonly number[] } {
    const settled = result.winners.slice(0, index + 1);
    const changeMaps =
        settled.length === 0 ? [result.scoreChanges] : settled.map((winner) => winner.scoreChanges);
    const pageChanges = changeMaps.at(-1);
    if (pageChanges === undefined) {
        throw new Error(`A round result has no payments for page ${index}`);
    }
    const seats = players.map(({ seat }) => seat).toSorted((first, second) => first - second);
    return {
        after: seats.map((seat) =>
            changeMaps.reduce(
                (sum, changeMap) => sum + seatEntry(changeMap, seat),
                seatEntry(result.scoresBeforePayment, seat),
            ),
        ),
        changes: seats.map((seat) => seatEntry(pageChanges, seat)),
    };
}

/** Every seat's card at a page, placed as it sits seen from the bottom seat. */
function resultSeats(
    table: RoundEndTable,
    names: SeatNames,
    { bottomSeat, index }: { readonly bottomSeat: number; readonly index: number },
): ResultSeat[] {
    const { after, changes } = settledScores(table, index);
    const placed = ranks(after, table.firstDealerSeat);
    const tags = seatTags(table, index, changes);
    return changes
        .map((delta, seat) => ({
            after: after[seat] ?? 0,
            delta,
            name: names.name(seat),
            position: listed(SEAT_POSITIONS, seatDistance(bottomSeat, seat)),
            rank: t(listed(RANK_NAMES, placed[seat] ?? -1)),
            role: role(delta),
            seat,
            tag: tags[seat] ?? null,
            wind: windLetter(names.wind(seat)),
            windName: windName(names.wind(seat)),
        }))
        .toSorted(
            (first, second) =>
                SEAT_POSITIONS.indexOf(first.position) - SEAT_POSITIONS.indexOf(second.position),
        );
}

function pageNames(result: RoundEndResult, names: SeatNames): string[] {
    if (result.draw !== null) {
        return [drawName(result.draw.kind)];
    }
    return result.winners.map((winner) => names.name(winner.seat));
}

/** Whose each page of a result is, as the buttons between them name it: a winner's name, or the draw's title. */
export function roundEndPageNames(
    table: Pick<RoundEndTable, "players" | "result">,
): readonly string[] {
    return pageNames(table.result, seatNames(table.players, table.result.dealerSeat));
}

/**
 * A round's result at a page, as the result panel shows it: every winner's hand, value and sticks (the page picks
 * which shows), a nagashi mangan's value, or the draw with its tenpai hands; and every seat's change, score and
 * placement through that page, placed as they sit seen from the bottom seat. A double ron has a page per winner
 * (`roundEndPages`); a page out of range shows the nearest.
 */
export function roundEndDisplay(
    table: RoundEndTable,
    view: RoundEndView,
    hasAkadora = true,
): RoundEndDisplayState {
    const { players, result } = table;
    const names = seatNames(players, result.dealerSeat);
    const shown = roundEndPageAt(result, view.page);
    const viewing = { hasAkadora, honbaSticks: table.inStep ? table.honbaSticks : null, names };
    return {
        body: resultBody(table, shown.page, viewing),
        page: shown.index,
        pageCount: shown.count,
        pageNames: pageNames(result, names),
        round: table.inStep
            ? formatRoundName(table.roundWind, table.roundInWind, table.honbaSticks)
            : null,
        seats: resultSeats(table, names, { bottomSeat: view.bottomSeat, index: shown.index }),
    };
}
