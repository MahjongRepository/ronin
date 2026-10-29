import { type PlayerState, type TableState } from "./types";

/** A closed hand of 3n+1 tiles waits for a draw; one of 3n+2 holds its turn's draw. */
const TILES_PER_SET = 3;
const HAND_AWAITING_DRAW = 1;

type ClosedHand = Pick<PlayerState, "tiles" | "concealedCount">;

/**
 * Returns a new players array with the player at the given seat updated.
 */
export function updatePlayer(
    players: readonly PlayerState[],
    seat: number,
    update: Partial<PlayerState>,
): PlayerState[] {
    return players.map((p) => (p.seat === seat ? { ...p, ...update } : p));
}

/** The player at `seat`; a table event naming a seat the table does not hold is an impossible state. */
export function requirePlayer(state: TableState, seat: number): PlayerState {
    const player = state.players.find((p) => p.seat === seat);
    if (!player) {
        throw new Error(`No player found for seat ${seat}`);
    }
    return player;
}

/**
 * Whether a seat about to discard or declare its own kan drew a tile this view never saw: its hand still waits for
 * a draw, and holds concealed tiles, so it is another seat's hand, whose draws go only to that seat.
 */
export function drewUnseen(player: PlayerState): boolean {
    const size = player.tiles.length + player.concealedCount;
    return player.concealedCount > 0 && size % TILES_PER_SET === HAND_AWAITING_DRAW;
}

/**
 * Take tiles out of a closed hand: a tile the view knows leaves `tiles`, any other leaves the concealed count.
 * Returns null when the hand holds neither, an impossible state the caller reports.
 */
export function takeFromHand(hand: ClosedHand, tileIds: readonly number[]): ClosedHand | null {
    const tiles = [...hand.tiles];
    let { concealedCount } = hand;
    for (const tileId of tileIds) {
        const index = tiles.indexOf(tileId);
        if (index !== -1) {
            tiles.splice(index, 1);
        } else if (concealedCount > 0) {
            concealedCount -= 1;
        } else {
            return null;
        }
    }
    return { concealedCount, tiles };
}
