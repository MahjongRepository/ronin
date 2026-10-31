import {
    type AutoplayState,
    type LoadedReplay,
    type ReplayCursor,
    type ReplayMoves,
    type ReplayPrefs,
    type ReplayUnshowable,
    type ReplayView,
    type StepDirection,
    autoplayDelayMs,
    autoplayStep,
    isPauseStop,
    parseReplayAddress,
    readReplay,
    replayMoves,
    resolveReplayAddress,
} from "@/entities/replay";
import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table";
import { type ReplayFetch } from "@/shared/api";
import { type WheelGesture, assertNever, wheelStep } from "@/shared/lib";

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

export interface LoadedScreen {
    readonly kind: "loaded";
    readonly replay: LoadedReplay;
    readonly view: ReplayView;
    readonly roundListOpen: boolean;
    readonly autoplay: ReplayAutoplay;
    /** Whether the other seats' hands hide, as a seat would see the table. */
    readonly hideHands: boolean;
    readonly hold: ReplayHold | null;
    /** Whether the seating shows over the board: a replay opened at its start, until the reader starts or moves. */
    readonly seating: boolean;
    /** The step button whose press stepped already, so the click that press ends in is dropped, once. */
    readonly pressedStep: StepDirection | null;
    readonly wheel: WheelGesture | null;
}

export type ReplayScreen =
    | { readonly kind: "loading"; readonly waiting: boolean }
    | { readonly kind: "failed"; readonly failure: ReplayFailure }
    | LoadedScreen;

/** The switches among the key commands, which act once per press however long the key is held. */
type ReplayToggle = "play" | "view" | "hands";

/** What a key does on the page: a move, autoplay's switch, the next seat's view, or the other hands' switch. */
export type ReplayKeyCommand = keyof ReplayMoves | ReplayToggle;

