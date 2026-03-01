import { NUM_TILES, SEAT_TILE_SPACE } from "@/shared/protocol/constants";

export interface DecodedDraw {
    seat: number;
    tileId: number;
}

export function decodeDraw(packed: number): DecodedDraw {
    if (!Number.isInteger(packed) || packed < 0 || packed >= SEAT_TILE_SPACE) {
        throw new RangeError(`Draw packed value must be 0-${SEAT_TILE_SPACE - 1}, got ${packed}`);
    }
    const seat = Math.trunc(packed / NUM_TILES);
    const tileId = packed % NUM_TILES;
    return { seat, tileId };
}
