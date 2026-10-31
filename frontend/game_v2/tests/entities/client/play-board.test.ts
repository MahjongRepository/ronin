import { render } from "lit-html";
import { describe, expect, it } from "vitest";

import { checkpointState } from "#tests/fixtures/seat-transcripts";
import {
    type LiveClient,
    NO_PLAY_UI,
    PlayBoard,
    type PlayCommand,
    type PlayUi,
    nextPlayUi,
    playDisplay,
    stepGameClient,
} from "@/entities/client";
import { CALLOUT_MS } from "@/entities/table";

function drawPlay(host: HTMLElement, state: LiveClient, ui: PlayUi = NO_PLAY_UI): void {
    render(
        PlayBoard({
            display: playDisplay(state, ui),
            onCommand: () => {},
            table: state.table,
        }),
        host,
    );
}

/** Focus the hand's first tile on a board in the document at `before`, redraw it at `after`: what holds the focus then. */
function focusThrough(
    before: LiveClient,
    after: LiveClient,
): {
    readonly tile: HTMLButtonElement | null;
    readonly focused: Element | null;
    readonly controls: HTMLButtonElement[];
} {
    const host = document.createElement("div");
    document.body.append(host);
    drawPlay(host, before);
    const tile = host.querySelector<HTMLButtonElement>(".board-local .hand-tile");
    tile?.focus();
    drawPlay(host, after);
    const focused = document.activeElement;
    const controls = [
        ...host.querySelectorAll<HTMLButtonElement>(".board-actions .decision-controls__action"),
    ];
    host.remove();
    return { controls, focused, tile };
}

function reachableByTab(control: HTMLButtonElement): boolean {
    return !control.disabled && control.tabIndex >= 0 && control.closest("[inert]") === null;
}

function renderPlay(state: LiveClient, ui: PlayUi = NO_PLAY_UI): HTMLElement {
    const host = document.createElement("div");
    drawPlay(host, state, ui);
    return host;
}

/** Press the button `selector` names, and the class of the element focused once the render settles. */
async function pressFocused(host: HTMLElement, selector: string): Promise<string | undefined> {
    host.querySelector<HTMLButtonElement>(selector)?.click();
    await Promise.resolve();
    return document.activeElement?.className;
}

/** A live board in the document whose commands change its view's `ui` and redraw it, as the game view does. */
function mountLive(
    state: LiveClient,
    initial: PlayUi,
): {
    readonly host: HTMLElement;
    readonly commands: PlayCommand[];
    readonly show: (next: PlayUi) => void;
} {
    const host = document.createElement("div");
    document.body.append(host);
    const commands: PlayCommand[] = [];
    let ui = initial;
    function show(next: PlayUi): void {
        ui = next;
        draw();
    }
    function draw(): void {
        render(
            PlayBoard({
                display: playDisplay(state, ui),
                onCommand: (command) => {
                    commands.push(command);
                    ui = nextPlayUi(state, ui, command);
                    draw();
                },
                table: state.table,
            }),
            host,
        );
    }
    draw();
    return { commands, host, show };
}

/** Close the open sheet by Close once every "Show all" is hidden, as a notice that grew to show whole leaves it. */
async function closeSheetWithNoShowAll(host: HTMLElement): Promise<void> {
    await settled();
    for (const showAll of host.querySelectorAll<HTMLElement>(".board-notice__more")) {
        showAll.style.display = "none";
    }
    host.querySelector<HTMLButtonElement>(".notice-sheet__close")?.click();
    await settled();
}

/** Let every render's queued focus settle, as the page would before the player's next key. */
function settled(): Promise<void> {
    return new Promise((resolve) => {
        setTimeout(resolve, 0);
    });
}

/** The timer's caption and digits, and whether its bank is marked as draining. */
function timer(host: HTMLElement): [string | undefined, string | undefined, boolean] {
    return [
        host.querySelector(".decision-timer__caption")?.textContent?.trim(),
        host.querySelector(".decision-timer__digits")?.textContent?.replaceAll(/\s+/gu, ""),
        host.querySelector(".decision-controls__bank--draining") !== null,
    ];
}

/** The play switches a live board draws for a state, each press going to `onCommand`. */
function renderSwitches(
    state: LiveClient,
    onCommand: (command: PlayCommand) => void,
): HTMLButtonElement[] {
    const host = document.createElement("div");
    render(
        PlayBoard({
            display: playDisplay(state, NO_PLAY_UI),
            onCommand,
            table: state.table,
        }),
        host,
    );
    return [...host.querySelectorAll<HTMLButtonElement>(".play-switch")];
}

