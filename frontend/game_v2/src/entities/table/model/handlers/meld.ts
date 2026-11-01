import { DesyncError } from "@/entities/table/model/desync-error";
import { ponOfType, takeFromHand, updatePlayer } from "@/entities/table/model/helpers";
import {
    type DiscardRecord,
    type MeldRecord,
    type PlayerState,
    type TableState,
} from "@/entities/table/model/types";
import { assertNever } from "@/shared/lib";
import { type ClaimedMeldEvent, type MeldEvent, tileType } from "@/shared/protocol";

import { shownKanIndex } from "./kan-declared";

type AddedKanEvent = Extract<MeldEvent, { meldType: "added_kan" }>;

function buildMeldRecord(event: MeldEvent): MeldRecord {
    const base = {
        calledTileId: event.calledTileId,
        callerSeat: event.callerSeat,
        fromSeat: event.fromSeat,
        tileIds: [...event.tileIds],
    };
    return event.meldType === "added_kan"
        ? { ...base, addedTileId: event.addedTileId, meldType: event.meldType }
        : { ...base, meldType: event.meldType };
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
    calledTileId: number,
): DiscardRecord {
    const latest = fromPlayer.discards.at(-1);
    const isCalled =
        state.lastDiscardSeat === fromPlayer.seat &&
        latest !== undefined &&
        !latest.claimed &&
        latest.tileId === calledTileId;
    if (!isCalled) {
        throw new DesyncError(
            `Called tile ${calledTileId} is not the table's latest discard, from seat ${fromPlayer.seat}`,
        );
    }
    return latest;
}

/** Mark the called tile claimed in its discarder's river. */
function markFromSeatDiscard(state: TableState, event: ClaimedMeldEvent): TableState {
    const { fromSeat } = event;
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

function applyOpenMeld(state: TableState, event: ClaimedMeldEvent): TableState {
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

/** Raise the caller's pon of the kan's type with the tile the server names as added from hand. */
function applyAddedKan(state: TableState, event: AddedKanEvent): TableState {
    const caller = findCaller(state, event);
    const { addedTileId } = event;
    const ponMeld = ponOfType(caller.melds, tileType(addedTileId));
    if (!ponMeld || ponMeld.tileIds.includes(addedTileId)) {
        throw new DesyncError(
            `No pon that tile ${addedTileId} raises to an added_kan at seat ${event.callerSeat}`,
        );
    }
    const kan = buildMeldRecord(event);
    const melds = caller.melds.map((m) => (m === ponMeld ? kan : m));
    return meldFromHand(state, event, { fromHand: [addedTileId], melds });
}

/**
 * Complete a kan its chankan prompt already showed as declared: the server's meld takes the shown kan's place, and
 * nothing more leaves the hand, which gave its tiles at the declaration.
 */
function completeShownKan(state: TableState, event: MeldEvent, shownIndex: number): TableState {
    const caller = findCaller(state, event);
    const kan = buildMeldRecord(event);
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
            return assertNever(event);
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
