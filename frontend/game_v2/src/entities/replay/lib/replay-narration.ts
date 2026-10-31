import { type ActionStep, type StepEvent } from "@/entities/replay/model/action-steps";
import {
    type BoardPerspective,
    type KanDeclaredEvent,
    type TableState,
    formatRoundName,
    roundInWind,
    roundResultSummary,
} from "@/entities/table";
import { RED_FIVES, tileName } from "@/entities/tile";
import {
    type DiscardEvent,
    type DrawEvent,
    type MeldEvent,
    SEAT_CONTROL_REASON,
    type SeatControlLine,
} from "@/shared/protocol";

const CALL_NAMES = { chi: "chi", open_kan: "kan", pon: "pon" } as const;

function playerName(table: TableState, seat: number): string {
    return table.players.find((player) => player.seat === seat)?.name ?? `Seat ${seat}`;
}

/** A kan named by its kind of tile, never by the red five that may be among its four. */
function kanTileName(tileIds: readonly number[]): string {
    const plain = tileIds.find((id) => !RED_FIVES.has(id)) ?? tileIds[0];
    return tileName(plain);
}

function meldLine(table: TableState, event: MeldEvent): string {
    const caller = playerName(table, event.callerSeat);
    switch (event.meldType) {
        case "closed_kan": {
            return `${caller} declares a closed kan of ${kanTileName(event.tileIds)}`;
        }
        case "added_kan": {
            return `${caller} adds a kan of ${kanTileName(event.tileIds)}`;
        }
        default: {
            const tile = event.calledTileId === null ? "" : ` on ${tileName(event.calledTileId)}`;
            const from =
                event.fromSeat === null ? "" : ` from ${playerName(table, event.fromSeat)}`;
            return `${caller} calls ${CALL_NAMES[event.meldType]}${tile}${from}`;
        }
    }
}

function kanDeclaredLine(table: TableState, event: KanDeclaredEvent): string {
    const kind = event.kanType === "added" ? "an added" : "a closed";
    return `${playerName(table, event.seat)} declares ${kind} kan of ${tileName(event.tileId)}`;
}

function seatControlLine(table: TableState, line: SeatControlLine): string {
    const name = playerName(table, line.seat);
    if (line.type === "human_return") {
        return `${name} is back`;
    }
    return line.reason === SEAT_CONTROL_REASON.ABSENT
        ? `AI plays for ${name}, who is absent`
        : `AI plays for ${name}, who left`;
}

interface Narrated {
    readonly event: StepEvent;
    readonly table: TableState;
    readonly isDeal: boolean;
    readonly perspective: BoardPerspective;
}

function drawLine(table: TableState, event: DrawEvent, perspective: BoardPerspective): string {
    const name = playerName(table, event.seat);
    const shown = perspective.reveal === "all" || perspective.bottomSeat === event.seat;
    return shown ? `${name} draws ${tileName(event.tileId)}` : `${name} draws`;
}

function discardLine(table: TableState, event: DiscardEvent): string {
    const name = playerName(table, event.seat);
    const tile = tileName(event.tileId);
    return event.isRiichi
        ? `${name} declares riichi, discarding ${tile}`
        : `${name} discards ${tile}`;
}

/** The line a seat's own move adds: a draw (none for the deal's), a discard, a call, a kan. */
function seatMoveLine({ event, isDeal, perspective, table }: Narrated): string | null {
    switch (event.type) {
        case "draw": {
            return isDeal ? null : drawLine(table, event, perspective);
        }
        case "discard": {
            return discardLine(table, event);
        }
        case "meld": {
            return meldLine(table, event);
        }
        case "kan_declared": {
            return kanDeclaredLine(table, event);
        }
        default: {
            return null;
        }
    }
}

/** The line one entry adds to its stop's narration, or null for one that tells nothing of its own. */
function moveLine(narrated: Narrated): string | null {
    const { event, table } = narrated;
    switch (event.type) {
        case "round_started": {
            const round = formatRoundName(event.wind, roundInWind(table), event.honbaSticks);
            return `${round}: ${playerName(table, event.dealerSeat)} deals`;
        }
        case "dora_revealed": {
            return `new dora indicator ${tileName(event.tileId)}`;
        }
        case "round_end": {
            return roundResultSummary(table.roundEndResult, table.players);
        }
        case "game_end": {
            return `Game over: ${playerName(table, event.winnerSeat)} wins`;
        }
        default: {
            return seatMoveLine(narrated);
        }
    }
}

/** The timeline a replay's stops narrate: `events[i]` is entry i's step event and `tables[i + 1]` the table after it. */
export interface NarratedTimeline {
    readonly events: readonly StepEvent[];
    readonly tables: readonly TableState[];
}

function isSeatControl(event: StepEvent): event is SeatControlLine {
    return event.type === "ai_replacement" || event.type === "human_return";
}

/**
 * What a replay's stop shows happening, in a line: its move with the bookkeeping after it ("Alice discards 5m",
 * "Bob declares a closed kan of East · new dora indicator 3p"), then any seat that changed hands among its entries.
 * A draw names its tile only where the perspective shows the drawer's hand.
 */
export function narrateStop(
    timeline: NarratedTimeline,
    stop: ActionStep,
    perspective: BoardPerspective,
): string {
    const { events, tables } = timeline;
    const isDeal = events[stop.moveEntry]?.type === "round_started";
    const entries = Array.from(
        { length: stop.stateIndex - stop.firstEntry },
        (_slot, offset) => stop.firstEntry + offset,
    );
    const notes = entries.flatMap((entry) => {
        const event = events[entry];
        return isSeatControl(event) ? [seatControlLine(tables[entry + 1], event)] : [];
    });
    const moves = entries.flatMap((entry) => {
        const event = events[entry];
        if (isSeatControl(event)) {
            return [];
        }
        const line = moveLine({ event, isDeal, perspective, table: tables[entry + 1] });
        return line === null ? [] : [line];
    });
    return [...moves, ...notes].join(" · ");
}
