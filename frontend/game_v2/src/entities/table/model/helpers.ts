import { tileType } from "@/shared/protocol";

import { DesyncError } from "./desync-error";
import { type MeldRecord, type PlayerState, type TableState } from "./types";

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
        throw new DesyncError(`No player found for seat ${seat}`);
    }
    return player;
}

/**
 * A seat's entry in a server score map (`scores`, `scoreChanges`), which names every seat: a map lacking the seat is an
 * impossible state.
 */
export function seatEntry(map: Readonly<Record<string, number>>, seat: number): number {
    const entry = map[String(seat)];
    if (entry === undefined) {
        throw new DesyncError(`A score map names no entry for seat ${seat}`);
    }
    return entry;
}

/** The game's riichi stick value; a win collecting sticks on a table that never learned it is an impossible state. */
export function requireRiichiStickValue(context: Pick<TableState, "riichiStickValue">): number {
    if (context.riichiStickValue === null) {
        throw new DesyncError("The table holds no riichi stick value");
    }
    return context.riichiStickValue;
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

/** A seat's pon of a tile type, which an added kan of the type raises, or undefined. */
export function ponOfType(melds: readonly MeldRecord[], type: number): MeldRecord | undefined {
    return melds.find((meld) => meld.meldType === "pon" && tileType(meld.tileIds[0]) === type);
}
