import { NUM_PLAYERS } from "./constants";

/** The copies of each tile type in the wall: a tile id is its type's first id plus its copy. */
const COPIES_PER_TILE_TYPE = 4;

/** A wire tile id's type, 0 to 33: the four copies of a tile share it. */
export function tileType(tileId: number): number {
    return Math.floor(tileId / COPIES_PER_TILE_TYPE);
}

/** Every tile id of a type: a kan's four tiles. */
export function tileTypeCopies(type: number): number[] {
    const first = type * COPIES_PER_TILE_TYPE;
    return Array.from({ length: COPIES_PER_TILE_TYPE }, (_unused, copy) => first + copy);
}

/** How many seats on from `fromSeat` `toSeat` sits, in turn order: 0 for itself, 1 for the next seat. */
export function seatDistance(fromSeat: number, toSeat: number): number {
    return (toSeat - fromSeat + NUM_PLAYERS) % NUM_PLAYERS;
}
