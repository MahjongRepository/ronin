import { updatePlayer } from "@/entities/table/model/helpers";
import {
    type DiscardRecord,
    type MeldRecord,
    type PlayerState,
    type TableState,
} from "@/entities/table/model/types";
import { tile136toString } from "@/entities/tile";
import { type MeldEvent } from "@/shared/protocol";

function markLastDiscardClaimed(discards: DiscardRecord[]): DiscardRecord[] {
    if (discards.length === 0) {
        return discards;
    }
    return discards.map((d, idx) => (idx === discards.length - 1 ? { ...d, claimed: true } : d));
}

function removeTilesFromHand(hand: number[], tilesToRemove: number[]): number[] {
    const result = [...hand];
    for (const tileId of tilesToRemove) {
        const idx = result.indexOf(tileId);
        if (idx === -1) {
            throw new Error(`Tile ${tileId} not found in hand during meld`);
        }
        result.splice(idx, 1);
    }
    return result;
}

function buildMeldRecord(event: MeldEvent): MeldRecord {
    return {
        calledTileId: event.calledTileId,
        callerSeat: event.callerSeat,
        fromSeat: event.fromSeat,
        meldType: event.meldType,
        tileIds: [...event.tileIds],
    };
}

interface CallerUpdate {
    melds: MeldRecord[];
    tiles: number[];
}

function updateCallerWithMeld(
    players: PlayerState[],
    callerSeat: number,
    update: CallerUpdate,
): PlayerState[] {
    return updatePlayer(players, callerSeat, {
        drawnTileId: null,
        melds: update.melds,
        tiles: update.tiles,
    });
}

function markFromSeatDiscard(players: PlayerState[], fromSeat: number | null): PlayerState[] {
    if (fromSeat === null) {
        return players;
    }
    const fromPlayer = players.find((p) => p.seat === fromSeat);
    if (!fromPlayer) {
        throw new Error(`fromSeat player not found for seat ${fromSeat}`);
    }
    return updatePlayer(players, fromSeat, {
        discards: markLastDiscardClaimed(fromPlayer.discards),
    });
}

function applyOpenMeld(state: TableState, event: MeldEvent): TableState {
    const caller = state.players.find((p) => p.seat === event.callerSeat);
    if (!caller) {
        throw new Error(`Caller not found for seat ${event.callerSeat}`);
    }

    const tilesFromHand = event.tileIds.filter((id) => id !== event.calledTileId);
    const callerUpdate: CallerUpdate = {
        melds: [...caller.melds, buildMeldRecord(event)],
        tiles: removeTilesFromHand(caller.tiles, tilesFromHand),
    };
    let players = updateCallerWithMeld(state.players, event.callerSeat, callerUpdate);
    players = markFromSeatDiscard(players, event.fromSeat);

    return { ...state, players };
}

function applyClosedKan(state: TableState, event: MeldEvent): TableState {
    const caller = state.players.find((p) => p.seat === event.callerSeat);
    if (!caller) {
        throw new Error(`Caller not found for seat ${event.callerSeat}`);
    }

    const callerUpdate: CallerUpdate = {
        melds: [...caller.melds, buildMeldRecord(event)],
        tiles: removeTilesFromHand(caller.tiles, event.tileIds),
    };
    return {
        ...state,
        players: updateCallerWithMeld(state.players, event.callerSeat, callerUpdate),
    };
}

/** Find the existing pon matching the event's tile type and derive which tile was added from hand. */
function findPonAndAddedTile(
    caller: PlayerState,
    event: MeldEvent,
): { ponMeld: MeldRecord; addedTileId: number } | null {
    const eventTile34 = event.tileIds.length > 0 ? Math.floor(event.tileIds[0] / 4) : -1;
    const ponMeld = caller.melds.find(
        (m) =>
            m.meldType === "pon" &&
            m.tileIds.length > 0 &&
            Math.floor(m.tileIds[0] / 4) === eventTile34,
    );
    if (!ponMeld) {
        return null;
    }
    const ponTileSet = new Set(ponMeld.tileIds);
    const addedTileId = event.tileIds.find((id) => !ponTileSet.has(id));
    if (addedTileId === undefined) {
        return null;
    }
    return { addedTileId, ponMeld };
}

function applyAddedKan(state: TableState, event: MeldEvent): TableState {
    const caller = state.players.find((p) => p.seat === event.callerSeat);
    if (!caller) {
        throw new Error(`Caller not found for seat ${event.callerSeat}`);
    }

    const match = findPonAndAddedTile(caller, event);
    if (!match) {
        throw new Error(`No matching pon found for added_kan at seat ${event.callerSeat}`);
    }

    const updatedMelds = caller.melds.map((m): MeldRecord => {
        if (m === match.ponMeld) {
            return {
                addedTileId: match.addedTileId,
                calledTileId: event.calledTileId,
                callerSeat: event.callerSeat,
                fromSeat: event.fromSeat,
                meldType: event.meldType,
                tileIds: [...event.tileIds],
            };
        }
        return m;
    });

    const callerUpdate: CallerUpdate = {
        melds: updatedMelds,
        tiles: removeTilesFromHand(caller.tiles, [match.addedTileId]),
    };
    return {
        ...state,
        players: updateCallerWithMeld(state.players, event.callerSeat, callerUpdate),
    };
}

function meldDescription(state: TableState, event: MeldEvent): string {
    const caller = state.players.find((p) => p.seat === event.callerSeat);
    const tileName = event.calledTileId !== null ? tile136toString(event.calledTileId) : "unknown";
    return `${caller?.name ?? `Seat ${event.callerSeat}`} called ${event.meldType} on ${tileName}`;
}

export function applyMeld(state: TableState, event: MeldEvent): TableState {
    const nextState = applyMeldByType(state, event);
    return {
        ...nextState,
        currentPlayerSeat: event.callerSeat,
        lastEventDescription: meldDescription(state, event),
    };
}

function applyMeldByType(state: TableState, event: MeldEvent): TableState {
    switch (event.meldType) {
        case "chi":
        case "pon":
        case "open_kan":
            return applyOpenMeld(state, event);
        case "closed_kan":
            return applyClosedKan(state, event);
        case "added_kan":
            return applyAddedKan(state, event);
        default: {
            const _exhaustive: never = event.meldType;
            throw new Error(`Unhandled meld type: ${String(_exhaustive)}`);
        }
    }
}
