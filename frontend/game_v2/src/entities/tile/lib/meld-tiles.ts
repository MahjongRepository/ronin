import { type MeldType } from "@/shared/protocol/constants";

import { type TileFace, tile136toString } from "./tile-utils";

/** A meld as the table records it: its tile ids, who called it from whom, and which tile was called or added. */
export interface MeldInput {
    readonly tileIds: readonly number[];
    readonly meldType: MeldType;
    readonly callerSeat: number;
    readonly fromSeat: number | null;
    readonly calledTileId: number | null;
    readonly addedTileId?: number;
}

/**
 * A tile of a meld as it is laid: upright, sideways (the called tile, turned toward the seat it came from), face
 * down (a closed kan's ends), or an added kan's called tile with the added one stacked on it.
 */
export type MeldTile =
    | { readonly kind: "upright" | "sideways" | "facedown"; readonly face: TileFace }
    | { readonly kind: "stacked"; readonly bottom: TileFace; readonly top: TileFace };

/**
 * Sideways tile position based on relative seat distance: (fromSeat - callerSeat + 4) % 4 is 1 for kamicha (left),
 * 2 for toimen (centre), 3 for shimocha (right), so one less is the 0-based slot.
 */
function sidewaysPosition(callerSeat: number, fromSeat: number): number {
    return ((fromSeat - callerSeat + 4) % 4) - 1;
}

function chiTiles(input: MeldInput): MeldTile[] {
    const sorted = input.tileIds.toSorted((tileA, tileB) => ((tileA / 4) | 0) - ((tileB / 4) | 0));
    return sorted.map((tileId) => ({
        face: tile136toString(tileId),
        kind: tileId === input.calledTileId ? "sideways" : "upright",
    }));
}

function openMeldTiles(input: MeldInput, tileCount: number): MeldTile[] {
    if (input.fromSeat === null || input.calledTileId === null) {
        throw new Error(`fromSeat and calledTileId are required for ${input.meldType}`);
    }
    const pos = sidewaysPosition(input.callerSeat, input.fromSeat);
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

function addedKanTiles(input: MeldInput, addedId: number): MeldTile[] {
    if (input.fromSeat === null || input.calledTileId === null) {
        throw new Error("fromSeat and calledTileId are required for added_kan");
    }
    const pos = sidewaysPosition(input.callerSeat, input.fromSeat);
    const calledId = input.calledTileId;
    const otherTiles = input.tileIds.filter((id) => id !== addedId && id !== calledId);
    let otherIdx = 0;
    return Array.from({ length: 3 }, (_unused, idx): MeldTile =>
        idx === pos
            ? { bottom: tile136toString(calledId), kind: "stacked", top: tile136toString(addedId) }
            : { face: tile136toString(otherTiles[otherIdx++]), kind: "upright" },
    );
}

/**
 * The tiles a meld is laid as, left to right. An added kan whose added tile is unknown (the compact meld encoding
 * a round end carries does not name it) is laid as an open kan.
 */
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
            return input.addedTileId === undefined
                ? openMeldTiles({ ...input, meldType: "open_kan" }, 4)
                : addedKanTiles(input, input.addedTileId);
        }
    }
}
