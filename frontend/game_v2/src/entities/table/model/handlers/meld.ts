import { drewUnseen, takeFromHand, updatePlayer } from "@/entities/table/model/helpers";
import {
    type DiscardRecord,
    type MeldRecord,
    type PlayerState,
    type TableState,
} from "@/entities/table/model/types";
import { type MeldEvent } from "@/shared/protocol";

import { shownKanIndex } from "./kan-declared";

function markLastDiscardClaimed(discards: readonly DiscardRecord[]): readonly DiscardRecord[] {
    if (discards.length === 0) {
        return discards;
    }
    return discards.map((d, idx) => (idx === discards.length - 1 ? { ...d, claimed: true } : d));
}

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
        throw new Error(`Caller not found for seat ${event.callerSeat}`);
    }
    return caller;
}

/**
 * Move the caller's tiles from hand into its melds. A kan the caller declares on its own turn follows its draw,
 * which a hidden hand took unseen: that draw joins its concealed count first and leaves the wall.
 */
function meldFromHand(
    state: TableState,
    event: MeldEvent,
    { fromHand, melds }: MeldMove,
): TableState {
    const caller = findCaller(state, event);
    const ownTurn = event.meldType === "closed_kan" || event.meldType === "added_kan";
    const unseen = ownTurn && drewUnseen(caller) ? 1 : 0;
    const hand = takeFromHand(
        { concealedCount: caller.concealedCount + unseen, tiles: caller.tiles },
        fromHand,
    );
    if (hand === null) {
        throw new Error(`Tiles ${fromHand.join(", ")} not found in hand during meld`);
    }
    return {
        ...state,
        players: updatePlayer(state.players, event.callerSeat, {
            concealedCount: hand.concealedCount,
            drawnTileId: null,
            melds,
            tiles: hand.tiles,
        }),
        tilesRemaining: state.tilesRemaining - unseen,
    };
}

function markFromSeatDiscard(state: TableState, fromSeat: number | null): TableState {
    if (fromSeat === null) {
        return state;
    }
    const fromPlayer = state.players.find((p) => p.seat === fromSeat);
    if (!fromPlayer) {
        throw new Error(`fromSeat player not found for seat ${fromSeat}`);
    }
    return {
        ...state,
        players: updatePlayer(state.players, fromSeat, {
            discards: markLastDiscardClaimed(fromPlayer.discards),
        }),
    };
}

function applyOpenMeld(state: TableState, event: MeldEvent): TableState {
    const caller = findCaller(state, event);
    const tilesFromHand = event.tileIds.filter((id) => id !== event.calledTileId);
    const melds = [...caller.melds, buildMeldRecord(event)];
    const moved = meldFromHand(state, event, { fromHand: tilesFromHand, melds });
    return markFromSeatDiscard(moved, event.fromSeat);
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
    const caller = findCaller(state, event);
    const match = findPonAndAddedTile(caller, event);
    if (!match) {
        throw new Error(`No matching pon found for added_kan at seat ${event.callerSeat}`);
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

function applyMeldByType(state: TableState, event: MeldEvent): TableState {
    if (event.meldType === "closed_kan" || event.meldType === "added_kan") {
        const shownIndex = shownKanIndex(
            findCaller(state, event),
            event.meldType,
            event.tileIds[0],
        );
        if (shownIndex !== -1) {
            return completeShownKan(state, event, shownIndex);
        }
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

export function applyMeld(state: TableState, event: MeldEvent): TableState {
    const nextState = applyMeldByType(state, event);
    return {
        ...nextState,
        currentPlayerSeat: event.callerSeat,
        lastDiscardSeat: null,
    };
}
