import { nothing, render } from "lit-html";
import { assert, describe, expect, it, onTestFinished } from "vitest";

import { ManualClock, steadyClockOn } from "#tests/fixtures/clock";
import {
    checkpointState,
    loadSeatScenario,
    receivedPayload,
} from "#tests/fixtures/seat-transcripts";
import {
    type ClientEffect,
    type LiveClient,
    NO_PLAY_UI,
    PlayBoard,
    type PlayCommand,
    type PlayUi,
    decisionOf,
    playDisplay,
    startGameClient,
    stepGameClient,
    stepPlayUi,
} from "@/entities/client";
import { RIGHT_CLICK_SETTLE_MS } from "@/entities/client/ui/play-input";
import { HAND_TILE_FOCUS_KEY, PLAYABLE_TILE_FOCUS_KEY } from "@/entities/tile";
import { keyedControls } from "@/shared/lib";
import { type ClientMessage, buildDiscardAction, buildPassAction } from "@/shared/protocol";

const manualClock = new ManualClock();
const inputClock = steadyClockOn(manualClock);

function passTime(ms: number): void {
    manualClock.advanceTo(manualClock.elapsedNow() + ms);
}

class InputBoard {
    readonly host = document.createElement("div");
    readonly commands: PlayCommand[] = [];
    readonly effects: ClientEffect[] = [];
    readonly board: HTMLElement;

    constructor(
        private state: LiveClient,
        private ui: PlayUi,
    ) {
        document.body.append(this.host);
        this.draw();
        this.board = element(this.host, ".game-board");
        onTestFinished(() => {
            render(nothing, this.host);
            this.host.remove();
        });
    }

    private readonly onCommand = (command: PlayCommand): void => {
        this.commands.push(command);
        if (command.kind === "intent") {
            const { effects, state } = stepGameClient(this.state, {
                at: this.state.now,
                intent: command.intent,
                kind: "intent",
            });
            this.state = state;
            this.effects.push(...effects);
        }
        this.ui = stepPlayUi(this.state, this.ui, command);
        this.draw();
    };

    private draw(): void {
        render(
            PlayBoard({
                clock: inputClock,
                display: playDisplay(this.state, this.ui),
                onCommand: this.onCommand,
                onLanguage: () => {},
            }),
            this.host,
        );
    }

    readonly show = (state: LiveClient): void => {
        this.state = state;
        this.ui = stepPlayUi(state, this.ui, { kind: "client_stepped" });
        this.draw();
    };
}

function mountInput(state: LiveClient, ui: PlayUi = NO_PLAY_UI): InputBoard {
    return new InputBoard(state, ui);
}

function element(host: HTMLElement, selector: string): HTMLElement {
    const found = host.querySelector<HTMLElement>(selector);
    if (found === null) {
        throw new Error(`Missing ${selector}`);
    }
    return found;
}

function key(target: HTMLElement, init: KeyboardEventInit, type = "keydown"): KeyboardEvent {
    const event = new KeyboardEvent(type, { bubbles: true, cancelable: true, ...init });
    target.dispatchEvent(event);
    return event;
}

function keys(target: HTMLElement, inputs: readonly KeyboardEventInit[]): void {
    for (const init of inputs) {
        key(target, init);
    }
}

function activate(input: "pointer" | "keyboard", target: HTMLElement, phase: "down" | "up"): void {
    if (input === "pointer") {
        pointer(target, `pointer${phase}`, { button: 0 });
    } else {
        key(target, { key: " " }, `key${phase}`);
    }
}

function sendPreventedEscape(target: HTMLElement): void {
    const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Escape" });
    event.preventDefault();
    target.dispatchEvent(event);
}

function pointer(target: HTMLElement, type: string, init: PointerEventInit = {}): void {
    target.dispatchEvent(
        new PointerEvent(type, {
            bubbles: true,
            button: 2,
            cancelable: true,
            isPrimary: true,
            pointerId: 1,
            pointerType: "mouse",
            ...init,
        }),
    );
}

function rightPress(target: HTMLElement): void {
    pointer(target, "pointerdown");
    pointer(target, "pointerup");
}

function rightClick(target: HTMLElement): void {
    passTime(RIGHT_CLICK_SETTLE_MS);
    rightPress(target);
}

function rightPressBeforeSettled(target: HTMLElement): void {
    passTime(RIGHT_CLICK_SETTLE_MS - 1);
    rightPress(target);
}

