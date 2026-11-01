import { type SoundCue, moveSoundCues } from "@/entities/client";
import { type ReplayMoves, replayMoves } from "@/entities/replay/lib/replay-display";
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
} from "@/entities/replay/model/replay-autoplay";
import { type ShownReplayCall, shownReplayCall } from "@/entities/replay/model/replay-calls";
import { type ReplayCursor } from "@/entities/replay/model/replay-cursor";
import { type ReplayPrefs } from "@/entities/replay/model/replay-prefs";
import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table";
import { type ReplayFetch } from "@/shared/api";
import { type WheelGesture, assertNever, wheelStep } from "@/shared/lib";

/** The way a step button steps, which a pointer may hold to repeat. */
export type StepDirection = "next" | "prev";

/** A held step button steps from its press, again after this delay, then every `HOLD_REPEAT_MS`. */
export const HOLD_DELAY_MS = 350;
export const HOLD_REPEAT_MS = 120;

const HTTP_NOT_FOUND = 404;

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

export interface LoadedReplayScreen {
    readonly kind: "loaded";
    readonly replay: LoadedReplay;
    readonly view: ReplayView;
    readonly roundListOpen: boolean;
    readonly autoplay: ReplayAutoplay;
    /** Whether the other seats' hands hide, as a seat would see the table. */
    readonly hideHands: boolean;
    /** Whether a step on plays its move's sounds, a setting the live game shares. */
    readonly soundOn: boolean;
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
}

export type ReplayScreen =
    | { readonly kind: "loading"; readonly waiting: boolean }
    | { readonly kind: "failed"; readonly failure: ReplayFailure }
    | LoadedReplayScreen;

/** The switches among the key commands, which act once per press however long the key is held. */
type ReplayToggle = "play" | "view" | "hands";

/** What a key does on the page: a move, autoplay's switch, the next seat's view, or the other hands' switch. */
export type ReplayKeyCommand = keyof ReplayMoves | ReplayToggle;

/**
 * Where a fetched replay opens: the page's address, the reader's settings, the game's sound setting, and the round
 * list and autoplay asked.
 */
export interface ReplayOpening {
    readonly search: string;
    readonly prefs: ReplayPrefs;
    readonly soundOn: boolean;
    readonly roundListOpen: boolean;
    readonly autoplay: boolean;
}

type LoadEvent =
    | { readonly kind: "load_started" }
    | { readonly kind: "load_waiting" }
    | { readonly kind: "load_unreachable" }
    | { readonly kind: "fetched"; readonly fetched: ReplayFetch; readonly opening: ReplayOpening }
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

/**
 * The seating's start, the options, a seat chosen to view from (its plate or score, by board position), the page
 * hiding, and the settings menu opened or closed and its sound switch.
 */
type OptionInput =
    | { readonly kind: "start" }
    | { readonly kind: "toggle_play" }
    | { readonly kind: "view_seat"; readonly seat: SeatPosition }
    | { readonly kind: "toggle_hands" }
    | { readonly kind: "page_hide" }
    | { readonly kind: "toggle_settings" }
    | { readonly kind: "close_settings" }
    | { readonly kind: "toggle_sound" };

type LoadedInput = StepInput | MoveInput | RoundListInput | OptionInput;

type Timed<Input> = { readonly at: number } & Input;

/** An input of the page, before its source stamps it with the clock's time. */
export type ReplayPageInput = LoadEvent | LoadedInput;

/** An input of the page, stamped with the logical time its source read from the clock. */
export type ReplayPageEvent = { readonly at: number } & ReplayPageInput;

/**
 * Where the page puts the focus after drawing: its root, the round list's current row, the list's toggle, or the
 * seating's start.
 */
export type ReplayFocusTarget = "root" | "current_round" | "round_list_toggle" | "start";

