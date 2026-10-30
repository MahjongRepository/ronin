import { DesyncError } from "@/entities/table/model/desync-error";
import { ponOfType, takeFromHand, updatePlayer } from "@/entities/table/model/helpers";
import {
    type DiscardRecord,
    type MeldRecord,
    type PlayerState,
    type TableState,
} from "@/entities/table/model/types";
import { type MeldEvent, tileType } from "@/shared/protocol";

import { shownKanIndex } from "./kan-declared";

function buildMeldRecord(event: MeldEvent, addedTileId?: number): MeldRecord {
    const record: MeldRecord = {
        calledTileId: event.calledTileId,
        callerSeat: event.callerSeat,
        fromSeat: event.fromSeat,
        meldType: event.meldType,
        tileIds: [...event.tileIds],
    };
    return addedTileId === undefined ? record : { ...record, addedTileId };
}

/** The caller's melds once the meld lands, and the tiles it takes from the caller's hand. */
interface MeldMove {
    readonly melds: readonly MeldRecord[];
    readonly fromHand: readonly number[];
}

function findCaller(state: TableState, event: MeldEvent): PlayerState {
    const caller = state.players.find((p) => p.seat === event.callerSeat);
    if (!caller) {
        throw new DesyncError(`Caller not found for seat ${event.callerSeat}`);
    }
    return caller;
}

/** Move the caller's tiles from hand into its melds. */
function meldFromHand(
    state: TableState,
    event: MeldEvent,
    { fromHand, melds }: MeldMove,
): TableState {
    const caller = findCaller(state, event);
    const hand = takeFromHand(caller, fromHand);
    if (hand === null) {
        throw new DesyncError(`Tiles ${fromHand.join(", ")} not found in hand during meld`);
    }
    return {
        ...state,
        players: updatePlayer(state.players, event.callerSeat, {
            concealedCount: hand.concealedCount,
            drawnConcealed: false,
            drawnTileId: null,
            melds,
            tiles: hand.tiles,
        }),
    };
}

/** The discard a call takes: the table's latest, from the discarder's river, unclaimed and the called tile. */
function requireCalledDiscard(
    state: TableState,
    fromPlayer: PlayerState,
    calledTileId: number | null,
): DiscardRecord {
    const latest = fromPlayer.discards.at(-1);
    const isCalled =
        state.lastDiscardSeat === fromPlayer.seat &&
        latest !== undefined &&
        !latest.claimed &&
        latest.tileId === calledTileId;
    if (!isCalled) {
        throw new DesyncError(
            `Called tile ${String(calledTileId)} is not the table's latest discard, from seat ${fromPlayer.seat}`,
        );
    }
    return latest;
}

/** Mark the called tile claimed in its discarder's river. */
function markFromSeatDiscard(state: TableState, event: MeldEvent): TableState {
    const { fromSeat } = event;
    if (fromSeat === null) {
        return state;
    }
    const fromPlayer = state.players.find((p) => p.seat === fromSeat);
    if (!fromPlayer) {
        throw new DesyncError(`fromSeat player not found for seat ${fromSeat}`);
    }
    const latest = requireCalledDiscard(state, fromPlayer, event.calledTileId);
    return {
        ...state,
        players: updatePlayer(state.players, fromSeat, {
            discards: [...fromPlayer.discards.slice(0, -1), { ...latest, claimed: true }],
        }),
    };
}

function applyOpenMeld(state: TableState, event: MeldEvent): TableState {
    const caller = findCaller(state, event);
    const tilesFromHand = event.tileIds.filter((id) => id !== event.calledTileId);
    const melds = [...caller.melds, buildMeldRecord(event)];
    const moved = meldFromHand(state, event, { fromHand: tilesFromHand, melds });
    return markFromSeatDiscard(moved, event);
}

function applyClosedKan(state: TableState, event: MeldEvent): TableState {
    const caller = findCaller(state, event);
    const melds = [...caller.melds, buildMeldRecord(event)];
    return meldFromHand(state, event, { fromHand: event.tileIds, melds });
}

/** Find the existing pon matching the event's tile type and derive which tile was added from hand. */
function findPonAndAddedTile(
    caller: PlayerState,
    event: MeldEvent,
): { ponMeld: MeldRecord; addedTileId: number } | null {
    const ponMeld = ponOfType(caller.melds, tileType(event.tileIds[0]));
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
    const caller = findCaller(state, event);
    const match = findPonAndAddedTile(caller, event);
    if (!match) {
        throw new DesyncError(`No matching pon found for added_kan at seat ${event.callerSeat}`);
    }
    const kan = buildMeldRecord(event, match.addedTileId);
    const melds = caller.melds.map((m) => (m === match.ponMeld ? kan : m));
    return meldFromHand(state, event, { fromHand: [match.addedTileId], melds });
}

/**
 * Complete a kan its chankan prompt already showed as declared: the server's meld takes the shown kan's place, and
 * nothing more leaves the hand, which gave its tiles at the declaration.
 */
function completeShownKan(state: TableState, event: MeldEvent, shownIndex: number): TableState {
    const caller = findCaller(state, event);
    const shown = caller.melds[shownIndex];
    const kan = buildMeldRecord(event, shown.addedTileId);
    return {
        ...state,
        players: updatePlayer(state.players, event.callerSeat, {
            melds: caller.melds.map((meld, index) => (index === shownIndex ? kan : meld)),
        }),
    };
}

/** The index of the caller's kan declared open to chankan that the meld completes, or -1 for any other meld. */
export function shownKanOfMeld(state: TableState, event: MeldEvent): number {
    if (event.meldType !== "closed_kan" && event.meldType !== "added_kan") {
        return -1;
    }
    return shownKanIndex(findCaller(state, event), event.meldType, event.tileIds[0]);
}

function applyMeldByType(state: TableState, event: MeldEvent): TableState {
    const shownIndex = shownKanOfMeld(state, event);
    if (shownIndex !== -1) {
        return completeShownKan(state, event, shownIndex);
    }
    switch (event.meldType) {
        case "chi":
        case "pon":
        case "open_kan": {
            return applyOpenMeld(state, event);
        }
        case "closed_kan": {
            return applyClosedKan(state, event);
        }
        case "added_kan": {
            return applyAddedKan(state, event);
        }
        default: {
            const unhandled: never = event.meldType;
            throw new Error(`Unhandled meld type: ${String(unhandled)}`);
        }
    }
}

/** Whether a meld takes a discard from the river: a call (chi, pon, open kan), never a kan from the caller's own hand. */
function claimsDiscard(meldType: MeldEvent["meldType"]): boolean {
    return meldType === "chi" || meldType === "pon" || meldType === "open_kan";
}

/** A meld; the latest discard stays marked unless the meld claimed it. */
export function applyMeld(state: TableState, event: MeldEvent): TableState {
    const nextState = applyMeldByType(state, event);
    return {
        ...nextState,
        currentPlayerSeat: event.callerSeat,
        lastDiscardSeat: claimsDiscard(event.meldType) ? null : state.lastDiscardSeat,
    };
}
