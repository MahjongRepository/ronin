import { tileType } from "@/shared/protocol";

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

const FIVE_RED_MAN = 16;
const FIVE_RED_PIN = 52;
const FIVE_RED_SOU = 88;

/** The red fives (aka-dora) by their 136-format ids, each its own face. */
const RED_FIVE_FACES: ReadonlyMap<number, TileFace> = new Map([
    [FIVE_RED_MAN, "0m"],
    [FIVE_RED_PIN, "0p"],
    [FIVE_RED_SOU, "0s"],
]);

const RED_FIVES: ReadonlySet<number> = new Set(RED_FIVE_FACES.keys());

/** Every tile type's face by its 34-format index: the suits' 1 to 9, then the honors, no red five among them. */
const TYPE_FACES: readonly TileFace[] = TILE_FACES.filter((face) => !face.startsWith("0"));

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
function tile136toString(tileId: number, hasAkadora = true): TileFace {
    assertValidTileId(tileId);
    return (hasAkadora ? RED_FIVE_FACES.get(tileId) : undefined) ?? TYPE_FACES[tileType(tileId)];
}

const HONOR_NAMES = [
    "East",
    "South",
    "West",
    "North",
    "White dragon",
    "Green dragon",
    "Red dragon",
] as const;

/** A tile as a sentence names it: "5m", "red 5p", "East", "White dragon". */
function tileName(tileId: number): string {
    const face = tile136toString(tileId);
    const rank = face.charAt(0);
    const suit = face.charAt(1);
    if (suit === "z") {
        return HONOR_NAMES[Number(rank) - 1];
    }
    return rank === "0" ? `red 5${suit}` : face;
}

export {
    tile136toString,
    tileName,
    TILE_FACES,
    FIVE_RED_MAN,
    FIVE_RED_PIN,
    FIVE_RED_SOU,
    RED_FIVES,
};
export type { TileFace };
