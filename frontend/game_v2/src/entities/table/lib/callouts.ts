import {
    type BoardCallout,
    type CalloutKind,
    SEAT_POSITIONS,
} from "@/entities/table/model/board-types";
import { showsDeclaredKan } from "@/entities/table/model/handlers/kan-declared";
import { shownKanOfMeld } from "@/entities/table/model/handlers/meld";
import { type TableEvent, type TableState } from "@/entities/table/model/types";
import {
    ABORTIVE_DRAW_TYPE,
    MELD_TYPE,
    type MeldEvent,
    type MeldType,
    ROUND_RESULT_TYPE,
} from "@/shared/protocol";

/** A call a seat makes aloud: its kind and the seat that made it, and for a kan the tile type it tells that kan by. */
export interface Call {
    readonly kind: CalloutKind;
    readonly seat: number;
    readonly kanTileType?: number;
}

/** How long a live call shows by its seat: the board's callout plays its whole animation in this time. */
export const CALLOUT_MS = 1500;

const SEAT_COUNT = 4;
const COPIES_PER_TILE = 4;

const CALLOUT_LABELS: Readonly<Record<CalloutKind, string>> = {
    chi: "Chi",
    kan: "Kan",
    pon: "Pon",
    riichi: "Riichi",
    ron: "Ron",
    tsumo: "Tsumo",
};

const MELD_CALLS: Readonly<Record<MeldType, CalloutKind>> = {
    [MELD_TYPE.ADDED_KAN]: "kan",
    [MELD_TYPE.CHI]: "chi",
    [MELD_TYPE.CLOSED_KAN]: "kan",
    [MELD_TYPE.OPEN_KAN]: "kan",
    [MELD_TYPE.PON]: "pon",
};

const NO_CALLS: readonly Call[] = [];

/** The calls a round's result makes: each winner's ron or tsumo, or the three rons that drew the round. */
function resultCalls(table: TableState): readonly Call[] {
    const result = table.roundEndResult;
    if (result === null) {
        return NO_CALLS;
    }
    if (result.draw !== null) {
        const tripleRon = result.draw.kind === ABORTIVE_DRAW_TYPE.TRIPLE_RON;
        return tripleRon ? result.draw.ronSeats.map((seat) => ({ kind: "ron", seat })) : NO_CALLS;
    }
    const kind = result.resultType === ROUND_RESULT_TYPE.TSUMO ? "tsumo" : "ron";
    return result.winners.map((winner) => ({ kind, seat: winner.seat }));
}

function kanCall(seat: number, tileId: number): Call {
    return { kanTileType: Math.floor(tileId / COPIES_PER_TILE), kind: "kan", seat };
}

/** A meld's call: its chi or pon, or its kan unless it completes a kan the table found shown already. */
function meldCalls(event: MeldEvent, before: TableState): readonly Call[] {
    const kind = MELD_CALLS[event.meldType];
    if (kind !== "kan") {
        return [{ kind, seat: event.callerSeat }];
    }
    const shown = shownKanOfMeld(before, event) !== -1;
    return shown ? NO_CALLS : [kanCall(event.callerSeat, event.tileIds[0])];
}

/**
 * The calls a table event makes aloud, read with the table it found (`before`) and the one it left (`after`): a meld's
 * chi, pon or kan, a kan declared open to chankan, a riichi declaration's discard, a round's ron or tsumo; none for
 * any other move, nor for a kan the table already showed (the declaration a re-sent prompt repeats, the meld that
 * completes a kan nobody robbed). Null for an event that is no move of its own (bookkeeping of the move before it, a
 * seat changing hands, a reconnect's snapshot), which leaves the calls the board shows as they are.
 */
export function eventCalls(
    event: TableEvent,
    before: TableState,
    after: TableState,
): readonly Call[] | null {
    switch (event.type) {
        case "meld": {
            return meldCalls(event, before);
        }
        case "kan_declared": {
            return showsDeclaredKan(before, event) ? NO_CALLS : [kanCall(event.seat, event.tileId)];
        }
        case "discard": {
            return event.isRiichi ? [{ kind: "riichi", seat: event.seat }] : NO_CALLS;
        }
        case "round_end": {
            return resultCalls(after);
        }
        case "round_started":
        case "draw":
        case "game_end": {
            return NO_CALLS;
        }
        default: {
            return null;
        }
    }
}

/** Whether `call` is a kan one of `shown` already calls: the same seat's kan of the same tile. */
export function callsShownKan(shown: readonly Call[], call: Call): boolean {
    return (
        call.kind === "kan" &&
        shown.some(
            (other) =>
                other.kind === "kan" &&
                other.seat === call.seat &&
                other.kanTileType === call.kanTileType,
        )
    );
}

/** The calls as the board shows them, each at its seat's position from the seat at the bottom. */
export function boardCallouts(calls: readonly Call[], bottomSeat: number): BoardCallout[] {
    return calls.map(({ kind, seat }) => ({
        kind,
        label: CALLOUT_LABELS[kind],
        position: SEAT_POSITIONS[(seat - bottomSeat + SEAT_COUNT) % SEAT_COUNT],
    }));
}
