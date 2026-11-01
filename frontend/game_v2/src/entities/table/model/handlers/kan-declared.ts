import { DesyncError } from "@/entities/table/model/desync-error";
import {
    ponOfType,
    requirePlayer,
    takeFromHand,
    updatePlayer,
} from "@/entities/table/model/helpers";
import {
    type KanDeclaredEvent,
    type MeldRecord,
    type PlayerState,
    type TableState,
} from "@/entities/table/model/types";
import {
    type ChankanPromptEvent,
    KAN_TYPE,
    type MeldType,
    ROUND_RESULT_TYPE,
    type RoundEndEvent,
    tileType,
    tileTypeCopies,
} from "@/shared/protocol";

type DeclaredKanType = "added_kan" | "closed_kan";

/** The kan a chankan prompt shows its declarer declaring, as the prompt names it. */
export function chankanKanDeclared(prompt: ChankanPromptEvent): KanDeclaredEvent {
    return {
        kanType: prompt.kanType,
        seat: prompt.fromSeat,
        tileId: prompt.tileId,
        type: "kan_declared",
    };
}

/** The kan a round end's win robbed, as declared before the win, or null for a round end that robbed none. */
export function robbedKanDeclared(event: RoundEndEvent): KanDeclaredEvent | null {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.RON:
        case ROUND_RESULT_TYPE.DOUBLE_RON:
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW: {
            const kan = event.robbedKan;
            return kan === null
                ? null
                : {
                      kanType: kan.kanType,
                      seat: kan.seat,
                      tileId: kan.tileId,
                      type: "kan_declared",
                  };
        }
        default: {
            return null;
        }
    }
}

/** The index of the seat's kan of the tile's type that a declaration already shows, or -1. */
export function shownKanIndex(player: PlayerState, meldType: MeldType, tileId: number): number {
    return player.melds.findIndex(
        (meld) => meld.meldType === meldType && tileType(meld.tileIds[0]) === tileType(tileId),
    );
}

/** The meld a declared kan lays, by the type its source names. */
function declaredKanType(event: KanDeclaredEvent): DeclaredKanType {
    return event.kanType === KAN_TYPE.ADDED ? "added_kan" : "closed_kan";
}

/** The kan as laid, and the tiles it takes from the hand: an added kan's one tile, a closed kan's four copies. */
function declaredKan(
    player: PlayerState,
    event: KanDeclaredEvent,
    meldType: DeclaredKanType,
): { readonly melds: readonly MeldRecord[]; readonly fromHand: readonly number[] } {
    if (meldType === "closed_kan") {
        const tileIds = tileTypeCopies(tileType(event.tileId));
        const kan: MeldRecord = {
            calledTileId: null,
            callerSeat: event.seat,
            fromSeat: null,
            meldType,
            tileIds,
        };
        return { fromHand: tileIds, melds: [...player.melds, kan] };
    }
    const pon = ponOfType(player.melds, tileType(event.tileId));
    if (pon === undefined) {
        throw new DesyncError(
            `No pon to raise to an added kan of ${event.tileId} at seat ${event.seat}`,
        );
    }
    const kan: MeldRecord = {
        ...pon,
        addedTileId: event.tileId,
        meldType,
        tileIds: [...pon.tileIds, event.tileId],
    };
    return {
        fromHand: [event.tileId],
        melds: player.melds.map((meld) => (meld === pon ? kan : meld)),
    };
}

/** Whether the table already shows the kan a declaration names: an earlier prompt for it showed it. */
export function showsDeclaredKan(state: TableState, event: KanDeclaredEvent): boolean {
    const player = requirePlayer(state, event.seat);
    return shownKanIndex(player, declaredKanType(event), event.tileId) !== -1;
}

/**
 * Show a kan declared open to chankan: its tiles leave the hand for the kan. It draws no replacement and reveals no
 * dora, since the kan completes only once nobody robs it. A kan the table already shows (the prompt showed it before
 * the round end that robs it) is not taken twice. It claims no discard, so the latest discard stays marked.
 */
export function applyKanDeclared(state: TableState, event: KanDeclaredEvent): TableState {
    if (showsDeclaredKan(state, event)) {
        return state;
    }
    const player = requirePlayer(state, event.seat);
    const meldType = declaredKanType(event);
    const { fromHand, melds } = declaredKan(player, event, meldType);
    const hand = takeFromHand(player, fromHand);
    if (hand === null) {
        throw new DesyncError(
            `Tiles ${fromHand.join(", ")} not found in hand of seat ${event.seat}`,
        );
    }
    return {
        ...state,
        currentPlayerSeat: event.seat,
        players: updatePlayer(state.players, event.seat, {
            concealedCount: hand.concealedCount,
            drawnConcealed: false,
            drawnTileId: null,
            melds,
            tiles: hand.tiles,
        }),
    };
}
