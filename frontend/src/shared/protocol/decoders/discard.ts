import { NUM_DISCARD_FLAGS, NUM_TILES, SEAT_TILE_SPACE } from "../constants";

const MAX_DISCARD = NUM_DISCARD_FLAGS * SEAT_TILE_SPACE - 1; // 2175

export interface DecodedDiscard {
    isRiichi: boolean;
    isTsumogiri: boolean;
    seat: number;
    tileId: number;
}

export function decodeDiscard(packed: number): DecodedDiscard {
    if (!Number.isInteger(packed) || packed < 0 || packed > MAX_DISCARD) {
        throw new RangeError(`Discard packed value must be 0-${MAX_DISCARD}, got ${packed}`);
    }
    const flag = Math.trunc(packed / SEAT_TILE_SPACE);
    const remainder = packed % SEAT_TILE_SPACE;
    const seat = Math.trunc(remainder / NUM_TILES);
    const tileId = remainder % NUM_TILES;
    const isTsumogiri = (flag & 0b01) !== 0;
    const isRiichi = (flag & 0b10) !== 0;
    return { isRiichi, isTsumogiri, seat, tileId };
}