const LINKS = { history: "/history", replay: "/play/history/g1?v=2&seat=1" };

function renderLiveGameEnd(
    gameEnd: LiveClient = checkpointState("final_round_seat_1", "game end"),
): { host: HTMLElement; commands: PlayCommand[] } {
    const ended = stepGameClient(gameEnd, {
        at: gameEnd.now,
        intent: { type: "confirm_result" },
        kind: "intent",
    }).state;
    const commands: PlayCommand[] = [];
    const host = document.createElement("div");
    render(
        PlayBoard({
            display: playDisplay(ended, NO_PLAY_UI),
            links: LINKS,
            onCommand: (command) => commands.push(command),
            table: ended.table,
        }),
        host,
    );
    return { commands, host };
}

describe("PlayBoard", () => {
    it("ranks the seats at the game's end, the viewer marked, and leads to the last result, the replay, the history and the lobby", () => {
        const { commands, host } = renderLiveGameEnd();
        const actions = [...host.querySelectorAll<HTMLElement>(".seating__action")];
        const rows = [...host.querySelectorAll(".seating__seat:not(.seating__seat--head)")];

        expect(rows.map((row) => row.querySelector(".seating__placement")?.textContent)).toEqual([
            "1st",
            "2nd",
            "3rd",
            "4th",
        ]);
        expect(host.querySelector(".seating__seat--viewer .seating__name")?.textContent).toBe(
            "Alice",
        );
        expect(
            actions.map((action) => [action.textContent?.trim(), action.getAttribute("href")]),
        ).toEqual([
            ["Last hand", null],
            ["Replay", LINKS.replay],
            ["Game history", LINKS.history],
            ["Lobby", null],
        ]);

        actions[0].click();
        actions[3].click();
        expect(commands).toEqual([
            { intent: { type: "show_last_result" }, kind: "intent" },
            { intent: { type: "leave" }, kind: "intent" },
        ]);
    });

    it("holds a won round's result back for its call, but asks about leaving over it at once, with no furiten", () => {
        const roundEnd = checkpointState("own_turn_seat_1", "round end");
        function renderAt(confirmingLeave: boolean): HTMLElement {
            const host = document.createElement("div");
            render(
                PlayBoard({
                    display: playDisplay(roundEnd, { ...NO_PLAY_UI, confirmingLeave }),
                    onCommand: () => {},
                    table: roundEnd.table,
                }),
                host,
            );
            return host;
        }
        const result = renderAt(false);
        const leaving = renderAt(true);

        expect(roundEnd.furiten).toBe(true);
        expect(result.querySelector(".board-overlay--after-call .round-end-result")).not.toBeNull();
        expect(result.querySelector(".decision-controls")).toBeNull();
        expect(leaving.querySelector(".board-overlay .leave-confirm__stay")).not.toBeNull();
        expect(leaving.querySelector(".board-overlay--after-call")).toBeNull();
    });

    it("opens the notices whole over the round confirm with its seconds, the board inert, the leave question in its place", () => {
        const roundEnd = checkpointState("own_turn_seat_1", "round end");
        const opened = { ...NO_PLAY_UI, noticeSheet: "tile_sprite", tileSprite: "failed" } as const;
        const sheet = renderPlay(roundEnd, opened);
        const leaving = renderPlay(roundEnd, { ...opened, confirmingLeave: true });

        expect([
            sheet.querySelector(".board-overlay .notice-sheet__text")?.textContent,
            sheet.querySelector(".notice-sheet__note")?.textContent?.replaceAll(/\s+/gu, " "),
            sheet.querySelector(".round-end-result"),
            sheet.querySelector(".board-layout")?.hasAttribute("inert"),
        ]).toEqual([
            "Tile images did not load; tiles show their names",
            "Play goes on beneath this sheet. The round's result awaits your OK: 10 s left.",
            null,
            true,
        ]);
        expect(leaving.querySelector(".board-overlay .leave-confirm__stay")).not.toBeNull();
        expect(leaving.querySelector(".notice-sheet")).toBeNull();
    });

    it("closes the notices' sheet alone on Escape, giving the focus back to the Show all that opened it", async () => {
        const turn = checkpointState("call_prompt_seat_1", "turn");
        const { commands, host } = mountLive(turn, { ...NO_PLAY_UI, tileSprite: "failed" });
        const focusedOnOpen = await pressFocused(host, ".board-notice__more");
        const escape = new KeyboardEvent("keydown", {
            bubbles: true,
            cancelable: true,
            key: "Escape",
        });
        host.querySelector(".notice-sheet__close")?.dispatchEvent(escape);
        await settled();

        expect(commands).toEqual([
            { kind: "show_notice", notice: "tile_sprite" },
            { kind: "close_notice" },
        ]);
        expect([
            focusedOnOpen,
            escape.defaultPrevented,
            host.querySelector(".notice-sheet"),
        ]).toEqual(["notice-sheet__close", true, null]);
        expect(document.activeElement).toBe(host.querySelector(".board-notice__more"));
        host.remove();
    });

    it("gives the focus to the result's first enabled control, past a disabled pager, when the sheet closes over it with no Show all shown", async () => {
        const won = checkpointState("double_ron_seat_1", "round end");
        const firstPage = stepGameClient(won, { at: won.now + CALLOUT_MS, kind: "tick" }).state;
        const { host } = mountLive(firstPage, {
            ...NO_PLAY_UI,
            noticeSheet: "tile_sprite",
            tileSprite: "failed",
        });
        await closeSheetWithNoShowAll(host);
        const buttons = [
            ...host.querySelectorAll<HTMLButtonElement>(".board-overlay__panel button"),
        ];

        expect(
            buttons.map((button) => [button.getAttribute("aria-label"), button.disabled]),
        ).toEqual([
            ["Previous winner", true],
            ["Next winner", false],
            ["Next", false],
        ]);
        expect(document.activeElement).toBe(buttons[1]);
        host.remove();
    });

    it("gives the focus back to the board, never the page's body, when the sheet closes as its last notice goes", async () => {
        const turn = checkpointState("call_prompt_seat_1", "turn");
        const failed: PlayUi = { ...NO_PLAY_UI, tileSprite: "failed" };
        const { host, show } = mountLive(turn, failed);
        const focusedOnOpen = await pressFocused(host, ".board-notice__more");
        show({ ...failed, noticeSheet: "tile_sprite", tileSprite: "ready" });
        await settled();

        expect(focusedOnOpen).toBe("notice-sheet__close");
        expect(host.querySelector(".notice-sheet")).toBeNull();
        expect(document.activeElement).toBe(host.querySelector(".board-local button"));
        host.remove();
    });

    it("keeps the focus on the hand's tile as a call offer opens, its controls reachable by Tab without moving it", () => {
        const { controls, focused, tile } = focusThrough(
            checkpointState("call_prompt_seat_1", "seat 2 drew"),
            checkpointState("call_prompt_seat_1", "pon prompt"),
        );

        expect(tile).not.toBeNull();
        expect(focused).toBe(tile);
        expect(controls.map(reachableByTab)).toEqual(controls.map(() => true));
        expect(controls.length).toBeGreaterThan(0);
    });

    it("times a turn as its base and bank apart, marks the bank once it alone drains, and says Sent once answered", () => {
        const turn = checkpointState("own_turn_seat_1", "rinshan");
        const inBank = stepGameClient(turn, { at: turn.now + 6000, kind: "tick" }).state;
        const discard = {
            tileId: turn.table.players[1].drawnTileId ?? -1,
            type: "discard",
        } as const;
        const sent = stepGameClient(inBank, {
            at: inBank.now,
            intent: discard,
            kind: "intent",
        }).state;

        expect(timer(renderPlay(turn))).toEqual(["", "5+30", false]);
        expect(timer(renderPlay(inBank))).toEqual(["Bank", "0+29", true]);
        expect(timer(renderPlay(sent))).toEqual(["Sent", "", false]);
    });

    it("draws each play switch as a switch announcing its state, a press turning it and sending nothing", () => {
        const turn = checkpointState("anchor_seat_1", "own turn");
        const commands: PlayCommand[] = [];
        const [autoWin] = renderSwitches(turn, (command) => commands.push(command));
        autoWin.click();
        const toggle = { playSwitch: "auto_win", type: "toggle_switch" } as const;
        const step = stepGameClient(turn, { at: turn.now, intent: toggle, kind: "intent" });
        const switches = renderSwitches(step.state, () => {});

        expect(commands).toEqual([{ intent: toggle, kind: "intent" }]);
        expect(step.effects).toEqual([]);
        expect(
            switches.map((button) => [
                button.textContent?.trim(),
                button.getAttribute("role"),
                button.getAttribute("aria-checked"),
            ]),
        ).toEqual([
            ["Auto win", "switch", "true"],
            ["No calls", "switch", "false"],
            ["Auto discard", "switch", "false"],
        ]);
    });
});
