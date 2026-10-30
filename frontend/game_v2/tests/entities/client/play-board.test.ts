import { render } from "lit-html";
import { describe, expect, it } from "vitest";

import { checkpointState } from "#tests/fixtures/seat-transcripts";
import {
    NO_PLAY_UI,
    PlayBoard,
    type PlayCommand,
    playDisplay,
    stepGameClient,
} from "@/entities/client";
import { renderStandings } from "@/entities/table/ui/standings";

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
});
