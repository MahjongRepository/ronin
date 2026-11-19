import { afterEach, describe, expect, it } from "vitest";

import { type LobbyRooms, createLobbyState } from "@/lobby/state";
import { renderLobby } from "@/lobby/ui";

const LISTED_ROOMS: LobbyRooms["rooms"] = [
    {
        name: "Jade Crane",
        numAiPlayers: 3,
        playerCount: 1,
        players: [{ isBot: false, name: "dev" }],
        roomId: "r1",
    },
];

function renderSeatedAt(myRoomId: string): HTMLElement {
    const state = createLobbyState(null);
    state.rooms = { myRoomId, rooms: LISTED_ROOMS };
    const host = document.createElement("main");
    document.body.append(host);
    renderLobby(host, state, { createRoom: () => {}, createTournament: () => {} });
    return host;
}

function seatedHint(host: HTMLElement): (string | null | undefined)[] {
    const hint = host.querySelector(".lobby-seated-hint");
    return [
        hint?.querySelector(".lobby-table-name")?.textContent,
        hint?.querySelector("a")?.getAttribute("href"),
    ];
}

afterEach(() => {
    document.body.replaceChildren();
});

describe("renderLobby", () => {
    it("shows the seated hint with a link back to the user's table, listed or starting", () => {
        const host = renderSeatedAt("r1");
        const startingHost = renderSeatedAt("r2");

        expect(seatedHint(host)).toEqual(["Jade Crane", "/rooms/r1"]);
        expect(
            host.querySelector(".lobby-actions")?.classList.contains("lobby-actions--seated"),
        ).toBe(true);
        expect(host.querySelector(".lobby-room-card .lobby-join-btn")?.textContent).toBe(
            "Back to your table",
        );
        expect(seatedHint(startingHost)).toEqual(["Table", "/rooms/r2"]);
    });
});