function fingerTap(target: HTMLElement): void {
    const finger = { button: 0, pointerType: "touch" };
    pointer(target, "pointerdown", finger);
    pointer(target, "pointerup", finger);
    target.click();
}

function discardableTiles(state: LiveClient): readonly [number, number] {
    const [first, second] = playDisplay(state, NO_PLAY_UI).tileIntents.keys();
    assert(first !== undefined && second !== undefined);
    return [first, second];
}

function tileButton(host: HTMLElement, tileId: number): HTMLElement {
    return element(host, `[data-tile-id="${tileId}"]`);
}

function armedAfterTap(host: HTMLElement, target: HTMLElement): number[] {
    fingerTap(target);
    return [...host.querySelectorAll<HTMLElement>(".hand-tile--armed")].map((button) =>
        Number(button.dataset.tileId),
    );
}

function messages(effects: readonly ClientEffect[]): ClientMessage[] {
    return effects.flatMap((effect) => (effect.type === "send" ? [effect.message] : []));
}

function waitId(state: LiveClient): number {
    const decision = decisionOf(state);
    assert(decision !== null);
    return decision.waitId;
}

/**
 * A fresh page's client on the named transcript's game after its snapshot and the wait the server re-sent behind it:
 * the resume screen showing over that open decision.
 */
function resumedOver(name: string, resent: string): LiveClient {
    const { transcript } = loadSeatScenario(name);
    const handoff = { gameTicket: "ticket", wsUrl: `ws://game/ws/${transcript.gameId}` };
    const steps = [
        { at: 0, kind: "transport_opened" },
        { at: 100, kind: "server_message", raw: receivedPayload(transcript, "reconnected") },
        { at: 100, kind: "server_message", raw: receivedPayload(transcript, resent) },
    ] as const;
    return steps.reduce(
        (state, event) => stepGameClient(state, event).state,
        startGameClient(transcript.gameId, handoff, 0).state,
    );
}