/** The IO a transition asks of the view, which runs it after drawing the new screen. */
export type ReplayPageEffect =
    | { readonly kind: "write_address" }
    | { readonly kind: "play_sounds"; readonly cues: readonly SoundCue[] }
    | { readonly kind: "save_sound"; readonly soundOn: boolean }
    | { readonly kind: "save_prefs"; readonly prefs: ReplayPrefs }
    | { readonly kind: "focus"; readonly target: ReplayFocusTarget };

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
    return command === "play" || command === "view" || command === "hands";
}

/** Where one step toward `direction` goes from the cursor shown; null where it cannot go on. */
function stepTarget(screen: LoadedReplayScreen, direction: StepDirection): ReplayCursor | null {
    return replayMoves(screen.replay.navigation, screen.view.cursor)[direction];
}

/**
 * Whether the wheel steps toward `direction` from the screen shown: past the seating, where a step goes. A wheel that
 * would take none scrolls.
 */
export function canStep(screen: ReplayScreen, direction: StepDirection): boolean {
    return screen.kind === "loaded" && !screen.seating && stepTarget(screen, direction) !== null;
}

/** Whether the cursor shown is where a continuous move pauses: a result's page or the last stop. */
function atPauseStop(screen: LoadedReplayScreen): boolean {
    return isPauseStop(screen.replay.navigation, screen.view.cursor);
}

/**
 * The earliest logical time the page must be ticked at: autoplay's next move or a held button's next repeat. The view
 * keeps one timer armed to it, as the live driver does to the client's deadlines.
 */
export function replayPageDeadline(screen: ReplayScreen): number | null {
    if (screen.kind !== "loaded") {
        return null;
    }
    const dues = [screen.autoplay.dueAt, screen.hold?.repeatAt ?? null].filter(
        (due) => due !== null,
    );
    return dues.length === 0 ? null : Math.min(...dues);
}

