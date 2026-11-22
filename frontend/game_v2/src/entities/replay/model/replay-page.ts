import {
    type SettingsMenuCommand,
    type SoundCue,
    moveSoundCues,
    stepSettingsMenu,
} from "@/entities/client";
import { type ReplayMoves, replayMoves } from "@/entities/replay/lib/replay-display";
import { handAnalysisUrl, handNotation } from "@/entities/replay/model/hand-notation";
import {
    type LoadedReplay,
    type ReplayUnshowable,
    readReplay,
} from "@/entities/replay/model/read-replay";
import {
    type ReplayView,
    parseReplayAddress,
    resolveReplayAddress,
} from "@/entities/replay/model/replay-address";
import {
    type AutoplayState,
    autoplayDelayMs,
    autoplayStep,
    isPauseStop,
    observeAutoplayDelayMs,
} from "@/entities/replay/model/replay-autoplay";
import {
    type CallMove,
    type ShownReplayCall,
    shownReplayCall,
} from "@/entities/replay/model/replay-calls";
import { type ReplayCursor, lastCursor } from "@/entities/replay/model/replay-cursor";
import { type ReplayPrefs } from "@/entities/replay/model/replay-prefs";
import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table";
import { type ObserveFetch, type ReplayFetch } from "@/shared/api";
import { type WheelGesture, assertNever, holdWheel, wheelStep } from "@/shared/lib";
import { type ObserveAnswer } from "@/shared/protocol";

/** The way a step button steps, which a pointer may hold to repeat. */
export type StepDirection = "next" | "prev";

/** A held step button steps from its press, again after this delay, then every `HOLD_REPEAT_MS`. */
export const HOLD_DELAY_MS = 350;
export const HOLD_REPEAT_MS = 120;

/** How long the page says a copy of the hand went through, or did not. */
export const HAND_COPY_NOTICE_MS = 2000;

const HTTP_NOT_FOUND = 404;

/** How long after each observe answer, or a failed request, the page asks the stream again. */
export const OBSERVE_POLL_MS = 2000;

const SECOND_MS = 1000;

/** Why the page shows no replay. */
export type ReplayFailure =
    | ReplayUnshowable
    | { readonly kind: "not_found" }
    | { readonly kind: "refused"; readonly status: number }
    | { readonly kind: "unreachable" }
    | { readonly kind: "show_failed" };

/** Autoplay as the page runs it: its state, and while it plays, the logical time it moves on at. */
export interface ReplayAutoplay extends AutoplayState {
    readonly dueAt: number | null;
}

/** A step button its pointer holds down: the way it steps, and when it repeats, null while the pointer is off it. */
export interface ReplayHold {
    readonly direction: StepDirection;
    readonly repeatAt: number | null;
}

/** Whether a copy of the hand went through, which the page says until `until`. */
export interface ReplayHandCopy {
    readonly outcome: "copied" | "failed";
    readonly until: number;
}

/**
 * The observe stream a page follows: every record received so far, the version record first; the cursor its next
 * request asks from; whether the stream has ended or the server no longer holds the game; and when the next request is
 * due, null while one is in flight and once the stream is done.
 */
export interface ObserveStream {
    readonly content: Uint8Array;
    readonly next: number;
    readonly ended: boolean;
    readonly gone: boolean;
    readonly pollAt: number | null;
}

/**
 * The countdown before a game's first records may be watched: its players East to North, the logical time the records
 * become available, the time left as last drawn, and when the next whole second is due to be drawn, null at zero.
 */
export interface ObserveCountdown {
    readonly players: readonly string[];
    readonly gameType: string;
    readonly availableAt: number;
    readonly remainingMs: number;
    readonly redrawAt: number | null;
}

/** An observed game before it can be played: no answer yet (`countdown` null), or no playable record yet. */
export interface ObserveWaitingScreen {
    readonly kind: "observe_waiting";
    readonly stream: ObserveStream;
    readonly countdown: ObserveCountdown | null;
}

export interface LoadedReplayScreen {
    readonly kind: "loaded";
    readonly replay: LoadedReplay;
    /** The observe stream the replay grows from, null for a saved game's replay. */
    readonly observe: ObserveStream | null;
    readonly view: ReplayView;
    readonly roundListOpen: boolean;
    readonly autoplay: ReplayAutoplay;
    /** Whether the other seats' hands hide, as a seat would see the table. */
    readonly hideHands: boolean;
    /** Whether the rivers mark the discards of the tile just drawn. */
    readonly showTsumogiri: boolean;
    /** Whether the tools' menu by the options is open. */
    readonly toolsOpen: boolean;
    /** Whether a step on plays its move's sounds, a setting the live game shares. */
    readonly soundOn: boolean;
    /** Whether the board animates, a setting the live game shares. */
    readonly animationsOn: boolean;
    /** Whether the settings menu in the board's corner is open. */
    readonly settingsOpen: boolean;
    readonly hold: ReplayHold | null;
    /**
     * Whether the seating shows over the board, until the reader starts or moves (never by the wheel): a replay opened
     * at its start, or anywhere with the sound on, whose Start is the click the browser asks before playing a sound.
     */
    readonly seating: boolean;
    /** The step button whose press stepped already, so the click that press ends in is dropped, once. */
    readonly pressedStep: StepDirection | null;
    readonly wheel: WheelGesture | null;
    /** The calls the board shows, which fade on their own time as the reader moves on. */
    readonly shownCall: ShownReplayCall | null;
    readonly handCopy: ReplayHandCopy | null;
}

export type ReplayScreen =
    | { readonly kind: "loading"; readonly waiting: boolean }
    | { readonly kind: "failed"; readonly failure: ReplayFailure }
    | ObserveWaitingScreen
    | { readonly kind: "observe_gone" }
    | LoadedReplayScreen;

/**
 * The key commands that act once per press however long the key is held: autoplay's switch, the next seat's view, the
 * other hands' switch and the hand opened in Tenhou's analysis.
 */
type ReplayToggle = "play" | "view" | "hands" | "analyze";

/** What a key does on the page: a move, or one of the commands acting once per press. */
export type ReplayKeyCommand = keyof ReplayMoves | ReplayToggle;

