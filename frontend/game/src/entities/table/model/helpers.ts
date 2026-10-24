import { type PlayerState } from "./types";

/**
 * Returns a new players array with the player at the given seat updated.
 */
export function updatePlayer(
    players: PlayerState[],
    seat: number,
    update: Partial<PlayerState>,
): PlayerState[] {
    return players.map((p) => (p.seat === seat ? { ...p, ...update } : p));
}
