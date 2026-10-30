import { render } from "lit-html";
import { describe, expect, it } from "vitest";

import { checkpointState } from "#tests/fixtures/seat-transcripts";
import {
    type GameClientState,
    NO_PLAY_UI,
    PlayBoard,
    type PlayCommand,
    playDisplay,
    stepGameClient,
} from "@/entities/client";
import { renderStandings } from "@/entities/table/ui/standings";

function renderPlay(state: GameClientState): HTMLElement {
    const host = document.createElement("div");
    render(
        PlayBoard({
            display: playDisplay(state, NO_PLAY_UI),
            onCommand: () => {},
            standings: null,
            table: state.table,
        }),
        host,
    );
    return host;
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
    state: GameClientState,
    onCommand: (command: PlayCommand) => void,
): HTMLButtonElement[] {
    const host = document.createElement("div");
    render(
        PlayBoard({
            display: playDisplay(state, NO_PLAY_UI),
            onCommand,
            standings: null,
            table: state.table,
        }),
        host,
    );
    return [...host.querySelectorAll<HTMLButtonElement>(".play-switch")];
}

const LINKS = { history: "/history", replay: "/play/history/g1?v=2&seat=1" };

function renderLiveStandings(): { host: HTMLElement; commands: PlayCommand[] } {
    const gameEnd = checkpointState("final_round_seat_1", "game end");
    const standings = stepGameClient(gameEnd, {
        at: gameEnd.now,
        intent: { type: "confirm_result" },
        kind: "intent",
    }).state;
    const commands: PlayCommand[] = [];
    const host = document.createElement("div");
    render(
        PlayBoard({
            display: playDisplay(standings, NO_PLAY_UI),
            links: LINKS,
            onCommand: (command) => commands.push(command),
            standings: renderStandings,
            table: standings.table,
        }),
        host,
    );
    return { commands, host };
}

describe("PlayBoard", () => {
    it("leads from the live standings to the last result, the replay, the history and the lobby", () => {
        const { commands, host } = renderLiveStandings();
        const actions = [...host.querySelectorAll<HTMLElement>(".standings__action")];

        expect(
            actions.map((action) => [action.textContent?.trim(), action.getAttribute("href")]),
        ).toEqual([
            ["Last hand", null],
            ["Replay", LINKS.replay],
            ["Game history", LINKS.history],
            ["Lobby", null],
        ]);
        expect(host.querySelector(".standings__col--viewer .standings__name")?.textContent).toBe(
            "Alice",
        );

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
                    standings: null,
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
