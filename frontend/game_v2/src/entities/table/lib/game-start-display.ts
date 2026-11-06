import { formatPoints } from "@/entities/table/lib/round-end-display";
import { formatRoundName, roundName } from "@/entities/table/lib/round-name";
import { windLetter, windName } from "@/entities/table/lib/wind-name";
import { type TableState } from "@/entities/table/model/types";
import { GAME_TYPE, type GameType, WIND, seatDistance } from "@/shared/protocol";

export const GAME_TYPE_NAMES: Readonly<Record<GameType, string>> = {
    [GAME_TYPE.HANCHAN]: "Hanchan",
    [GAME_TYPE.TONPUSEN]: "Tonpuu",
};

/** A seat at the table: its seat wind, its player, and whether it deals, is the viewer's or AI. */
export interface GameStartSeat {
    readonly wind: string;
    readonly windName: string;
    readonly name: string;
    readonly isDealer: boolean;
    readonly isViewer: boolean;
    readonly isAiPlayer: boolean;
    /** The seat's score where the view knows it (a dealt round's, a replay's first deal's); else null. */
    readonly score: string | null;
}

/** The seating: the game's length where known, the round, and the seats in wind order. */
export interface GameStartDisplayState {
    readonly gameType: string | null;
    readonly round: string;
    readonly seats: readonly GameStartSeat[];
}

/** Whose seating a view reads: the round's dealer (East), the viewer's seat, and whether the scores show. */
interface SeatingView {
    readonly dealer: number;
    readonly viewerSeat: number | null;
    readonly scored: boolean;
}

/** The seats in wind order from the dealer's seat round, each scored where the view shows scores. */
function seatsInWindOrder(
    table: TableState,
    { dealer, scored, viewerSeat }: SeatingView,
): GameStartSeat[] {
    function windOf(seat: number): number {
        return seatDistance(dealer, seat);
    }
    return table.players
        .toSorted((first, second) => windOf(first.seat) - windOf(second.seat))
        .map((player) => ({
            isAiPlayer: player.isAiPlayer,
            isDealer: player.seat === dealer,
            isViewer: player.seat === viewerSeat,
            name: player.name,
            score: scored ? formatPoints(player.score) : null,
            wind: windLetter(windOf(player.seat)),
            windName: windName(windOf(player.seat)),
        }));
}

function gameTypeName(table: TableState): string | null {
    return table.gameType === null ? null : GAME_TYPE_NAMES[table.gameType];
}

/**
 * The seating of the round on a live table from the viewer's seat: once dealt, the round with its honba, the seats in
 * wind order from its dealer and their scores now; before the first deal, the first round from the first dealer, with
 * no score, since the game's start names none.
 */
export function tableSeatingDisplay(
    table: TableState,
    viewerSeat: number | null,
): GameStartDisplayState {
    const dealt = table.phase !== "pre_game";
    return {
        gameType: gameTypeName(table),
        round: dealt
            ? formatRoundName(table.roundWind, table.roundInWind, table.honbaSticks)
            : roundName(WIND.EAST, 1),
        seats: seatsInWindOrder(table, {
            dealer: dealt ? table.dealerSeat : table.firstDealerSeat,
            scored: dealt,
            viewerSeat,
        }),
    };
}

/**
 * The seating a replay opens on, from its table as the game started at its first deal's scores: each seat's starting
 * score shown, no seat the reader's.
 */
export function replaySeatingDisplay(table: TableState): GameStartDisplayState {
    return {
        gameType: gameTypeName(table),
        round: roundName(WIND.EAST, 1),
        seats: seatsInWindOrder(table, {
            dealer: table.firstDealerSeat,
            scored: true,
            viewerSeat: null,
        }),
    };
}
