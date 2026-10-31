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

/** Read a replay file for its page: its timeline, its stops by round from the first deal, and where it broke off. */
export function readReplay(text: string): ReplayRead {
    const read = readReplayTimeline(text);
    if (!read.ok) {
        return { ok: false, unshowable: read.refusal };
    }
    const { calls, events, tables } = timelineSource(read.timeline);
    const navigation = buildNavigationIndex(events, tables);
    const opening = firstCursor(navigation);
    if (opening === null) {
        return { ok: false, unshowable: { damage: read.damage, kind: "no_deal" } };
    }
    const last = tables[tables.length - 1];
    return {
        ok: true,
        replay: {
            calls,
            damage: read.damage,
            events,
            firstDealerSeat: last.firstDealerSeat,
            navigation,
            opening,
            seatCount: last.players.length,
            tables,
        },
    };
}