/**
 * Where a fetched replay opens: the page's address, the reader's settings, the game's sound setting, and the round
 * list and autoplay asked.
 */
export interface ReplayOpening {
    readonly search: string;
    readonly prefs: ReplayPrefs;
    readonly soundOn: boolean;
    readonly animationsOn: boolean;
    readonly roundListOpen: boolean;
    readonly autoplay: boolean;
}

/** Where an observed game opens: the reader's settings, the game's sound setting and the round list asked. */
export type ObserveOpening = Omit<ReplayOpening, "autoplay" | "search">;

/** An observe request's answer, or its network failure. */
type ObserveEvent =
    | {
          readonly kind: "observe_fetched";
          readonly fetched: ObserveFetch;
          readonly opening: ObserveOpening;
      }
    | { readonly kind: "observe_unreachable" };

type LoadEvent =
    | { readonly kind: "load_started" }
    | { readonly kind: "load_waiting" }
    | { readonly kind: "load_unreachable" }
    | { readonly kind: "fetched"; readonly fetched: ReplayFetch; readonly opening: ReplayOpening }
    | { readonly kind: "observe_started" }
    | ObserveEvent
    | { readonly kind: "show_failed" };

interface KeyInput {
    readonly kind: "key";
    readonly command: ReplayKeyCommand | null;
    readonly repeat: boolean;
}

interface PressInput {
    readonly kind: "step_press";
    readonly direction: StepDirection;
    readonly primary: boolean;
}

/** A step button's click and press, a hold's pointer, the wheel and the deadline's tick. */
type StepInput =
    | { readonly kind: "step_click"; readonly direction: StepDirection }
    | PressInput
    | { readonly kind: "hold_pointer"; readonly over: boolean }
    | { readonly kind: "hold_end"; readonly cancelled: boolean }
    | { readonly kind: "wheel"; readonly deltaPx: number }
    | { readonly kind: "tick" };

/** A move to a cursor: the controls', a key's, a result's page and a round chosen from the list. */
type MoveInput =
    | { readonly kind: "move"; readonly cursor: ReplayCursor }
    | KeyInput
    | { readonly kind: "result_page"; readonly page: number }
    | { readonly kind: "select_round"; readonly cursor: ReplayCursor };

/** The round list opened, closed (its own close or Escape) or dismissed (a click outside it). */
type RoundListInput =
    | { readonly kind: "toggle_round_list" }
    | { readonly kind: "close_round_list" }
    | { readonly kind: "dismiss_round_list" };

/** The tools' menu opened, closed (Escape) or dismissed (a click outside it), and its tsumogiri switch. */
type ToolsInput =
    | { readonly kind: "toggle_tools" }
    | { readonly kind: "close_tools" }
    | { readonly kind: "dismiss_tools" }
    | { readonly kind: "toggle_tsumogiri" };

/**
 * The seating's start, the options, a seat chosen to view from (its plate or score, by board position), the page
 * hiding, and the settings menu opened or closed and its sound switch.
 */
type OptionInput =
    | { readonly kind: "start" }
    | { readonly kind: "copy_hand" }
    | { readonly kind: "analyze_hand" }
    | { readonly kind: "hand_copy"; readonly outcome: ReplayHandCopy["outcome"] }
    | { readonly kind: "toggle_play" }
    | { readonly kind: "view_seat"; readonly seat: SeatPosition }
    | { readonly kind: "toggle_hands" }
    | { readonly kind: "page_hide" }
    | { readonly kind: "toggle_settings" }
    | { readonly kind: "close_settings" }
    | { readonly kind: "toggle_sound" }
    | { readonly kind: "toggle_animations" };

type LoadedInput = StepInput | MoveInput | RoundListInput | ToolsInput | OptionInput;

type Timed<Input> = { readonly at: number } & Input;

/** An input of the page, before its source stamps it with the clock's time. */
export type ReplayPageInput = LoadEvent | LoadedInput;

/** An input of the page, stamped with the logical time its source read from the clock. */
export type ReplayPageEvent = { readonly at: number } & ReplayPageInput;

/**
 * Where the page puts the focus after drawing: its root, the round list's current row, the list's toggle, the tools'
 * first item or their toggle, or the seating's start.
 */
export type ReplayFocusTarget =
    | "root"
    | "current_round"
    | "round_list_toggle"
    | "tools"
    | "tools_toggle"
    | "start";

/** The IO a transition asks of the view, which runs it after drawing the new screen. */
export type ReplayPageEffect =
    | { readonly kind: "write_address" }
    | { readonly kind: "play_sounds"; readonly cues: readonly SoundCue[] }
    | { readonly kind: "copy_text"; readonly text: string }
    | { readonly kind: "open_url"; readonly url: string }
    | { readonly kind: "save_sound"; readonly soundOn: boolean }
    | { readonly kind: "save_animations"; readonly animationsOn: boolean }
    | { readonly kind: "save_prefs"; readonly prefs: ReplayPrefs }
    | { readonly kind: "focus"; readonly target: ReplayFocusTarget }
    | { readonly kind: "fetch_observe"; readonly from: number };

export interface ReplayPageStep {
    readonly screen: ReplayScreen;
    readonly effects: readonly ReplayPageEffect[];
}

interface LoadedStep extends ReplayPageStep {
    readonly screen: LoadedReplayScreen;
}

const WRITE_ADDRESS: ReplayPageEffect = { kind: "write_address" };

function focusOn(target: ReplayFocusTarget): ReplayPageEffect {
    return { kind: "focus", target };
}

function quiet<Screen extends ReplayScreen>(
    screen: Screen,
): { readonly screen: Screen; readonly effects: readonly ReplayPageEffect[] } {
    return { effects: [], screen };
}

function isToggle(command: ReplayKeyCommand): command is ReplayToggle {
    return command === "play" || command === "view" || command === "hands" || command === "analyze";
}

function isStep(command: keyof ReplayMoves): command is StepDirection {
    return command === "next" || command === "prev";
}

