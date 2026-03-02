import { type MeldRecord } from "@/entities/table/model/types";
import { type MeldTileDisplay, tile136toString } from "@/entities/tile";

/**
 * Sideways tile position based on relative seat distance.
 * (fromSeat - callerSeat + 4) % 4 gives: 1=kamicha(left), 2=toimen(center), 3=shimocha(right)
 * Subtract 1 to get 0-based index: 0=left, 1=center, 2=right.
 */
function sidewaysPosition(callerSeat: number, fromSeat: number): number {
    return ((fromSeat - callerSeat + 4) % 4) - 1;
}

function chiToDisplay(meld: MeldRecord): MeldTileDisplay[] {
    const sorted = [...meld.tileIds].sort((tileA, tileB) => ((tileA / 4) | 0) - ((tileB / 4) | 0));
    return sorted.map((tileId) => ({
        face: tile136toString(tileId),
        kind: tileId === meld.calledTileId ? "sideways" : "upright",
    }));
}

function openMeldToDisplay(meld: MeldRecord, tileCount: number): MeldTileDisplay[] {
    const pos = sidewaysPosition(meld.callerSeat, meld.fromSeat!);
    const otherTiles = meld.tileIds.filter((id) => id !== meld.calledTileId);

    const result: MeldTileDisplay[] = [];
    let otherIdx = 0;
    for (let idx = 0; idx < tileCount; idx++) {
        if (idx === pos) {
            result.push({ face: tile136toString(meld.calledTileId!), kind: "sideways" });
        } else {
            result.push({ face: tile136toString(otherTiles[otherIdx++]), kind: "upright" });
        }
    }
    return result;
}

function closedKanToDisplay(meld: MeldRecord): MeldTileDisplay[] {
    return meld.tileIds.map((tileId, idx) => {
        const face = tile136toString(tileId);
        if (idx === 0 || idx === 3) {
            return { face, kind: "facedown" as const };
        }
        return { face, kind: "upright" as const };
    });
}

function addedKanToDisplay(meld: MeldRecord): MeldTileDisplay[] {
    const pos = sidewaysPosition(meld.callerSeat, meld.fromSeat!);
    const otherTiles = meld.tileIds.filter(
        (id) => id !== meld.addedTileId && id !== meld.calledTileId,
    );

    const result: MeldTileDisplay[] = [];
    let otherIdx = 0;
    for (let idx = 0; idx < 3; idx++) {
        if (idx === pos) {
            result.push({
                bottom: tile136toString(meld.calledTileId!),
                kind: "stacked",
                top: tile136toString(meld.addedTileId!),
            });
        } else {
            result.push({ face: tile136toString(otherTiles[otherIdx++]), kind: "upright" });
        }
    }
    return result;
}

export function meldToDisplay(meld: MeldRecord): MeldTileDisplay[] {
    switch (meld.meldType) {
        case "chi":
            return chiToDisplay(meld);
        case "pon":
            return openMeldToDisplay(meld, 3);
        case "open_kan":
            return openMeldToDisplay(meld, 4);
        case "closed_kan":
            return closedKanToDisplay(meld);
        case "added_kan":
            return addedKanToDisplay(meld);
        default: {
            const _exhaustive: never = meld.meldType;
            throw new Error(`Unhandled meld type: ${String(_exhaustive)}`);
        }
    }
}
