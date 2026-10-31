import { type NavigationIndex } from "./navigation-index";
import { type ReplayCursor, positionCursor, roundPosition } from "./replay-cursor";

/** The query parameters of a replay page's address (`docs/architecture.md`, Replays). */
export const REPLAY_ADDRESS_PARAM = { ROUND: "round", SEAT: "seat", STEP: "step" } as const;

/**
 * What a replay page's query asks for, each part a whole number or null when it is missing, repeated or not a whole
 * number: `seat` the seat at the bottom, `round` the recorded deal (repeats counted) and `step` the stop within it,
 * all from 0.
 */
export interface ReplayAddress {
    readonly seat: number | null;
    readonly round: number | null;
    readonly step: number | null;
}

/** Where a replay opens and from which seat. */
export interface ReplayView {
    readonly cursor: ReplayCursor;
    readonly bottomSeat: number;
}

const WHOLE_NUMBER = /^\d{1,9}$/;

function wholeNumberParam(params: URLSearchParams, name: string): number | null {
    const values = params.getAll(name);
    if (values.length !== 1 || !WHOLE_NUMBER.test(values[0])) {
        return null;
    }
    return Number(values[0]);
}

export function parseReplayAddress(search: string): ReplayAddress {
    const params = new URLSearchParams(search);
    return {
        round: wholeNumberParam(params, REPLAY_ADDRESS_PARAM.ROUND),
        seat: wholeNumberParam(params, REPLAY_ADDRESS_PARAM.SEAT),
        step: wholeNumberParam(params, REPLAY_ADDRESS_PARAM.STEP),
    };
}

/** The view an address falls back to, part by part, and how many seats the game has. */
export interface ReplayViewDefaults extends ReplayView {
    readonly seatCount: number;
}

/**
 * Where an address opens a replay, each bad part replaced by its fallback: a seat the game does not seat by the
 * default seat, a round the replay does not hold by the default cursor (the first deal; its step ignored), a step its
 * round does not hold by that round's deal.
 */
export function resolveReplayAddress(
    nav: NavigationIndex,
    address: ReplayAddress,
    defaults: ReplayViewDefaults,
): ReplayView {
    const seat =
        address.seat !== null && address.seat < defaults.seatCount
            ? address.seat
            : defaults.bottomSeat;
    const round =
        address.round === null ? null : positionCursor(nav, { round: address.round, step: 0 });
    if (address.round === null || round === null) {
        return { bottomSeat: seat, cursor: defaults.cursor };
    }
    const step =
        address.step === null
            ? null
            : positionCursor(nav, { round: address.round, step: address.step });
    return { bottomSeat: seat, cursor: step ?? round };
}

/**
 * The page's query naming a view, the page's other parameters (`v=2`, `debug`) kept as they were; a repeated
 * position parameter becomes one. A double ron's page is not named: a link opens a result at its first page.
 */
export function replayAddressSearch(
    search: string,
    nav: NavigationIndex,
    view: ReplayView,
): string {
    const params = new URLSearchParams(search);
    const { round, step } = roundPosition(nav, view.cursor);
    params.set(REPLAY_ADDRESS_PARAM.SEAT, String(view.bottomSeat));
    params.set(REPLAY_ADDRESS_PARAM.ROUND, String(round));
    params.set(REPLAY_ADDRESS_PARAM.STEP, String(step));
    return `?${params.toString()}`;
}