function movesOf({ replay, view }: LoadedReplayScreen): ReplayMoves {
    return replayMoves(replay.navigation, view.cursor, view.bottomSeat);
}

/** Where one step toward `direction` goes from the cursor shown; null where it cannot go on. */
function stepTarget(screen: LoadedReplayScreen, direction: StepDirection): ReplayCursor | null {
    return movesOf(screen)[direction];
}

/**
 * Whether the wheel steps toward `direction` from the screen shown: past the seating, where a step goes. A wheel that
 * would take none scrolls.
 */
export function canStep(screen: ReplayScreen, direction: StepDirection): boolean {
    return (
        screen.kind === "loaded" &&
        screen.observe === null &&
        !screen.seating &&
        stepTarget(screen, direction) !== null
    );
}

/** Whether the cursor shown is where a held step pauses: a result's page or the last stop. */
function atPauseStop(screen: LoadedReplayScreen): boolean {
    return isPauseStop(screen.replay.navigation, screen.view.cursor);
}

function earliest(dues: readonly (number | null)[]): number | null {
    const set = dues.filter((due) => due !== null);
    return set.length === 0 ? null : Math.min(...set);
}

/**
 * The earliest logical time the page must be ticked at: autoplay's next move, a held button's next repeat, the hand
 * copy's notice ending, the observe stream's next request or the countdown's next second. The view keeps one timer
 * armed to it, as the live driver does to the client's deadlines.
 */
export function replayPageDeadline(screen: ReplayScreen): number | null {
    if (screen.kind === "observe_waiting") {
        return earliest([screen.stream.pollAt, screen.countdown?.redrawAt ?? null]);
    }
    if (screen.kind !== "loaded") {
        return null;
    }
    return earliest([
        screen.autoplay.dueAt,
        screen.hold?.repeatAt ?? null,
        screen.handCopy?.until ?? null,
        screen.observe?.pollAt ?? null,
    ]);
}

/** A move from the cursor shown: where to, when, and whether calls it shows are announced (a single step's). */
type CursorMove = Omit<CallMove, "from">;

function withCursor(screen: LoadedReplayScreen, move: CursorMove): LoadedReplayScreen {
    const { replay, shownCall, view } = screen;
    return {
        ...screen,
        shownCall: shownReplayCall(replay, shownCall, { ...move, from: view.cursor }),
        view: { ...view, cursor: move.to },
    };
}

/**
 * What a move to `to` asks of the view: the address written, and, while the sound is on, the sounds of the move a
 * step on to the next stop makes. A jump, a step back or a turn of a result's page plays nothing.
 */
function moveEffects(screen: LoadedReplayScreen, to: ReplayCursor): readonly ReplayPageEffect[] {
    const from = screen.view.cursor;
    if (!screen.soundOn || to.stop !== from.stop + 1) {
        return [WRITE_ADDRESS];
    }
    const { calls, navigation, tables } = screen.replay;
    const [before, after] = [from, to].map((cursor) => navigation.stops[cursor.stop].stateIndex);
    const cues = moveSoundCues(tables[before], tables[after], calls[after]);
    return cues.length === 0 ? [WRITE_ADDRESS] : [WRITE_ADDRESS, { cues, kind: "play_sounds" }];
}

function withoutPressedStep(screen: LoadedReplayScreen): LoadedReplayScreen {
    return screen.pressedStep === null ? screen : { ...screen, pressedStep: null };
}

/**
 * Autoplay playing, its next move armed from `at` at the pace of the stop shown (an observed game's own pace), the
 * seating closed.
 */
function armed(screen: LoadedReplayScreen, at: number): LoadedReplayScreen {
    const { autoplay, observe, replay, view } = screen;
    const delayMs =
        observe === null
            ? autoplayDelayMs(replay, view.cursor)
            : observeAutoplayDelayMs(replay, view.cursor);
    return {
        ...screen,
        autoplay: { ...autoplay, dueAt: at + delayMs, playing: true },
        seating: false,
    };
}

/** Whether the replay may still grow: an observe stream that has neither ended nor gone. */
function awaitsStream({ observe }: LoadedReplayScreen): boolean {
    return observe !== null && !observe.ended && !observe.gone;
}

/** Autoplay playing with no move armed: waiting at the newest stop for the stream's next records. */
function waitingForStream(screen: LoadedReplayScreen): LoadedReplayScreen {
    return { ...screen, autoplay: { ...screen.autoplay, dueAt: null, playing: true } };
}

function paused(screen: LoadedReplayScreen): LoadedReplayScreen {
    return screen.autoplay.playing
        ? { ...screen, autoplay: { ...screen.autoplay, dueAt: null, playing: false } }
        : screen;
}

function unheld(screen: LoadedReplayScreen): LoadedReplayScreen {
    return screen.hold === null ? screen : { ...screen, hold: null };
}

/** A move the reader asked for, which stops autoplay and a held step button and closes the seating. */
function moveTo(screen: LoadedReplayScreen, move: CursorMove): LoadedStep {
    return {
        effects: moveEffects(screen, move.to),
        screen: { ...withCursor(paused(unheld(screen)), move), seating: false },
    };
}

function savingPrefs(screen: LoadedReplayScreen): LoadedStep {
    const prefs = { hideHands: screen.hideHands, showTsumogiri: screen.showTsumogiri };
    return { effects: [{ kind: "save_prefs", prefs }], screen };
}

/** A loaded screen showing its view at `at`, autoplay stopped, from the opening's settings. */
function loadedScreen(
    replay: LoadedReplay,
    opening: ObserveOpening,
    shown: Pick<LoadedReplayScreen, "observe" | "seating" | "view"> & { readonly at: number },
): LoadedReplayScreen {
    const { view } = shown;
    return {
        animationsOn: opening.animationsOn,
        autoplay: { dueAt: null, playing: false },
        handCopy: null,
        hideHands: opening.prefs.hideHands,
        hold: null,
        kind: "loaded",
        observe: shown.observe,
        pressedStep: null,
        replay,
        roundListOpen: opening.roundListOpen,
        seating: shown.seating,
        settingsOpen: false,
        showTsumogiri: opening.prefs.showTsumogiri,
        shownCall: shownReplayCall(replay, null, {
            announce: false,
            at: shown.at,
            from: null,
            to: view.cursor,
        }),
        soundOn: opening.soundOn,
        toolsOpen: false,
        view,
        wheel: null,
    };
}

