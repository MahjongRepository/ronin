import { formatPoints } from "@/entities/table/lib/round-end-display";
import { roundName } from "@/entities/table/lib/round-name";
import { windLetter, windName } from "@/entities/table/lib/wind-name";
import { type TableState } from "@/entities/table/model/types";
import { GAME_TYPE, type GameType, WIND, seatDistance } from "@/shared/protocol";

export const GAME_TYPE_NAMES: Readonly<Record<GameType, string>> = {
    [GAME_TYPE.HANCHAN]: "Hanchan",
    [GAME_TYPE.TONPUSEN]: "Tonpuu",
};

/** How the view shows the seating: the seat it is read from (none in a replay) and the seconds to the first deal. */
export interface GameStartView {
    readonly viewerSeat: number | null;
    /** The whole seconds left of the server's game start pause; null when unknown or run out. */
    readonly secondsLeft: number | null;
}

/** A seat at the table before the first deal: its seat wind, its player, and whether it deals, is the viewer's or AI. */
export interface GameStartSeat {
    readonly wind: string;
    readonly windName: string;
    readonly name: string;
    readonly isDealer: boolean;
    readonly isViewer: boolean;
    readonly isAiPlayer: boolean;
    /** The seat's starting score where the view knows it (a replay, from its first deal); else null. */
    readonly score: string | null;
}

/** The seating before the first deal: the game's length, its first round, the seats in wind order and when it deals. */
export interface GameStartDisplayState {
    readonly gameType: string | null;
    readonly round: string;
    readonly seats: readonly GameStartSeat[];
    /** The countdown to the first deal; null in a replay, which waits for its reader instead. */
    readonly status: string | null;
}

function startStatus(secondsLeft: number | null): string {
    return secondsLeft === null ? "Starting…" : `Starting in ${secondsLeft}`;
}

/** The seats in wind order from the first dealer's seat round (the dealer is East), each scored where `scored`. */
function seatsInWindOrder(
    table: TableState,
    viewerSeat: number | null,
    scored: boolean,
): GameStartSeat[] {
    const dealer = table.firstDealerSeat;
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
 * The seating a started game shows until its first deal, its seats in wind order. Its status counts the server's game
 * start pause down, or only says the game is starting where no pause is known. No score shows: the game's start
 * names none.
 */
export function gameStartDisplay(table: TableState, view: GameStartView): GameStartDisplayState {
    return {
        gameType: gameTypeName(table),
        round: roundName(WIND.EAST, 1),
        seats: seatsInWindOrder(table, view.viewerSeat, false),
        status: startStatus(view.secondsLeft),
    };
}

/**
 * The seating a replay opens on, from its table as the game started at its first deal's scores: each seat's starting
 * score shown, no seat the reader's, and no countdown.
 */
export function replaySeatingDisplay(table: TableState): GameStartDisplayState {
    return {
        gameType: gameTypeName(table),
        round: roundName(WIND.EAST, 1),
        seats: seatsInWindOrder(table, null, true),
        status: null,
    };
}
