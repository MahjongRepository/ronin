import { type SoundSetting } from "@ronin/shared/sound-setting";

import { type Call, type CalloutKind, type PlayerState, type TableState } from "@/entities/table";
import { type LocalStore } from "@/shared/lib";

import { matchesCall, submittedCall } from "./calls";
import { decisionCountdown } from "./countdown";
import { decisionOf } from "./pending";
import { unseenWait } from "./play-switches";
import { type LiveClient, type Offer } from "./types";

/** A move's sound, a new decision's chime, or a countdown's beep. */
export type SoundCue = CalloutKind | "discard" | "draw" | "yakuman" | "beep" | "decision";

const DECISION_SOUND_OFFERS = new Set<Offer["kind"]>([
    "chi",
    "pon",
    "kan",
    "riichi",
    "ron",
    "tsumo",
]);

/** The seconds of a decision's countdown that beep, each once; a decision no longer than them stays quiet. */
const BEEP_SECONDS = 5;

function discardCount(table: TableState): number {
    return table.players.reduce((count, player) => count + player.discards.length, 0);
}

function holdsDraw(player: PlayerState | undefined): boolean {
    return player !== undefined && (player.drawnTileId !== null || player.drawnConcealed);
}

/** Whether no tile has left a hand yet this round: no discard and no call, so the next draw opens the round. */
function opensRound(table: TableState): boolean {
    return table.players.every(
        (player) => player.discards.length === 0 && player.melds.length === 0,
    );
}

/**
 * Whether a move draws one tile after the round's opening one: the wall gives up exactly one and a seat newly holds a
 * draw, so a deal, the dealer's opening draw that comes with it, a re-sent draw and a win's revealed hand stay quiet.
 */
function drawsOneTile(before: TableState, after: TableState): boolean {
    return (
        !opensRound(before) &&
        after.tilesRemaining === before.tilesRemaining - 1 &&
        after.players.some(
            (player, index) => holdsDraw(player) && !holdsDraw(before.players[index]),
        )
    );
}

/** Whether a round's result pays a winner at a yakuman limit. */
function paysYakuman(table: TableState): boolean {
    return (
        table.roundEndResult?.winners.some((winner) => winner.handResult.yakumanCount !== null) ??
        false
    );
}

/** Each call's kind's voice once however many seats call it, and the gong when it wins at a yakuman limit. */
function callCues(calls: readonly Call[], table: TableState): readonly SoundCue[] {
    const voices = [...new Set(calls.map((call) => call.kind))];
    const wins = voices.some((kind) => kind === "ron" || kind === "tsumo");
    return wins && paysYakuman(table) ? [...voices, "yakuman"] : voices;
}

/**
 * The sounds of one move, live or in a replay, from the table it found (`before`) to the one it left (`after`), with
 * the calls it makes aloud: a discard's click when it adds exactly one discard to the table, so a deal or a
 * reconnect's snapshot, which replace the rivers whole, stays quiet; a draw's tick when it draws one tile after the
 * round's opening draw; then each
 * call's voice, a yakuman win's gong.
 */
export function moveSoundCues(
    before: TableState,
    after: TableState,
    calls: readonly Call[],
): readonly SoundCue[] {
    const discards: readonly SoundCue[] =
        discardCount(after) === discardCount(before) + 1 ? ["discard"] : [];
    const draws: readonly SoundCue[] = drawsOneTile(before, after) ? ["draw"] : [];
    return [...discards, ...draws, ...callCues(calls, after)];
}

/** The calls the board starts showing at a live step; none while the same calls stay showing, or none show. */
function newCalls(before: LiveClient, after: LiveClient): readonly Call[] {
    const shown = after.calls;
    return shown === null || shown === before.calls
        ? []
        : shown.calls.filter((call) => !before.calls?.calls.includes(call));
}

/** The whole seconds the viewer's open decision reads, while it runs and lasts longer than the beeping seconds. */
function beepingSeconds(
    state: LiveClient,
): { readonly waitId: number; readonly seconds: number } | null {
    const decision = decisionOf(state);
    const countdown = decisionCountdown(state);
    if (decision?.deadline == null || countdown?.kind !== "running") {
        return null;
    }
    const lasts = decision.deadline - decision.openedAt > BEEP_SECONDS * 1000;
    return lasts ? { seconds: countdown.secondsLeft, waitId: decision.waitId } : null;
}

function entersTimeBank(before: LiveClient, after: LiveClient): boolean {
    const was = decisionCountdown(before);
    const now = decisionCountdown(after);
    return (
        was?.kind === "running" &&
        was.clock?.inBank === false &&
        now?.kind === "running" &&
        now.clock?.inBank === true &&
        decisionOf(before)?.waitId === decisionOf(after)?.waitId
    );
}

/** A beep when the open decision enters its bank or shows a new second of its last few, never twice at once. */
function beepCues(before: LiveClient, after: LiveClient): readonly SoundCue[] {
    if (entersTimeBank(before, after)) {
        return ["beep"];
    }
    const now = beepingSeconds(after);
    if (now === null || now.seconds > BEEP_SECONDS) {
        return [];
    }
    const was = beepingSeconds(before);
    const sameSecond = was !== null && was.waitId === now.waitId && was.seconds === now.seconds;
    return sameSecond ? [] : ["beep"];
}

function decisionCues(before: LiveClient, after: LiveClient): readonly SoundCue[] {
    const decision = decisionOf(after);
    if (
        decision?.status.kind !== "open" ||
        !unseenWait(decision.waitId, before.highestOpenedWaitId)
    ) {
        return [];
    }
    return decision.offers.some((offer) => DECISION_SOUND_OFFERS.has(offer.kind))
        ? ["decision"]
        : [];
}

/**
 * The sounds one step of the live client makes, from the state it found (`before`) to the one it left (`after`):
 * a discard's click, the voice of each call the board starts showing (a riichi's with its discard's click) with the
 * gong for a yakuman win, a new call, riichi or win decision's chime, and a beep at the bank's start and each last second.
 */
export function soundCues(before: LiveClient, after: LiveClient): readonly SoundCue[] {
    const declared = submittedCall(before);
    const calls = newCalls(before, after).filter((call) => !matchesCall(call, declared));
    const move = moveSoundCues(before.table, after.table, calls);
    const confirmedWin =
        (declared?.kind === "ron" || declared?.kind === "tsumo") &&
        before.table.roundEndResult !== after.table.roundEndResult &&
        paysYakuman(after.table) &&
        !move.includes("yakuman");
    return [
        ...move,
        ...(confirmedWin ? ["yakuman" as const] : []),
        ...decisionCues(before, after),
        ...beepCues(before, after),
    ];
}

/** The game's sounds as a page plays them: the setting this browser keeps for them, and their player. */
export interface GameSound {
    readonly setting: LocalStore<SoundSetting>;
    readonly play: (cue: SoundCue) => void;
}