/**
 * A replay opened where its address says, from the seat it names; one whose address names no position, or any with the
 * sound on, opens on the seating, its start focused, unless autoplay was asked.
 */
function openedScreen(replay: LoadedReplay, opening: ReplayOpening, at: number): ReplayPageStep {
    const address = parseReplayAddress(opening.search);
    const view = resolveReplayAddress(replay.navigation, address, {
        bottomSeat: replay.firstDealerSeat,
        cursor: replay.opening,
        seatCount: replay.seatCount,
    });
    const screen = loadedScreen(replay, opening, {
        at,
        observe: null,
        seating: address.round === null || opening.soundOn,
        view,
    });
    if (opening.autoplay) {
        return { effects: [WRITE_ADDRESS], screen: armed(screen, at) };
    }
    return {
        effects: screen.seating ? [WRITE_ADDRESS, focusOn("start")] : [WRITE_ADDRESS],
        screen,
    };
}

/** A fetch's answer: a 404 the retries outlasted, another status refused, else the file read and opened. */
function onFetched(fetched: ReplayFetch, opening: ReplayOpening, at: number): ReplayPageStep {
    if (!fetched.ok) {
        const failure: ReplayFailure =
            fetched.status === HTTP_NOT_FOUND
                ? { kind: "not_found" }
                : { kind: "refused", status: fetched.status };
        return quiet({ failure, kind: "failed" });
    }
    const read = readReplay(fetched.content, "archive");
    return read.ok
        ? openedScreen(read.replay, opening, at)
        : quiet({ failure: read.unshowable, kind: "failed" });
}

/**
 * Autoplay's switch: it plays only where a next step exists, or waits at the newest stop of a stream still growing, and
 * playing ends a hold.
 */
function togglePlay(screen: LoadedReplayScreen, at: number): LoadedStep {
    if (screen.autoplay.playing) {
        return quiet(paused(screen));
    }
    if (stepTarget(screen, "next") === null) {
        return quiet(awaitsStream(screen) ? waitingForStream(unheld(screen)) : screen);
    }
    return quiet(armed(unheld(screen), at));
}

/**
 * The seat `turns` seats on from the bottom's taken to the bottom, where the cursor and the result's page stay; the
 * bottom's own (no turn) changes nothing.
 */
function switchView(screen: LoadedReplayScreen, turns: number): LoadedStep {
    if (turns % screen.replay.seatCount === 0) {
        return quiet(screen);
    }
    const bottomSeat = (screen.view.bottomSeat + turns) % screen.replay.seatCount;
    return {
        effects: [WRITE_ADDRESS],
        screen: { ...screen, view: { ...screen.view, bottomSeat } },
    };
}

function toggleHands(screen: LoadedReplayScreen): LoadedStep {
    return savingPrefs({ ...screen, hideHands: !screen.hideHands });
}

function runToggle(screen: LoadedReplayScreen, toggle: ReplayToggle, at: number): LoadedStep {
    switch (toggle) {
        case "play": {
            return togglePlay(screen, at);
        }
        case "view": {
            return switchView(screen, 1);
        }
        case "hands": {
            return toggleHands(screen);
        }
        case "analyze": {
            return sendHand(screen, "analyze_hand");
        }
        default: {
            return assertNever(toggle);
        }
    }
}

/** A key the page takes: a switch acts once per press; a held move's repeats pause where a result shows. */
function onKey(screen: LoadedReplayScreen, { at, command, repeat }: Timed<KeyInput>): LoadedStep {
    const cleared = withoutPressedStep(screen);
    if (command === null) {
        return quiet(cleared);
    }
    if (isToggle(command)) {
        return repeat ? quiet(cleared) : runToggle(cleared, command, at);
    }
    if (repeat && atPauseStop(cleared)) {
        return quiet(cleared);
    }
    const target = movesOf(cleared)[command];
    return target === null
        ? quiet(cleared)
        : moveTo(cleared, { announce: !repeat && isStep(command), at, to: target });
}

/** A step button's click: a keyboard's or an assistive technology's steps, the one ending a press is dropped. */
function onStepClick(screen: LoadedReplayScreen, direction: StepDirection, at: number): LoadedStep {
    const cleared = withoutPressedStep(screen);
    const target = screen.pressedStep === direction ? null : stepTarget(cleared, direction);
    return target === null ? quiet(cleared) : moveTo(cleared, { announce: true, at, to: target });
}

/** A primary pointer's press of a step button: one step at once, then the hold repeating it after a delay. */
function onStepPress(
    screen: LoadedReplayScreen,
    { at, direction, primary }: Timed<PressInput>,
): LoadedStep {
    const cleared = withoutPressedStep(screen);
    const first = primary ? stepTarget(cleared, direction) : null;
    if (first === null) {
        return quiet(cleared);
    }
    const moved = moveTo(cleared, { announce: true, at, to: first });
    return {
        effects: moved.effects,
        screen: {
            ...moved.screen,
            hold: { direction, repeatAt: at + HOLD_DELAY_MS },
            pressedStep: direction,
        },
    };
}

/** The hold following its pointer: the repeat waits while it is off the button and goes on when it is back. */
function onHoldPointer(screen: LoadedReplayScreen, over: boolean, at: number): LoadedStep {
    const { hold } = screen;
    if (hold === null || (hold.repeatAt !== null) === over) {
        return quiet(screen);
    }
    return quiet({ ...screen, hold: { ...hold, repeatAt: over ? at + HOLD_REPEAT_MS : null } });
}

/** The hold's press ended, or was cancelled, after which no click follows it. */
function onHoldEnd(screen: LoadedReplayScreen, cancelled: boolean): LoadedStep {
    if (screen.hold === null) {
        return quiet(screen);
    }
    return quiet({ ...screen, hold: null, pressedStep: cancelled ? null : screen.pressedStep });
}