describe("live board input", () => {
    it("passes the call under a fresh page's resume screen on Escape, leaving the screen up", () => {
        const state = resumedOver("reconnect_seat_1", "prompt re-sent");
        assert(state.opening.kind === "showing" && state.opening.cause === "resume");
        const { board, effects, host } = mountInput(state);
        key(board, { key: "Escape" });

        expect(messages(effects)).toEqual([buildPassAction(waitId(state))]);
        expect(host.querySelector(".seating")).not.toBeNull();
    });

    it("discards the re-sent draw under a fresh page's resume screen on right-click", () => {
        const state = resumedOver("bank_reconnect_seat_1", "draw re-sent");
        const drawn = playDisplay(state, NO_PLAY_UI).board?.players[0].drawnTile?.tileId;
        assert(state.opening.kind === "showing" && drawn !== undefined);
        const { board, effects } = mountInput(state);
        rightClick(board);

        expect(messages(effects)).toEqual([buildDiscardAction(drawn, waitId(state))]);
    });

    it("presses the opening screen's OK on Enter from the board, once for a held key, sending nothing", () => {
        const state = checkpointState("own_turn_seat_1", "game started");
        const { board, commands, effects, host } = mountInput(state);
        keys(board, [{ key: "Enter" }, { key: "Enter", repeat: true }]);

        expect(commands).toEqual([{ intent: { type: "confirm_opening" }, kind: "intent" }]);
        expect([effects, host.querySelector(".seating")]).toEqual([[], null]);
    });

    it("backs out of chi before passing, ignores held Escape, and sends one pass", () => {
        const state = checkpointState("call_prompt_seat_1", "prompt");
        const { board, commands, effects, host } = mountInput(state);
        element(host, '[data-focus-key~="tile-choice-chi"]').click();
        keys(board, [{ key: "Escape" }, { key: "Escape", repeat: true }]);
        expect(commands).toEqual([
            { kind: "toggle_tile_choice", offer: "chi" },
            { kind: "step_back" },
        ]);
        expect(messages(effects)).toEqual([]);

        keys(board, [{ key: "Escape" }, { key: "Escape" }]);
        expect(messages(effects)).toEqual([buildPassAction(waitId(state))]);
    });

    it("cancels riichi selection on right-click before allowing a drawn-tile discard", () => {
        const state = checkpointState("own_turn_seat_1", "rinshan");
        const { board, commands, effects, host } = mountInput(state);
        element(host, '[data-focus-key~="riichi-pick"]').click();
        rightClick(board);
        expect(commands).toEqual([{ kind: "toggle_riichi_pick" }, { kind: "step_back" }]);
        expect(messages(effects)).toEqual([]);

        rightClick(board);
        expect(messages(effects)).toEqual([buildDiscardAction(120, waitId(state))]);
    });

    it("discards the draw despite a tsumo offer, while Escape leaves that turn alone", () => {
        const state = checkpointState("own_turn_seat_1", "tsumo draw");
        const drawn = playDisplay(state, NO_PLAY_UI).board?.players[0].drawnTile?.tileId;
        assert(drawn !== undefined);
        const { board, effects } = mountInput(state);
        key(board, { key: "Escape" });
        expect(messages(effects)).toEqual([]);

        rightClick(board);
        rightClick(board);
        expect(messages(effects)).toEqual([buildDiscardAction(drawn, waitId(state))]);
    });

    it("lifts a tile on a finger's first tap, moves the lift, drops it elsewhere, and discards on the second tap", () => {
        const state = checkpointState("own_turn_seat_1", "rinshan");
        const [first, second] = discardableTiles(state);
        const { board, effects, host } = mountInput(state);
        expect([
            armedAfterTap(host, tileButton(host, first)),
            armedAfterTap(host, tileButton(host, second)),
            armedAfterTap(host, board),
        ]).toEqual([[first], [second], []]);
        expect(messages(effects)).toEqual([]);

        fingerTap(tileButton(host, first));
        fingerTap(tileButton(host, first));
        expect(messages(effects)).toEqual([buildDiscardAction(first, waitId(state))]);
    });

    it("discards on one mouse press", () => {
        const state = checkpointState("own_turn_seat_1", "rinshan");
        const [tileId] = discardableTiles(state);
        const { effects, host } = mountInput(state);
        const tile = tileButton(host, tileId);
        pointer(tile, "pointerdown", { button: 0 });
        pointer(tile, "pointerup", { button: 0 });
        tile.click();
        expect(messages(effects)).toEqual([buildDiscardAction(tileId, waitId(state))]);
    });

    it("picks riichi's discard on one finger tap", () => {
        const state = checkpointState("own_turn_seat_1", "rinshan");
        const { commands, host } = mountInput(state);
        element(host, '[data-focus-key~="riichi-pick"]').click();
        fingerTap(element(host, ".hand-tile--declaring"));
        expect(host.querySelector(".hand-tile--armed")).toBeNull();
        expect(commands.at(-1)?.kind).toBe("intent");
    });

    it("closes settings, then unpins scores, before right-click can pass a call", () => {
        const state = checkpointState("call_prompt_seat_1", "prompt");
        const { board, commands, effects } = mountInput(state, {
            ...NO_PLAY_UI,
            pinnedNameplate: "left",
            settingsOpen: true,
        });
        rightClick(board);
        rightClick(board);
        expect(commands).toEqual([
            { kind: "close_settings" },
            { kind: "pin_nameplate", seat: null },
        ]);
        expect(messages(effects)).toEqual([]);

        rightClick(board);
        expect(messages(effects)).toEqual([buildPassAction(waitId(state))]);
    });
});

