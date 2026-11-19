import { afterEach, describe, expect, it } from "vitest";

import { createLobbyState } from "@/lobby/state";
import { renderLobby } from "@/lobby/ui";

afterEach(() => {
    document.body.replaceChildren();
});

describe("renderLobby", () => {
    it("shows the seated hint with a link back to the user's table", () => {
        const state = createLobbyState(null);
        state.rooms = {
            myRoomId: "r1",
            rooms: [
                {
                    name: "Jade Crane",
                    numAiPlayers: 3,
                    playerCount: 1,
                    players: [{ isBot: false, name: "dev" }],
                    roomId: "r1",
                },
            ],
        };
        const host = document.createElement("main");
        document.body.append(host);

        renderLobby(host, state, { createRoom: () => {} });

        const hint = host.querySelector(".lobby-seated-hint");
        expect(hint?.querySelector(".lobby-table-name")?.textContent).toBe("Jade Crane");
        expect(hint?.querySelector("a")?.getAttribute("href")).toBe("/rooms/r1");
        expect(
            host.querySelector(".lobby-actions")?.classList.contains("lobby-actions--seated"),
        ).toBe(true);
        expect(host.querySelector(".lobby-room-card .lobby-join-btn")?.textContent).toBe(
            "Back to your table",
        );
    });
});