/** How long a turning wheel holds a result's page before it steps on. */
export const WHEEL_RESULT_HOLD_MS = 500;

/**
 * A wheel turned toward a step that goes somewhere: a gesture steps once it has run far enough, then on a beat, and
 * holds each result page for `WHEEL_RESULT_HOLD_MS`, counting no distance, before it steps on as the wheel turns. It
 * never leaves the seating: a wheel is no click the browser lets a sound play after.
 */
function onWheel(screen: LoadedReplayScreen, deltaPx: number, at: number): LoadedStep {
    const target = screen.seating ? null : stepTarget(screen, deltaPx > 0 ? "next" : "prev");
    if (target === null) {
        return quiet(screen);
    }
    const { gesture, step } = wheelStep(screen.wheel, deltaPx, at);
    if (step === 0) {
        return quiet({ ...screen, wheel: gesture });
    }
    const moved = moveTo(screen, { announce: false, at, to: target });
    const wheel = atPauseStop(moved.screen)
        ? holdWheel(gesture, at + WHEEL_RESULT_HOLD_MS)
        : gesture;
    return { effects: moved.effects, screen: { ...moved.screen, wheel } };
}

/**
 * Autoplay's move on. A replay pauses on a result's page and at its last stop; an observed game crosses its results
 * and waits at the newest stop while the stream still grows.
 */
function autoplayTick(screen: LoadedReplayScreen, at: number): LoadedStep {
    const step = autoplayStep(screen.replay.navigation, screen.view.cursor);
    if (step === null) {
        return quiet(awaitsStream(screen) ? waitingForStream(screen) : paused(screen));
    }
    const moved = withCursor(screen, { announce: true, at, to: step.cursor });
    const pauses = screen.observe === null && step.pause;
    return {
        effects: moveEffects(screen, step.cursor),
        screen: pauses ? paused(moved) : armed(moved, at),
    };
}

function holdTick(screen: LoadedReplayScreen, hold: ReplayHold, at: number): LoadedStep {
    const target = atPauseStop(screen) ? null : stepTarget(screen, hold.direction);
    if (target === null) {
        return quiet(unheld(screen));
    }
    return {
        effects: moveEffects(screen, target),
        screen: {
            ...withCursor(screen, { announce: false, at, to: target }),
            hold: { ...hold, repeatAt: at + HOLD_REPEAT_MS },
        },
    };
}

/** The screen with the hand copy's notice gone once its time has come. */
function withoutPastHandCopy(screen: LoadedReplayScreen, at: number): LoadedReplayScreen {
    return screen.handCopy !== null && screen.handCopy.until <= at
        ? { ...screen, handCopy: null }
        : screen;
}

/** The observe stream's next request asked once its time has come, nothing in flight until it is answered. */
function polled(
    stream: ObserveStream,
    at: number,
): { readonly stream: ObserveStream; readonly effects: readonly ReplayPageEffect[] } {
    if (stream.pollAt === null || stream.pollAt > at) {
        return { effects: [], stream };
    }
    return {
        effects: [{ from: stream.next, kind: "fetch_observe" }],
        stream: { ...stream, pollAt: null },
    };
}

/**
 * A tick ends the hand copy's notice, asks the observe stream's next records, and moves autoplay or repeats a held
 * button, once each one's time has come; one before all of them does nothing.
 */
function onTick(shown: LoadedReplayScreen, at: number): LoadedStep {
    const notified = withoutPastHandCopy(shown, at);
    if (notified.observe === null) {
        return onPlaybackTick(notified, at);
    }
    const poll = polled(notified.observe, at);
    const stepped = onPlaybackTick(
        poll.stream === notified.observe ? notified : { ...notified, observe: poll.stream },
        at,
    );
    return { effects: [...poll.effects, ...stepped.effects], screen: stepped.screen };
}

/** A tick's autoplay move or held button's repeat, once its time has come. */
function onPlaybackTick(screen: LoadedReplayScreen, at: number): LoadedStep {
    const { autoplay, hold } = screen;
    if (autoplay.dueAt !== null && autoplay.dueAt <= at) {
        return autoplayTick(screen, at);
    }
    if (hold !== null && hold.repeatAt !== null && hold.repeatAt <= at) {
        return holdTick(screen, hold, at);
    }
    return quiet(screen);
}

function closeRoundList(screen: LoadedReplayScreen): LoadedStep {
    const closed = screen.roundListOpen ? { ...screen, roundListOpen: false } : screen;
    return { effects: [focusOn("round_list_toggle")], screen: closed };
}

/**
 * The round list opened, the tools' menu closed, with the focus on the current round's row, or closed with it back on
 * the toggle.
 */
function toggleRoundList(screen: LoadedReplayScreen): LoadedStep {
    if (screen.roundListOpen) {
        return closeRoundList(screen);
    }
    return {
        effects: [focusOn("current_round")],
        screen: { ...screen, roundListOpen: true, toolsOpen: false },
    };
}

function closeTools(screen: LoadedReplayScreen): LoadedStep {
    const closed = screen.toolsOpen ? { ...screen, toolsOpen: false } : screen;
    return { effects: [focusOn("tools_toggle")], screen: closed };
}

/** The tools' menu opened, the round list closed, with the focus on its first item, or closed with it back on the toggle. */
function toggleTools(screen: LoadedReplayScreen): LoadedStep {
    if (screen.toolsOpen) {
        return closeTools(screen);
    }
    return {
        effects: [focusOn("tools")],
        screen: { ...screen, roundListOpen: false, toolsOpen: true },
    };
}

function stepTools(screen: LoadedReplayScreen, event: ToolsInput): LoadedStep {
    switch (event.kind) {
        case "toggle_tools": {
            return toggleTools(screen);
        }
        case "close_tools": {
            return closeTools(screen);
        }
        case "dismiss_tools": {
            return quiet(screen.toolsOpen ? { ...screen, toolsOpen: false } : screen);
        }
        case "toggle_tsumogiri": {
            return savingPrefs({ ...screen, showTsumogiri: !screen.showTsumogiri });
        }
        default: {
            return assertNever(event);
        }
    }
}