describe("live board gesture guards", () => {
    it("accepts an accessibility click after the pointer leaves without a press", () => {
        const state = checkpointState("call_prompt_seat_1", "prompt");
        const { board, effects, host } = mountInput(state);
        pointer(board, "pointerleave");
        element(host, ".decision-controls__action--pass").click();
        expect(messages(effects)).toEqual([buildPassAction(waitId(state))]);
    });

    it("drops a right press when a new decision arrives before release", () => {
        const { board, effects, show } = mountInput(
            checkpointState("call_prompt_seat_1", "prompt"),
        );
        pointer(board, "pointerdown");
        show(checkpointState("own_turn_seat_1", "rinshan"));
        pointer(board, "pointerup");
        expect(messages(effects)).toEqual([]);
    });

    it("cancels a right press released on another element or after leaving the board", () => {
        const { board, effects, host } = mountInput(
            checkpointState("call_prompt_seat_1", "prompt"),
        );
        pointer(board, "pointerdown");
        pointer(element(host, ".hand-tile"), "pointerup");
        pointer(board, "pointerdown");
        pointer(board, "pointerleave");
        pointer(board, "pointerup");
        expect(messages(effects)).toEqual([]);
    });

    it.each(["pointer", "keyboard"] as const)(
        "does not let a %s press activate a tile in the next decision",
        (input) => {
            const { effects, host, show } = mountInput(
                checkpointState("own_turn_seat_1", "rinshan"),
            );
            const tile = element(host, ".hand-tile--selectable");
            element(host, ".game-menu__toggle").focus();
            activate(input, tile, "down");
            tile.focus();
            show(checkpointState("call_prompt_seat_1", "turn"));
            const nextTile = element(host, ".hand-tile--selectable");
            activate(input, nextTile, "up");
            nextTile.click();
            expect(messages(effects)).toEqual([]);
        },
    );

    it("moves focus past kuikae-blocked tiles, clamps at the hand’s edge, without playing a tile", () => {
        const state = checkpointState("call_prompt_seat_1", "turn");
        const { board, effects } = mountInput(state);
        const all = keyedControls(board, HAND_TILE_FOCUS_KEY);
        const playable = keyedControls(board, PLAYABLE_TILE_FOCUS_KEY);
        expect(all.length).toBeGreaterThan(playable.length);
        key(all[0], { key: "ArrowRight" });
        expect(document.activeElement).toBe(playable[0]);
        key(playable[0], { key: "ArrowLeft" });
        expect([document.activeElement, messages(effects)]).toEqual([playable[0], []]);
    });

    it("leaves modified shortcuts, field typing, and prevented events alone", () => {
        const { board, effects } = mountInput(checkpointState("call_prompt_seat_1", "prompt"));
        const field = document.createElement("input");
        board.append(field);
        key(field, { key: "Escape" });
        keys(board, [
            { ctrlKey: true, key: "Escape" },
            { isComposing: true, key: "Escape" },
        ]);
        pointer(board, "pointerdown", { shiftKey: true });
        pointer(board, "pointerup", { shiftKey: true });
        sendPreventedEscape(board);
        expect(messages(effects)).toEqual([]);
    });

    it("restores the browser context menu and disables right-click actions when switched off", () => {
        const { board, effects } = mountInput(checkpointState("call_prompt_seat_1", "prompt"), {
            ...NO_PLAY_UI,
            rightClick: false,
        });
        rightClick(board);
        const menu = new MouseEvent("contextmenu", { bubbles: true, button: 2, cancelable: true });
        board.dispatchEvent(menu);
        expect(menu.defaultPrevented).toBe(false);
        expect(messages(effects)).toEqual([]);
    });

    it("blocks a canceled primary press even after it returns to a new decision", () => {
        const { board, effects, host, show } = mountInput(
            checkpointState("own_turn_seat_1", "rinshan"),
        );
        pointer(element(host, ".hand-tile--selectable"), "pointerdown", { button: 0 });
        pointer(board, "pointerleave", { button: 0 });
        show(checkpointState("call_prompt_seat_1", "turn"));
        const tile = element(host, ".hand-tile--selectable");
        pointer(tile, "pointerup", { button: 0 });
        tile.click();
        expect(messages(effects)).toEqual([]);
    });

    it("allows a fresh native summary activation after Enter opened settings", () => {
        const { host } = mountInput(checkpointState("call_prompt_seat_1", "prompt"));
        const toggle = element(host, ".game-menu__toggle");
        key(toggle, { key: "Enter" });
        toggle.click();
        key(toggle, { key: "Enter" }, "keyup");
        const summary = element(host, ".game-menu__controls summary");
        key(summary, { key: "Enter" });
        const click = new MouseEvent("click", { bubbles: true, cancelable: true });
        summary.dispatchEvent(click);
        expect(click.defaultPrevented).toBe(false);
    });

    it.each([
        ["call_prompt_seat_1", "turn"],
        ["double_ron_seat_1", "round end"],
    ])("keeps %s's %s on explicit buttons", (scenario, checkpoint) => {
        const { board, effects } = mountInput(checkpointState(scenario, checkpoint));
        board.click();
        key(board, { key: "Escape" });
        rightClick(board);
        expect(messages(effects)).toEqual([]);
    });
});

describe("live board right-click settling", () => {
    it("keeps a double right-click from passing a call and discarding the draw that follows", () => {
        const call = checkpointState("call_prompt_seat_1", "prompt");
        const turn = checkpointState("own_turn_seat_1", "rinshan");
        const { board, effects, show } = mountInput(call);
        rightPress(board);
        show(turn);
        rightPressBeforeSettled(board);
        rightPressBeforeSettled(board);
        expect(messages(effects)).toEqual([buildPassAction(waitId(call))]);

        rightClick(board);
        expect(messages(effects)).toEqual([
            buildPassAction(waitId(call)),
            buildDiscardAction(120, waitId(turn)),
        ]);
    });
});
