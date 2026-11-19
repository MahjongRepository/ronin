import { afterEach, describe, expect, it } from "vitest";

import { type LobbyRooms, createLobbyState } from "@/lobby/state";
import { renderLobby } from "@/lobby/ui";

const LISTED_ROOMS: LobbyRooms["rooms"] = [
    {
        name: "Jade Crane",
        numAiPlayers: 3,
        playerCount: 1,
        players: [
            { isBot: true, name: "ai-1" },
            { isBot: false, name: "dev" },
            { isBot: true, name: "ai-3" },
            { isBot: true, name: "ai-4" },
        ],
        roomId: "r1",
    },
];

function renderSeatedAt(myRoomId: string): HTMLElement {
    const state = createLobbyState(null);
    state.rooms = { myRoomId, rooms: LISTED_ROOMS };
    const host = document.createElement("main");
    document.body.append(host);
    renderLobby(host, state, { createRoom: () => {} });
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
    it("shows the seated hint, a link back to the user's table and its seats in seat order", () => {
        const host = renderSeatedAt("r1");
        const startingHost = renderSeatedAt("r2");

        expect(seatedHint(host)).toEqual(["Jade Crane", "/rooms/r1"]);
        expect(
            host.querySelector(".lobby-actions")?.classList.contains("lobby-actions--seated"),
        ).toBe(true);
        expect(host.querySelector(".lobby-room-row .lobby-join-btn")?.textContent).toBe(
            "Back to your table",
        );
        expect(
            [...host.querySelectorAll(".lobby-room-row .seat-name")].map(
                (seat) => seat.textContent,
            ),
        ).toEqual(["Free seat", "dev", "Free seat", "Free seat"]);
        expect(seatedHint(startingHost)).toEqual(["Table", "/rooms/r2"]);
    });

    it("lists each game being played with its wind and one column per seat, East to North", () => {
        const state = createLobbyState(null);
        state.games = [
            {
                gameId: "g1",
                gameType: "hanchan",
                players: ["A", "B", "C", "D"],
                startedAt: new Date(0),
            },
            {
                gameId: "g2",
                gameType: "tonpusen",
                players: ["E", "F", "G", "H"],
                startedAt: new Date(0),
            },
        ];
        const host = document.createElement("main");
        document.body.append(host);
        renderLobby(host, state, { createRoom: () => {} });

        const games = [...host.querySelectorAll(".current-games .current-game")];
        expect(
            games.map((game) => [
                game.querySelector(".current-game-wind")?.textContent,
                game.querySelector(".current-game-wind")?.getAttribute("title"),
                [...game.querySelectorAll(".seat-name")].map((seat) => seat.textContent),
            ]),
        ).toEqual([
            ["南", "Hanchan", ["A", "B", "C", "D"]],
            ["東", "Tonpuu", ["E", "F", "G", "H"]],
        ]);
        expect(host.querySelector(".current-games .lobby-table-count")?.textContent).toBe(
            "2 playing",
        );
    });
});