/** A round chosen from the list: the move, then the list closed with the focus back on its toggle. */
function selectRound(screen: LoadedReplayScreen, cursor: ReplayCursor, at: number): LoadedStep {
    const moved = moveTo(screen, { announce: false, at, to: cursor });
    const closed = closeRoundList(moved.screen);
    return { effects: [...moved.effects, ...closed.effects], screen: closed.screen };
}

/**
 * The closed hand of the seat at the bottom, at the stop shown, as `handNotation` writes it; null under the seating or
 * for a seat holding no tile.
 */
function shownHandNotation({ replay, seating, view }: LoadedReplayScreen): string | null {
    if (seating) {
        return null;
    }
    const table = replay.tables[replay.navigation.stops[view.cursor.stop].stateIndex];
    const player = table.players.find(({ seat }) => seat === view.bottomSeat);
    return player === undefined || player.tiles.length === 0
        ? null
        : handNotation(player, table.hasAkadora);
}

/** Whether the screen shows a hand to copy or to analyse: none under the seating. */
export function showsHand(screen: ReplayScreen): boolean {
    return screen.kind === "loaded" && shownHandNotation(screen) !== null;
}

/**
 * The hand shown sent out: put on the clipboard or opened in Tenhou's analysis. Sent from the tools' menu, the menu
 * closes with the focus on its toggle.
 */
function sendHand(screen: LoadedReplayScreen, kind: "copy_hand" | "analyze_hand"): LoadedStep {
    const notation = shownHandNotation(screen);
    if (notation === null) {
        return quiet(screen);
    }
    const sent: ReplayPageEffect =
        kind === "copy_hand"
            ? { kind: "copy_text", text: notation }
            : { kind: "open_url", url: handAnalysisUrl(notation) };
    return screen.toolsOpen
        ? { effects: [sent, focusOn("tools_toggle")], screen: { ...screen, toolsOpen: false } }
        : { effects: [sent], screen };
}

/** The seating's start: the board shown, the focus on the root, where the keys step on from it. */
function start(screen: LoadedReplayScreen): LoadedStep {
    return screen.seating
        ? { effects: [focusOn("root")], screen: { ...screen, seating: false } }
        : quiet(screen);
}

function stepInput(screen: LoadedReplayScreen, event: Timed<StepInput>): LoadedStep {
    switch (event.kind) {
        case "step_click": {
            return onStepClick(screen, event.direction, event.at);
        }
        case "step_press": {
            return onStepPress(screen, event);
        }
        case "hold_pointer": {
            return onHoldPointer(screen, event.over, event.at);
        }
        case "hold_end": {
            return onHoldEnd(screen, event.cancelled);
        }
        case "wheel": {
            return onWheel(screen, event.deltaPx, event.at);
        }
        case "tick": {
            return onTick(screen, event.at);
        }
        default: {
            return assertNever(event);
        }
    }
}

function stepMove(screen: LoadedReplayScreen, event: Timed<MoveInput>): LoadedStep {
    switch (event.kind) {
        case "move": {
            return moveTo(screen, { announce: false, at: event.at, to: event.cursor });
        }
        case "key": {
            return onKey(screen, event);
        }
        case "result_page": {
            const to = { ...screen.view.cursor, page: event.page };
            return moveTo(screen, { announce: false, at: event.at, to });
        }
        case "select_round": {
            return selectRound(screen, event.cursor, event.at);
        }
        default: {
            return assertNever(event);
        }
    }
}

function stepRoundList(screen: LoadedReplayScreen, event: Timed<RoundListInput>): LoadedStep {
    switch (event.kind) {
        case "toggle_round_list": {
            return toggleRoundList(screen);
        }
        case "close_round_list": {
            return closeRoundList(screen);
        }
        case "dismiss_round_list": {
            return quiet(screen.roundListOpen ? { ...screen, roundListOpen: false } : screen);
        }
        default: {
            return assertNever(event);
        }
    }
}

/** The settings menu opened or closed, or one of its switches turned, which the view keeps in this browser. */
function stepSettings(screen: LoadedReplayScreen, command: SettingsMenuCommand): LoadedStep {
    const { menu, saved } = stepSettingsMenu(
        { animationsOn: screen.animationsOn, open: screen.settingsOpen, soundOn: screen.soundOn },
        command,
    );
    if (saved === "sound") {
        return {
            effects: [{ kind: "save_sound", soundOn: menu.soundOn }],
            screen: { ...screen, soundOn: menu.soundOn },
        };
    }
    if (saved === "animations") {
        return {
            effects: [{ animationsOn: menu.animationsOn, kind: "save_animations" }],
            screen: { ...screen, animationsOn: menu.animationsOn },
        };
    }
    return quiet(
        menu.open === screen.settingsOpen ? screen : { ...screen, settingsOpen: menu.open },
    );
}

/**
 * Inputs that leave the settings menu as it is: its own, the deadline's, the clipboard's answer, the page hiding and a
 * click anywhere.
 */
const KEEPS_SETTINGS: ReadonlySet<LoadedInput["kind"]> = new Set([
    "toggle_settings",
    "close_settings",
    "toggle_sound",
    "toggle_animations",
    "tick",
    "hand_copy",
    "page_hide",
    "dismiss_round_list",
    "dismiss_tools",
]);

/** Whether the input is the reader's own, a key the page takes included, which closes the settings menu. */
function closesSettings(event: LoadedInput): boolean {
    return event.kind === "key" ? event.command !== null : !KEEPS_SETTINGS.has(event.kind);
}

function settingsClosed(step: LoadedStep): LoadedStep {
    return step.screen.settingsOpen
        ? { ...step, screen: { ...step.screen, settingsOpen: false } }
        : step;
}

