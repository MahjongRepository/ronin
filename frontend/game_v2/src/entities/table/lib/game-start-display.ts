import { roundName } from "@/entities/table/lib/round-name";
import { windLetter, windName } from "@/entities/table/lib/wind-name";
import { type TableState } from "@/entities/table/model/types";
import { GAME_TYPE, type GameType, WIND, seatDistance } from "@/shared/protocol";

const GAME_TYPE_NAMES: Readonly<Record<GameType, string>> = {
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
}

/** The seating before the first deal: the game's length, its first round, the seats in wind order and when it deals. */
export interface GameStartDisplayState {
    readonly gameType: string | null;
    readonly round: string;
    readonly seats: readonly GameStartSeat[];
    readonly status: string;
}

function startStatus(secondsLeft: number | null): string {
    return secondsLeft === null ? "Starting…" : `Starting in ${secondsLeft}`;
}

/**
 * The seating a started game shows until its first deal, from the first dealer's seat round: the dealer is East. Its
 * status counts the server's game start pause down, or only says the game is starting where no pause is known.
 */
export function gameStartDisplay(table: TableState, view: GameStartView): GameStartDisplayState {
    const dealer = table.firstDealerSeat;
    function windOf(seat: number): number {
        return seatDistance(dealer, seat);
    }
    const seats = table.players
        .toSorted((first, second) => windOf(first.seat) - windOf(second.seat))
        .map((player) => ({
            isAiPlayer: player.isAiPlayer,
            isDealer: player.seat === dealer,
            isViewer: player.seat === view.viewerSeat,
            name: player.name,
            wind: windLetter(windOf(player.seat)),
            windName: windName(windOf(player.seat)),
        }));
    return {
        gameType: table.gameType === null ? null : GAME_TYPE_NAMES[table.gameType],
        round: roundName(WIND.EAST, 1),
        seats,
        status: startStatus(view.secondsLeft),
    };
}
