import { type MeldType, seatDistance, tileType } from "@/shared/protocol";

import { type TileFace, tile136toString } from "./tile-utils";

interface MeldInputBase {
    readonly tileIds: readonly number[];
    readonly callerSeat: number;
    readonly fromSeat: number | null;
    readonly calledTileId: number | null;
}

/**
 * A meld as the table records it: its tile ids, who called it from whom, and which tile was called, and for an added
 * kan which tile was added from hand.
 */
export type MeldInput =
    | (MeldInputBase & {
          readonly meldType: Exclude<MeldType, "added_kan">;
          readonly addedTileId?: never;
      })
    | (MeldInputBase & { readonly meldType: "added_kan"; readonly addedTileId: number });

/**
 * A tile of a meld as it is laid: upright, sideways (the called tile, turned toward the seat it came from), face
 * down (a closed kan's ends), or an added kan's called tile with the added one stacked on it.
 */
export type MeldTile =
    | { readonly kind: "upright" | "sideways" | "facedown"; readonly face: TileFace }
    | { readonly kind: "stacked"; readonly bottom: TileFace; readonly top: TileFace };

/**
 * The slot of the sideways tile among `slotCount`, turned toward the seat it came from. Play runs to the caller's
 * right, so the feeder's distance from the caller is 1 for shimocha (right: the last slot), 2 for toimen (the middle:
 * slot 1, also of a four-tile kan) and 3 for kamicha (left: the first slot).
 */
function sidewaysPosition(callerSeat: number, fromSeat: number, slotCount: number): number {
    const distance = seatDistance(callerSeat, fromSeat);
    return distance === 1 ? slotCount - 1 : 3 - distance;
}

/** A chi is always fed by kamicha: its called tile sideways at the left, the other two in order after it. */
function chiTiles(input: MeldInput): MeldTile[] {
    const calledId = input.calledTileId;
    if (calledId === null || !input.tileIds.includes(calledId)) {
        throw new Error("calledTileId is required for chi and must be one of its tiles");
    }
    const others = input.tileIds
        .filter((tileId) => tileId !== calledId)
        .toSorted((tileA, tileB) => tileType(tileA) - tileType(tileB));
    return [
        { face: tile136toString(calledId), kind: "sideways" },
        ...others.map((tileId): MeldTile => ({ face: tile136toString(tileId), kind: "upright" })),
    ];
}

function openMeldTiles(input: MeldInput, tileCount: number): MeldTile[] {
    if (input.fromSeat === null || input.calledTileId === null) {
        throw new Error(`fromSeat and calledTileId are required for ${input.meldType}`);
    }
    const pos = sidewaysPosition(input.callerSeat, input.fromSeat, tileCount);
    const calledId = input.calledTileId;
    const otherTiles = input.tileIds.filter((id) => id !== calledId);
    let otherIdx = 0;
    return Array.from({ length: tileCount }, (_unused, idx): MeldTile =>
        idx === pos
            ? { face: tile136toString(calledId), kind: "sideways" }
            : { face: tile136toString(otherTiles[otherIdx++]), kind: "upright" },
    );
}

function closedKanTiles(input: MeldInput): MeldTile[] {
    return input.tileIds.map((tileId, idx) => ({
        face: tile136toString(tileId),
        kind: idx === 0 || idx === 3 ? "facedown" : "upright",
    }));
}

function addedKanTiles(input: MeldInput & { readonly meldType: "added_kan" }): MeldTile[] {
    if (input.fromSeat === null || input.calledTileId === null) {
        throw new Error("fromSeat and calledTileId are required for added_kan");
    }
    const pos = sidewaysPosition(input.callerSeat, input.fromSeat, 3);
    const calledId = input.calledTileId;
    const addedId = input.addedTileId;
    const otherTiles = input.tileIds.filter((id) => id !== addedId && id !== calledId);
    let otherIdx = 0;
    return Array.from({ length: 3 }, (_unused, idx): MeldTile =>
        idx === pos
            ? { bottom: tile136toString(calledId), kind: "stacked", top: tile136toString(addedId) }
            : { face: tile136toString(otherTiles[otherIdx++]), kind: "upright" },
    );
}

/** The tiles a meld is laid as, left to right. */
export function meldTiles(input: MeldInput): MeldTile[] {
    switch (input.meldType) {
        case "chi": {
            return chiTiles(input);
        }
        case "pon": {
            return openMeldTiles(input, 3);
        }
        case "open_kan": {
            return openMeldTiles(input, 4);
        }
        case "closed_kan": {
            return closedKanTiles(input);
        }
        case "added_kan": {
            return addedKanTiles(input);
        }
    }
}