function stepOption(screen: LoadedReplayScreen, event: Timed<OptionInput>): LoadedStep {
    switch (event.kind) {
        case "start": {
            return start(screen);
        }
        case "copy_hand":
        case "analyze_hand": {
            return sendHand(screen, event.kind);
        }
        case "hand_copy": {
            return quiet({
                ...screen,
                handCopy: { outcome: event.outcome, until: event.at + HAND_COPY_NOTICE_MS },
            });
        }
        case "toggle_play": {
            return togglePlay(screen, event.at);
        }
        case "view_seat": {
            return switchView(screen, SEAT_POSITIONS.indexOf(event.seat));
        }
        case "toggle_hands": {
            return toggleHands(screen);
        }
        case "page_hide": {
            return quiet(screen.observe === null ? paused(unheld(screen)) : unheld(screen));
        }
        default: {
            return stepSettings(screen, event.kind);
        }
    }
}

/** One input of a loaded replay; the reader's own input closes the settings menu, as live's page controls do. */
function stepLoaded(screen: LoadedReplayScreen, event: Timed<LoadedInput>): LoadedStep {
    const stepped = stepLoadedInput(screen, event);
    return closesSettings(event) ? settingsClosed(stepped) : stepped;
}

function stepLoadedInput(screen: LoadedReplayScreen, event: Timed<LoadedInput>): LoadedStep {
    switch (event.kind) {
        case "step_click":
        case "step_press":
        case "hold_pointer":
        case "hold_end":
        case "wheel":
        case "tick": {
            return stepInput(screen, event);
        }
        case "move":
        case "key":
        case "result_page":
        case "select_round": {
            return stepMove(screen, event);
        }
        case "toggle_round_list":
        case "close_round_list":
        case "dismiss_round_list": {
            return stepRoundList(screen, event);
        }
        case "toggle_tools":
        case "close_tools":
        case "dismiss_tools":
        case "toggle_tsumogiri": {
            return stepTools(screen, event);
        }
        default: {
            return stepOption(screen, event);
        }
    }
}

const STREAM_START: ObserveStream = {
    content: new Uint8Array(),
    ended: false,
    gone: false,
    next: 0,
    pollAt: null,
};

function appendBytes(head: Uint8Array, tail: Uint8Array): Uint8Array {
    const joined = new Uint8Array(head.length + tail.length);
    joined.set(head);
    joined.set(tail, head.length);
    return joined;
}

/** The stream after an answer: its records appended, its cursor moved on, the next request due unless it ended. */
function answeredStream(stream: ObserveStream, answer: ObserveAnswer, at: number): ObserveStream {
    return {
        content:
            answer.records.length === 0
                ? stream.content
                : appendBytes(stream.content, answer.records),
        ended: answer.ended,
        gone: false,
        next: answer.next,
        pollAt: answer.ended ? null : at + OBSERVE_POLL_MS,
    };
}

/** The stream after a request that failed: what it holds kept, asked again after the poll's wait, or gone on a 404. */
function failedStream(stream: ObserveStream, status: number | null, at: number): ObserveStream {
    return status === HTTP_NOT_FOUND
        ? { ...stream, gone: true, pollAt: null }
        : { ...stream, pollAt: at + OBSERVE_POLL_MS };
}

/** The time a countdown draws next: its next whole second left, none once it reached zero. */
function nextRedraw(availableAt: number, at: number): number | null {
    const remaining = availableAt - at;
    return remaining <= 0 ? null : at + (remaining % SECOND_MS || SECOND_MS);
}

function countdownOf(answer: ObserveAnswer, at: number): ObserveCountdown {
    const availableAt = at + answer.availableInMs;
    return {
        availableAt,
        gameType: answer.gameType,
        players: answer.players,
        redrawAt: nextRedraw(availableAt, at),
        remainingMs: answer.availableInMs,
    };
}

/**
 * An observed game opened on its first playable records, autoplay on, with no seating, from the first dealer's seat:
 * at the first deal for a viewer who saw the countdown, else at the newest stop.
 */
function observedScreen(
    replay: LoadedReplay,
    stream: ObserveStream,
    {
        at,
        opening,
        sawCountdown,
    }: { readonly at: number; readonly opening: ObserveOpening; readonly sawCountdown: boolean },
): ReplayPageStep {
    const cursor = sawCountdown
        ? replay.opening
        : (lastCursor(replay.navigation) ?? replay.opening);
    const screen = loadedScreen(replay, opening, {
        at,
        observe: stream,
        seating: false,
        view: { bottomSeat: replay.firstDealerSeat, cursor },
    });
    return quiet(armed(screen, at));
}

/** Whether records too few to play are worth waiting on: none yet, or a game start not followed by a deal yet. */
function awaitsPlayable(unshowable: ReplayUnshowable): boolean {
    return (
        unshowable.kind === "empty" || (unshowable.kind === "no_deal" && unshowable.damage === null)
    );
}

/** An observe request's outcome: its answer with where the game opens, or the status it failed with, null offline. */
type ObserveOutcome =
    | { readonly ok: true; readonly answer: ObserveAnswer; readonly opening: ObserveOpening }
    | { readonly ok: false; readonly status: number | null };

function outcomeOf(event: ObserveEvent): ObserveOutcome {
    if (event.kind === "observe_unreachable") {
        return { ok: false, status: null };
    }
    const { fetched, opening } = event;
    return fetched.ok ? { answer: fetched.answer, ok: true, opening } : fetched;
}

/**
 * An answer before the game can be played: a 404 shows the game gone, another failure asks again later; records that
 * play open the board, else the countdown shows from the answer.
 */
function onWaitingAnswer(screen: ObserveWaitingScreen, event: Timed<ObserveEvent>): ReplayPageStep {
    const outcome = outcomeOf(event);
    if (outcome.ok) {
        return onWaitingRecords(screen, outcome, event.at);
    }
    return outcome.status === HTTP_NOT_FOUND
        ? quiet({ kind: "observe_gone" })
        : quiet({ ...screen, stream: failedStream(screen.stream, outcome.status, event.at) });
}

/** Records before the game could be played: they open the board once they play, else the countdown shows. */
function onWaitingRecords(
    screen: ObserveWaitingScreen,
    { answer, opening }: Extract<ObserveOutcome, { readonly ok: true }>,
    at: number,
): ReplayPageStep {
    const stream = answeredStream(screen.stream, answer, at);
    const read = readReplay(stream.content, "observe");
    if (read.ok) {
        return observedScreen(read.replay, stream, {
            at,
            opening,
            sawCountdown: screen.countdown !== null,
        });
    }
    if (stream.ended || !awaitsPlayable(read.unshowable)) {
        return quiet({ failure: read.unshowable, kind: "failed" });
    }
    return quiet({ countdown: countdownOf(answer, at), kind: "observe_waiting", stream });
}