function withCursor(
    screen: LoadedReplayScreen,
    cursor: ReplayCursor,
    at: number,
): LoadedReplayScreen {
    const { replay, shownCall, view } = screen;
    return {
        ...screen,
        shownCall: shownReplayCall(replay, shownCall, { at, from: view.cursor, to: cursor }),
        view: { ...view, cursor },
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

/** Autoplay playing, its next move armed from `at` at the pace of the stop shown, the seating closed. */
function armed(screen: LoadedReplayScreen, at: number): LoadedReplayScreen {
    const { autoplay, replay, view } = screen;
    const dueAt = at + autoplayDelayMs(replay, view.cursor);
    return { ...screen, autoplay: { ...autoplay, dueAt, playing: true }, seating: false };
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
function moveTo(screen: LoadedReplayScreen, cursor: ReplayCursor, at: number): LoadedStep {
    return {
        effects: moveEffects(screen, cursor),
        screen: { ...withCursor(paused(unheld(screen)), cursor, at), seating: false },
    };
}

function savingPrefs(screen: LoadedReplayScreen): LoadedStep {
    const prefs = { hideHands: screen.hideHands };
    return { effects: [{ kind: "save_prefs", prefs }], screen };
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
    const screen: LoadedReplayScreen = {
        autoplay: { dueAt: null, playing: false },
        hideHands: opening.prefs.hideHands,
        hold: null,
        kind: "loaded",
        pressedStep: null,
        replay,
        roundListOpen: opening.roundListOpen,
        seating: address.round === null || opening.soundOn,
        settingsOpen: false,
        shownCall: shownReplayCall(replay, null, { at, from: null, to: view.cursor }),
        soundOn: opening.soundOn,
        view,
        wheel: null,
    };
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
    const read = readReplay(fetched.text);
    return read.ok
        ? openedScreen(read.replay, opening, at)
        : quiet({ failure: read.unshowable, kind: "failed" });
}

/** Autoplay's switch: it plays only where a next step exists, and playing ends a hold. */
function togglePlay(screen: LoadedReplayScreen, at: number): LoadedStep {
    if (screen.autoplay.playing || stepTarget(screen, "next") === null) {
        return quiet(paused(screen));
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
    const target = replayMoves(cleared.replay.navigation, cleared.view.cursor)[command];
    return target === null ? quiet(cleared) : moveTo(cleared, target, at);
}

/** A step button's click: a keyboard's or an assistive technology's steps, the one ending a press is dropped. */
function onStepClick(screen: LoadedReplayScreen, direction: StepDirection, at: number): LoadedStep {
    const cleared = withoutPressedStep(screen);
    const target = screen.pressedStep === direction ? null : stepTarget(cleared, direction);
    return target === null ? quiet(cleared) : moveTo(cleared, target, at);
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
    const moved = moveTo(cleared, first, at);
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

/**
 * A wheel turned toward a step that goes somewhere: a gesture steps once it has run far enough, then on a beat, and
 * once it reaches a result or the end it steps no more until it rests or turns back. It never leaves the seating: a
 * wheel is no click the browser lets a sound play after.
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
    const moved = moveTo(screen, target, at);
    return {
        effects: moved.effects,
        screen: { ...moved.screen, wheel: { ...gesture, halted: atPauseStop(moved.screen) } },
    };
}

function autoplayTick(screen: LoadedReplayScreen, at: number): LoadedStep {
    const step = autoplayStep(screen.replay.navigation, screen.view.cursor);
    if (step === null) {
        return quiet(paused(screen));
    }
    const moved = withCursor(screen, step.cursor, at);
    return {
        effects: moveEffects(screen, step.cursor),
        screen: step.pause ? paused(moved) : armed(moved, at),
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
            ...withCursor(screen, target, at),
            hold: { ...hold, repeatAt: at + HOLD_REPEAT_MS },
        },
    };
}

/** A tick moves autoplay or repeats a held button once its time has come; one before both does nothing. */
function onTick(screen: LoadedReplayScreen, at: number): LoadedStep {
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

/** The round list opened with the focus on the current round's row, or closed with it back on the toggle. */
function toggleRoundList(screen: LoadedReplayScreen): LoadedStep {
    if (screen.roundListOpen) {
        return closeRoundList(screen);
    }
    return { effects: [focusOn("current_round")], screen: { ...screen, roundListOpen: true } };
}

/** A round chosen from the list: the move, then the list closed with the focus back on its toggle. */
function selectRound(screen: LoadedReplayScreen, cursor: ReplayCursor, at: number): LoadedStep {
    const moved = moveTo(screen, cursor, at);
    const closed = closeRoundList(moved.screen);
    return { effects: [...moved.effects, ...closed.effects], screen: closed.screen };
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
            return moveTo(screen, event.cursor, event.at);
        }
        case "key": {
            return onKey(screen, event);
        }
        case "result_page": {
            return moveTo(screen, { ...screen.view.cursor, page: event.page }, event.at);
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

/** The settings menu opened or closed, or its sound switch turned, which the view keeps in this browser. */
function stepSettings(
    screen: LoadedReplayScreen,
    kind: "toggle_settings" | "close_settings" | "toggle_sound",
): LoadedStep {
    if (kind === "toggle_sound") {
        const soundOn = !screen.soundOn;
        return { effects: [{ kind: "save_sound", soundOn }], screen: { ...screen, soundOn } };
    }
    const settingsOpen = kind === "toggle_settings" && !screen.settingsOpen;
    return quiet(settingsOpen === screen.settingsOpen ? screen : { ...screen, settingsOpen });
}

function stepOption(screen: LoadedReplayScreen, event: Timed<OptionInput>): LoadedStep {
    switch (event.kind) {
        case "start": {
            return start(screen);
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
            return quiet(paused(unheld(screen)));
        }
        default: {
            return stepSettings(screen, event.kind);
        }
    }
}

function stepLoaded(screen: LoadedReplayScreen, event: Timed<LoadedInput>): LoadedStep {
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
        default: {
            return stepOption(screen, event);
        }
    }
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
        case "show_failed": {
            return quiet({ failure: { kind: "show_failed" }, kind: "failed" });
        }
        default: {
            return screen.kind === "loaded" ? stepLoaded(screen, event) : quiet(screen);
        }
    }
}