/** Where a fetched replay opens: the page's address, the reader's settings, and the round list and autoplay asked. */
export interface ReplayOpening {
    readonly search: string;
    readonly prefs: ReplayPrefs;
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
 * The seating's start, the options, a seat chosen to view from (its plate or score, by board position) and the page
 * hiding.
 */
type OptionInput =
    | { readonly kind: "start" }
    | { readonly kind: "toggle_play" }
    | { readonly kind: "view_seat"; readonly seat: SeatPosition }
    | { readonly kind: "toggle_hands" }
    | { readonly kind: "page_hide" };

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
    | { readonly kind: "save_prefs"; readonly prefs: ReplayPrefs }
    | { readonly kind: "focus"; readonly target: ReplayFocusTarget };

export interface ReplayPageStep {
    readonly screen: ReplayScreen;
    readonly effects: readonly ReplayPageEffect[];
}

interface LoadedStep extends ReplayPageStep {
    readonly screen: LoadedScreen;
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
function stepTarget(screen: LoadedScreen, direction: StepDirection): ReplayCursor | null {
    return replayMoves(screen.replay.navigation, screen.view.cursor)[direction];
}

/** Whether a step toward `direction` goes anywhere from the screen shown: a wheel that would take none scrolls. */
export function canStep(screen: ReplayScreen, direction: StepDirection): boolean {
    return screen.kind === "loaded" && stepTarget(screen, direction) !== null;
}

/** Whether the cursor shown is where a continuous move pauses: a result's page or the last stop. */
function atPauseStop(screen: LoadedScreen): boolean {
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

function withCursor(screen: LoadedScreen, cursor: ReplayCursor): LoadedScreen {
    return { ...screen, view: { ...screen.view, cursor } };
}

function withoutPressedStep(screen: LoadedScreen): LoadedScreen {
    return screen.pressedStep === null ? screen : { ...screen, pressedStep: null };
}

/** Autoplay playing, its next move armed from `at` at the pace of the stop shown, the seating closed. */
function armed(screen: LoadedScreen, at: number): LoadedScreen {
    const { autoplay, replay, view } = screen;
    const dueAt = at + autoplayDelayMs(replay, view.cursor);
    return { ...screen, autoplay: { ...autoplay, dueAt, playing: true }, seating: false };
}

function paused(screen: LoadedScreen): LoadedScreen {
    return screen.autoplay.playing
        ? { ...screen, autoplay: { ...screen.autoplay, dueAt: null, playing: false } }
        : screen;
}

function unheld(screen: LoadedScreen): LoadedScreen {
    return screen.hold === null ? screen : { ...screen, hold: null };
}

/** A move the reader asked for, which stops autoplay and a held step button and closes the seating. */
function moveTo(screen: LoadedScreen, cursor: ReplayCursor): LoadedStep {
    return {
        effects: [WRITE_ADDRESS],
        screen: { ...withCursor(paused(unheld(screen)), cursor), seating: false },
    };
}

function savingPrefs(screen: LoadedScreen): LoadedStep {
    const prefs = { hideHands: screen.hideHands };
    return { effects: [{ kind: "save_prefs", prefs }], screen };
}

/**
 * A replay opened where its address says, from the seat it names; one whose address names no position opens on the
 * seating, its start focused, unless autoplay was asked.
 */
function openedScreen(replay: LoadedReplay, opening: ReplayOpening, at: number): ReplayPageStep {
    const address = parseReplayAddress(opening.search);
    const view = resolveReplayAddress(replay.navigation, address, {
        bottomSeat: replay.firstDealerSeat,
        cursor: replay.opening,
        seatCount: replay.seatCount,
    });
    const screen: LoadedScreen = {
        autoplay: { dueAt: null, playing: false },
        hideHands: opening.prefs.hideHands,
        hold: null,
        kind: "loaded",
        pressedStep: null,
        replay,
        roundListOpen: opening.roundListOpen,
        seating: address.round === null,
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
function togglePlay(screen: LoadedScreen, at: number): LoadedStep {
    if (screen.autoplay.playing || stepTarget(screen, "next") === null) {
        return quiet(paused(screen));
    }
    return quiet(armed(unheld(screen), at));
}

/**
 * The seat `turns` seats on from the bottom's taken to the bottom, where the cursor and the result's page stay; the
 * bottom's own (no turn) changes nothing.
 */
function switchView(screen: LoadedScreen, turns: number): LoadedStep {
    if (turns % screen.replay.seatCount === 0) {
        return quiet(screen);
    }
    const bottomSeat = (screen.view.bottomSeat + turns) % screen.replay.seatCount;
    return {
        effects: [WRITE_ADDRESS],
        screen: { ...screen, view: { ...screen.view, bottomSeat } },
    };
}

function toggleHands(screen: LoadedScreen): LoadedStep {
    return savingPrefs({ ...screen, hideHands: !screen.hideHands });
}

function runToggle(screen: LoadedScreen, toggle: ReplayToggle, at: number): LoadedStep {
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
function onKey(screen: LoadedScreen, { at, command, repeat }: Timed<KeyInput>): LoadedStep {
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
    return target === null ? quiet(cleared) : moveTo(cleared, target);
}

/** A step button's click: a keyboard's or an assistive technology's steps, the one ending a press is dropped. */
function onStepClick(screen: LoadedScreen, direction: StepDirection): LoadedStep {
    const cleared = withoutPressedStep(screen);
    const target = screen.pressedStep === direction ? null : stepTarget(cleared, direction);
    return target === null ? quiet(cleared) : moveTo(cleared, target);
}

/** A primary pointer's press of a step button: one step at once, then the hold repeating it after a delay. */
function onStepPress(
    screen: LoadedScreen,
    { at, direction, primary }: Timed<PressInput>,
): LoadedStep {
    const cleared = withoutPressedStep(screen);
    const first = primary ? stepTarget(cleared, direction) : null;
    if (first === null) {
        return quiet(cleared);
    }
    const moved = moveTo(cleared, first);
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
function onHoldPointer(screen: LoadedScreen, over: boolean, at: number): LoadedStep {
    const { hold } = screen;
    if (hold === null || (hold.repeatAt !== null) === over) {
        return quiet(screen);
    }
    return quiet({ ...screen, hold: { ...hold, repeatAt: over ? at + HOLD_REPEAT_MS : null } });
}

/** The hold's press ended, or was cancelled, after which no click follows it. */
function onHoldEnd(screen: LoadedScreen, cancelled: boolean): LoadedStep {
    if (screen.hold === null) {
        return quiet(screen);
    }
    return quiet({ ...screen, hold: null, pressedStep: cancelled ? null : screen.pressedStep });
}

/**
 * A wheel turned toward a step that goes somewhere: a gesture steps once it has run far enough, then on a beat, and
 * once it reaches a result or the end it steps no more until it rests or turns back.
 */
function onWheel(screen: LoadedScreen, deltaPx: number, at: number): LoadedStep {
    const target = stepTarget(screen, deltaPx > 0 ? "next" : "prev");
    if (target === null) {
        return quiet(screen);
    }
    const { gesture, step } = wheelStep(screen.wheel, deltaPx, at);
    if (step === 0) {
        return quiet({ ...screen, wheel: gesture });
    }
    const moved = moveTo(screen, target);
    return {
        effects: moved.effects,
        screen: { ...moved.screen, wheel: { ...gesture, halted: atPauseStop(moved.screen) } },
    };
}

function autoplayTick(screen: LoadedScreen, at: number): LoadedStep {
    const step = autoplayStep(screen.replay.navigation, screen.view.cursor);
    if (step === null) {
        return quiet(paused(screen));
    }
    const moved = withCursor(screen, step.cursor);
    return { effects: [WRITE_ADDRESS], screen: step.pause ? paused(moved) : armed(moved, at) };
}

function holdTick(screen: LoadedScreen, hold: ReplayHold, at: number): LoadedStep {
    const target = atPauseStop(screen) ? null : stepTarget(screen, hold.direction);
    if (target === null) {
        return quiet(unheld(screen));
    }
    return {
        effects: [WRITE_ADDRESS],
        screen: { ...withCursor(screen, target), hold: { ...hold, repeatAt: at + HOLD_REPEAT_MS } },
    };
}

/** A tick moves autoplay or repeats a held button once its time has come; one before both does nothing. */
function onTick(screen: LoadedScreen, at: number): LoadedStep {
    const { autoplay, hold } = screen;
    if (autoplay.dueAt !== null && autoplay.dueAt <= at) {
        return autoplayTick(screen, at);
    }
    if (hold !== null && hold.repeatAt !== null && hold.repeatAt <= at) {
        return holdTick(screen, hold, at);
    }
    return quiet(screen);
}

function closeRoundList(screen: LoadedScreen): LoadedStep {
    const closed = screen.roundListOpen ? { ...screen, roundListOpen: false } : screen;
    return { effects: [focusOn("round_list_toggle")], screen: closed };
}

/** The round list opened with the focus on the current round's row, or closed with it back on the toggle. */
function toggleRoundList(screen: LoadedScreen): LoadedStep {
    if (screen.roundListOpen) {
        return closeRoundList(screen);
    }
    return { effects: [focusOn("current_round")], screen: { ...screen, roundListOpen: true } };
}

/** A round chosen from the list: the move, then the list closed with the focus back on its toggle. */
function selectRound(screen: LoadedScreen, cursor: ReplayCursor): LoadedStep {
    const moved = moveTo(screen, cursor);
    const closed = closeRoundList(moved.screen);
    return { effects: [...moved.effects, ...closed.effects], screen: closed.screen };
}

/** The seating's start: the board shown, the focus on the root, where the keys step on from it. */
function start(screen: LoadedScreen): LoadedStep {
    return screen.seating
        ? { effects: [focusOn("root")], screen: { ...screen, seating: false } }
        : quiet(screen);
}

function stepInput(screen: LoadedScreen, event: Timed<StepInput>): LoadedStep {
    switch (event.kind) {
        case "step_click": {
            return onStepClick(screen, event.direction);
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

function stepMove(screen: LoadedScreen, event: Timed<MoveInput>): LoadedStep {
    switch (event.kind) {
        case "move": {
            return moveTo(screen, event.cursor);
        }
        case "key": {
            return onKey(screen, event);
        }
        case "result_page": {
            return moveTo(screen, { ...screen.view.cursor, page: event.page });
        }
        case "select_round": {
            return selectRound(screen, event.cursor);
        }
        default: {
            return assertNever(event);
        }
    }
}

function stepRoundList(screen: LoadedScreen, event: Timed<RoundListInput>): LoadedStep {
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

function stepOption(screen: LoadedScreen, event: Timed<OptionInput>): LoadedStep {
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
            return assertNever(event);
        }
    }
}

function stepLoaded(screen: LoadedScreen, event: Timed<LoadedInput>): LoadedStep {
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
 * The replay page's transition: the screen after `event` and the IO it asks of the view (writing the address, saving
 * the reader's settings, moving the focus). It reads no clock and arms no timer; the deadlines it keeps
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
