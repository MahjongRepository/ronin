import { type Call, type CalloutKind, type TableState } from "@/entities/table";
import { type LocalStore } from "@/shared/lib";

import { decisionCountdown } from "./countdown";
import { decisionOf } from "./pending";
import { type LiveClient } from "./types";

/** A sound the game plays: a discard's click, a call's voice, a yakuman's gong, a decision's last seconds' beep. */
export type SoundCue = CalloutKind | "discard" | "yakuman" | "beep";

/** The seconds of a decision's countdown that beep, each once; a decision no longer than them stays quiet. */
const BEEP_SECONDS = 5;

function discardCount(table: TableState): number {
    return table.players.reduce((count, player) => count + player.discards.length, 0);
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
 * reconnect's snapshot, which replace the rivers whole, stays quiet; then each call's voice, a yakuman win's gong.
 */
export function moveSoundCues(
    before: TableState,
    after: TableState,
    calls: readonly Call[],
): readonly SoundCue[] {
    const discards: readonly SoundCue[] =
        discardCount(after) === discardCount(before) + 1 ? ["discard"] : [];
    return [...discards, ...callCues(calls, after)];
}

/** The calls the board starts showing at a live step; none while the same calls stay showing, or none show. */
function newCalls(before: LiveClient, after: LiveClient): readonly Call[] {
    const shown = after.calls;
    return shown === null || shown === before.calls ? [] : shown.calls;
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

/** A beep each time the viewer's open decision, one that lasts longer, shows a new second of its last few. */
function beepCues(before: LiveClient, after: LiveClient): readonly SoundCue[] {
    const now = beepingSeconds(after);
    if (now === null || now.seconds > BEEP_SECONDS) {
        return [];
    }
    const was = beepingSeconds(before);
    const sameSecond = was !== null && was.waitId === now.waitId && was.seconds === now.seconds;
    return sameSecond ? [] : ["beep"];
}

/**
 * The sounds one step of the live client makes, from the state it found (`before`) to the one it left (`after`):
 * a discard's click, the voice of each call the board starts showing (a riichi's with its discard's click) with the
 * gong for a yakuman win, and the beep of each new second at the end of a long decision.
 */
export function soundCues(before: LiveClient, after: LiveClient): readonly SoundCue[] {
    const move = moveSoundCues(before.table, after.table, newCalls(before, after));
    return [...move, ...beepCues(before, after)];
}

/** The sound setting as this browser keeps it: the v1 client's key and shape, so both clients share one setting. */
export interface SoundSetting {
    readonly sound_on: boolean;
}

export const SOUND_SETTING_KEY = "Majiang.pref";

export const DEFAULT_SOUND_SETTING: SoundSetting = { sound_on: true };

/** The stored sound setting, or the default for anything else than a settings object holding a boolean. */
export function readSoundSetting(stored: unknown): SoundSetting {
    if (typeof stored !== "object" || stored === null || !("sound_on" in stored)) {
        return DEFAULT_SOUND_SETTING;
    }
    const { sound_on: soundOn } = stored;
    return typeof soundOn === "boolean" ? { sound_on: soundOn } : DEFAULT_SOUND_SETTING;
}

/** The game's sounds as a page plays them: the setting this browser keeps for them, and their player. */
export interface GameSound {
    readonly setting: LocalStore<SoundSetting>;
    readonly play: (cue: SoundCue) => void;
}
