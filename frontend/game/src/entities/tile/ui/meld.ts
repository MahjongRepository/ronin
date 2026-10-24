import { html } from "lit-html";

import { type TileFace, tile136toString } from "@/entities/tile/lib/tile-utils";
import { type MeldType } from "@/shared/protocol/constants";

import { Tile } from "./tile";

interface MeldInput {
    tileIds: number[];
    meldType: MeldType;
    callerSeat: number;
    fromSeat: number | null;
    calledTileId: number | null;
    addedTileId?: number;
}

type MeldTileDisplay =
    | { kind: "upright"; face: TileFace }
    | { kind: "sideways"; face: TileFace }
    | { kind: "facedown"; face: TileFace }
    | { kind: "stacked"; bottom: TileFace; top: TileFace };

/**
 * Sideways tile position based on relative seat distance.
 * (fromSeat - callerSeat + 4) % 4 gives: 1=kamicha(left), 2=toimen(center), 3=shimocha(right)
 * Subtract 1 to get 0-based index: 0=left, 1=center, 2=right.
 */
function sidewaysPosition(callerSeat: number, fromSeat: number): number {
    return ((fromSeat - callerSeat + 4) % 4) - 1;
}

function chiToDisplay(input: MeldInput): MeldTileDisplay[] {
    const sorted = [...input.tileIds].sort((tileA, tileB) => ((tileA / 4) | 0) - ((tileB / 4) | 0));
    return sorted.map((tileId) => ({
        face: tile136toString(tileId),
        kind: tileId === input.calledTileId ? "sideways" : "upright",
    }));
}

function openMeldToDisplay(input: MeldInput, tileCount: number): MeldTileDisplay[] {
    if (input.fromSeat === null || input.calledTileId === null) {
        throw new Error(`fromSeat and calledTileId are required for ${input.meldType}`);
    }
    const pos = sidewaysPosition(input.callerSeat, input.fromSeat);
    const calledId = input.calledTileId;
    const otherTiles = input.tileIds.filter((id) => id !== calledId);
    let otherIdx = 0;
    return Array.from(
        { length: tileCount },
        (_unused, idx): MeldTileDisplay =>
            idx === pos
                ? { face: tile136toString(calledId), kind: "sideways" }
                : { face: tile136toString(otherTiles[otherIdx++]), kind: "upright" },
    );
}

function closedKanToDisplay(input: MeldInput): MeldTileDisplay[] {
    return input.tileIds.map((tileId, idx) => {
        const face = tile136toString(tileId);
        if (idx === 0 || idx === 3) {
            return { face, kind: "facedown" as const };
        }
        return { face, kind: "upright" as const };
    });
}

function addedKanToDisplay(input: MeldInput): MeldTileDisplay[] {
    if (input.fromSeat === null || input.calledTileId === null || input.addedTileId === undefined) {
        throw new Error("fromSeat, calledTileId, and addedTileId are required for added_kan");
    }
    const pos = sidewaysPosition(input.callerSeat, input.fromSeat);
    const calledId = input.calledTileId;
    const addedId = input.addedTileId;
    const otherTiles = input.tileIds.filter((id) => id !== addedId && id !== calledId);
    let otherIdx = 0;
    return Array.from(
        { length: 3 },
        (_unused, idx): MeldTileDisplay =>
            idx === pos
                ? {
                      bottom: tile136toString(calledId),
                      kind: "stacked",
                      top: tile136toString(addedId),
                  }
                : { face: tile136toString(otherTiles[otherIdx++]), kind: "upright" },
    );
}

// If meldType is "added_kan" but addedTileId is undefined, fall back to open_kan rendering.
// This handles the IMME decode path where addedTileId is not available.
function inputToDisplay(input: MeldInput): MeldTileDisplay[] {
    switch (input.meldType) {
        case "chi":
            return chiToDisplay(input);
        case "pon":
            return openMeldToDisplay(input, 3);
        case "open_kan":
            return openMeldToDisplay(input, 4);
        case "closed_kan":
            return closedKanToDisplay(input);
        case "added_kan":
            if (input.addedTileId === undefined) {
                return openMeldToDisplay({ ...input, meldType: "open_kan" }, 4);
            }
            return addedKanToDisplay(input);
    }
}

function MeldTile(tile: MeldTileDisplay) {
    switch (tile.kind) {
        case "upright":
            return html`<span class="meld-tile">${Tile(tile.face, "face")}</span>`;
        case "sideways":
            return html`<span class="meld-tile meld-tile-sideways">${Tile(tile.face, "face")}</span>`;
        case "facedown":
            return html`<span class="meld-tile">${Tile(tile.face, "back")}</span>`;
        case "stacked":
            return html`<span class="meld-tile meld-tile-stacked">
                <span class="meld-tile-stacked-bottom meld-tile-sideways">${Tile(tile.bottom, "face")}</span>
                <span class="meld-tile-stacked-top meld-tile-sideways">${Tile(tile.top, "face")}</span>
            </span>`;
    }
}

function Meld(input: MeldInput) {
    const tiles = inputToDisplay(input);
    return html`<span class="meld">${tiles.map(MeldTile)}</span>`;
}

export { Meld };
export type { MeldInput };
