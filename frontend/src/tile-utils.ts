// 136-format tile layout
//   Man:    0-35   (4 copies each of 1m-9m)
//   Pin:   36-71   (4 copies each of 1p-9p)
//   Sou:   72-107  (4 copies each of 1s-9s)
//   Honor: 108-135 (4 copies each of 1z-7z)

/** Tile face names matching sprite symbol IDs. */
const TILE_FACES = [
    "1m",
    "2m",
    "3m",
    "4m",
    "5m",
    "0m",
    "6m",
    "7m",
    "8m",
    "9m",
    "1p",
    "2p",
    "3p",
    "4p",
    "5p",
    "0p",
    "6p",
    "7p",
    "8p",
    "9p",
    "1s",
    "2s",
    "3s",
    "4s",
    "5s",
    "0s",
    "6s",
    "7s",
    "8s",
    "9s",
    "1z",
    "2z",
    "3z",
    "4z",
    "5z",
    "6z",
    "7z",
] as const;

type TileFace = (typeof TILE_FACES)[number];
type TileName = TileFace | "back";

// Red five constants (136-format IDs)
const FIVE_RED_MAN = 16;
const FIVE_RED_PIN = 52;
const FIVE_RED_SOU = 88;

const RED_FIVES = new Set([FIVE_RED_MAN, FIVE_RED_PIN, FIVE_RED_SOU]);

const SUITS = ["m", "p", "s"] as const;
const MAX_TILE_ID = 135;

function assertValidTileId(tileId: number): void {
    if (!Number.isInteger(tileId) || tileId < 0 || tileId > MAX_TILE_ID) {
        throw new RangeError(`Invalid tile ID: ${tileId} (expected 0–${MAX_TILE_ID})`);
    }
}

/**
 * Convert a 136-format wire tile ID to a display name.
 *
 * Red fives (aka-dora) are IDs 16, 52, 88 — mapped to "0m", "0p", "0s".
 */
function tile136toString(tileId: number): TileFace {
    assertValidTileId(tileId);

    if (RED_FIVES.has(tileId)) {
        const suit = SUITS[(tileId / 36) | 0];
        return `0${suit}` as TileFace;
    }

    const type34 = (tileId / 4) | 0;

    // Suited tiles (man, pin, sou): type34 0-26
    if (type34 < 27) {
        const suit = SUITS[(type34 / 9) | 0];
        const number = (type34 % 9) + 1;
        return `${number}${suit}` as TileFace;
    }

    // Honor tiles: type34 27-33 -> 1z-7z
    return `${type34 - 26}z` as TileFace;
}

export { tile136toString, TILE_FACES, FIVE_RED_MAN, FIVE_RED_PIN, FIVE_RED_SOU, RED_FIVES };
export type { TileFace, TileName };