/**
 * Autoplay waiting at the newest stop moves on once the stream brought a stop after it, and stops once the stream can
 * bring none.
 */
function resumedAutoplay(screen: LoadedReplayScreen, at: number): LoadedReplayScreen {
    const { autoplay } = screen;
    if (!autoplay.playing || autoplay.dueAt !== null) {
        return screen;
    }
    if (stepTarget(screen, "next") !== null) {
        return { ...screen, autoplay: { ...autoplay, dueAt: at } };
    }
    return awaitsStream(screen) ? screen : paused(screen);
}

/**
 * An answer while the board shows: new records extend the replay in place, keeping the view, the reader's settings and
 * autoplay; a 404 keeps the board and stops asking; another failure asks again later.
 */
function onLoadedAnswer(
    screen: LoadedReplayScreen,
    stream: ObserveStream,
    event: Timed<ObserveEvent>,
): ReplayPageStep {
    const outcome = outcomeOf(event);
    if (!outcome.ok) {
        const observe = failedStream(stream, outcome.status, event.at);
        return quiet(resumedAutoplay({ ...screen, observe }, event.at));
    }
    return extendedScreen(screen, answeredStream(stream, outcome.answer, event.at), event.at);
}

/** The replay rebuilt from the stream's records when an answer brought new ones, the view and autoplay kept. */
function extendedScreen(
    screen: LoadedReplayScreen,
    observe: ObserveStream,
    at: number,
): ReplayPageStep {
    if (observe.content === screen.observe?.content) {
        return quiet(resumedAutoplay({ ...screen, observe }, at));
    }
    const read = readReplay(observe.content, "observe");
    if (!read.ok) {
        return quiet({ failure: read.unshowable, kind: "failed" });
    }
    return quiet(resumedAutoplay({ ...screen, observe, replay: read.replay }, at));
}

function onObserveEvent(screen: ReplayScreen, event: Timed<ObserveEvent>): ReplayPageStep {
    if (screen.kind === "observe_waiting") {
        return onWaitingAnswer(screen, event);
    }
    if (screen.kind === "loaded" && screen.observe !== null) {
        return onLoadedAnswer(screen, screen.observe, event);
    }
    return quiet(screen);
}

/** A tick before the game can be played: the stream's next request and the countdown's next second, once due. */
function onWaitingTick(screen: ObserveWaitingScreen, at: number): ReplayPageStep {
    const poll = polled(screen.stream, at);
    const { countdown } = screen;
    const redrawn =
        countdown === null || countdown.redrawAt === null || countdown.redrawAt > at
            ? countdown
            : {
                  ...countdown,
                  redrawAt: nextRedraw(countdown.availableAt, at),
                  remainingMs: Math.max(0, countdown.availableAt - at),
              };
    if (poll.stream === screen.stream && redrawn === countdown) {
        return quiet(screen);
    }
    return {
        effects: poll.effects,
        screen: { ...screen, countdown: redrawn, stream: poll.stream },
    };
}

/** An observed game's own transition writes no address: the page names only the game. */
function withoutAddress(step: LoadedStep): LoadedStep {
    return step.screen.observe === null
        ? step
        : { ...step, effects: step.effects.filter((effect) => effect.kind !== "write_address") };
}

const OBSERVE_IGNORED_INPUTS: ReadonlySet<LoadedInput["kind"]> = new Set([
    "move",
    "result_page",
    "select_round",
    "step_click",
    "step_press",
    "wheel",
    "toggle_play",
]);

function movesObservedCursor(event: LoadedInput): boolean {
    if (event.kind === "key") {
        return event.command === "play" || (event.command !== null && !isToggle(event.command));
    }
    return OBSERVE_IGNORED_INPUTS.has(event.kind);
}

function stepOther(screen: ReplayScreen, event: Timed<LoadedInput>): ReplayPageStep {
    if (screen.kind === "loaded" && screen.observe !== null && movesObservedCursor(event)) {
        return quiet(screen);
    }
    if (screen.kind === "loaded") {
        return withoutAddress(stepLoaded(screen, event));
    }
    if (screen.kind === "observe_waiting" && event.kind === "tick") {
        return onWaitingTick(screen, event.at);
    }
    return quiet(screen);
}

/**
 * The replay page's transition: the screen after `event` and the IO it asks of the view (writing the address, playing
 * a step's sounds, saving the reader's settings or the sound's, moving the focus). It reads no clock and arms no timer; the deadlines it keeps
 * (`replayPageDeadline`) come back as ticks. A move with nowhere to go, and any input the screen shown cannot take,
 * leaves the screen as it was, the same object.
 */
export function stepReplayPage(screen: ReplayScreen, event: ReplayPageEvent): ReplayPageStep {
    switch (event.kind) {
        case "load_started": {
            return quiet({ kind: "loading", waiting: false });
        }
        case "load_waiting": {
            return quiet(screen.kind === "loading" ? { kind: "loading", waiting: true } : screen);
        }
        case "load_unreachable": {
            return quiet(
                screen.kind === "loading"
                    ? { failure: { kind: "unreachable" }, kind: "failed" }
                    : screen,
            );
        }
        case "fetched": {
            return screen.kind === "loading"
                ? onFetched(event.fetched, event.opening, event.at)
                : quiet(screen);
        }
        case "observe_started": {
            return {
                effects: [{ from: 0, kind: "fetch_observe" }],
                screen: { countdown: null, kind: "observe_waiting", stream: STREAM_START },
            };
        }
        case "observe_fetched":
        case "observe_unreachable": {
            return onObserveEvent(screen, event);
        }
        case "show_failed": {
            return quiet({ failure: { kind: "show_failed" }, kind: "failed" });
        }
        default: {
            return stepOther(screen, event);
        }
    }
}
