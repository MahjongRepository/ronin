import {
    type ClientTimeline,
    type TimelineEntry,
    readReplayTimeline,
    timelineStates,
} from "@/entities/client";
import { type ReplaySource } from "@/entities/replay/lib/replay-display";
import {
    type ReplayLineError,
    type ReplayRefusal,
    type TableState,
    isReplayEvent,
    isSeatControlLine,
} from "@/entities/table";

import { type StepEvent } from "./action-steps";
import { buildNavigationIndex } from "./navigation-index";
import { type ReplayCursor, firstCursor } from "./replay-cursor";

function stepEventOf(parsed: TimelineEntry["parsed"]): StepEvent {
    if (parsed !== null) {
        if (parsed.type === "kan_declared" || isSeatControlLine(parsed) || isReplayEvent(parsed)) {
            return parsed;
        }
    }
    throw new Error(`A replay timeline entry shows no replay event: ${parsed?.type ?? "none"}`);
}

/**
 * The step event of each timeline entry, for the replay's stops: its replay event, the kan a round end robbed as
 * declared, or a seat control line. The reader keeps no other entry, so any other throws.
 */
export function timelineStepEvents(timeline: ClientTimeline): StepEvent[] {
    return timeline.entries.map(({ parsed }) => stepEventOf(parsed));
}

/** A replay ready for its page: what it shows, where it opens, and the seats a viewer may look from. */
export interface LoadedReplay extends ReplaySource {
    /** Each timeline entry's step event, by which autoplay paces its stops. */
    readonly events: readonly StepEvent[];
    /** The first deal, where the page opens when its address names no stop the replay holds. */
    readonly opening: ReplayCursor;
    /**
     * The table as the game started, seated before its first deal, each seat at the score its first deal starts it
     * on (the game's start names none): the seating the page opens on.
     */
    readonly startTable: TableState;
    /** The recorded first dealer's seat, the default seat at the bottom (`docs/architecture.md`, Replays). */
    readonly firstDealerSeat: number;
    readonly seatCount: number;
}

/** A replay the page cannot show: refused by its version line, or holding no deal to open on. */
export type ReplayUnshowable =
    | ReplayRefusal
    | { readonly kind: "no_deal"; readonly damage: ReplayLineError | null };

export type ReplayRead =
    | { readonly ok: true; readonly replay: LoadedReplay }
    | { readonly ok: false; readonly unshowable: ReplayUnshowable };

/** Each timeline entry's step event, and each timeline state's table and the calls it shows. */
function timelineSource(
    timeline: ClientTimeline,
): Pick<LoadedReplay, "calls" | "events" | "tables"> {
    const states = timelineStates(timeline);
    return {
        calls: states.map((state) => state.calls?.calls ?? []),
        events: timelineStepEvents(timeline),
        tables: states.map((state) => state.table),
    };
}

/** The first seated table, each seat at the score `firstDeal` starts it on; null before any seat. */
function seatedAtStart(tables: readonly TableState[], firstDeal: TableState): TableState | null {
    const seated = tables.find((table) => table.players.length > 0);
    if (seated === undefined) {
        return null;
    }
    const players = seated.players.map((player) => ({
        ...player,
        score: firstDeal.players.find((dealt) => dealt.seat === player.seat)?.score ?? player.score,
    }));
    return { ...seated, players };
}

/**
 * A timeline's replay for its page: where it opens (its first deal), the table as the game started and the seats it
 * holds; null where it holds no deal.
 */
function loadedReplay(
    source: Pick<LoadedReplay, "calls" | "damage" | "events" | "tables">,
): LoadedReplay | null {
    const { events, tables } = source;
    const navigation = buildNavigationIndex(events, tables);
    const opening = firstCursor(navigation);
    if (opening === null) {
        return null;
    }
    const startTable = seatedAtStart(tables, tables[navigation.stops[opening.stop].stateIndex]);
    if (startTable === null) {
        return null;
    }
    const last = tables[tables.length - 1];
    return {
        ...source,
        firstDealerSeat: last.firstDealerSeat,
        navigation,
        opening,
        seatCount: last.players.length,
        startTable,
    };
}

/** Read a replay file for its page: its timeline, its stops by round from the first deal, and where it broke off. */
export function readReplay(text: string): ReplayRead {
    const read = readReplayTimeline(text);
    if (!read.ok) {
        return { ok: false, unshowable: read.refusal };
    }
    const replay = loadedReplay({ ...timelineSource(read.timeline), damage: read.damage });
    return replay === null
        ? { ok: false, unshowable: { damage: read.damage, kind: "no_deal" } }
        : { ok: true, replay };
}
