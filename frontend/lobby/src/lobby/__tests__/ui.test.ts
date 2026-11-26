import { afterEach, describe, expect, it, vi } from "vitest";

import { type LobbyRooms, createLobbyState } from "@/lobby/state";
import { renderLobby } from "@/lobby/ui";

const NO_ACTIONS = { createRoom: () => {}, returnToGame: () => {} };

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
    renderLobby(host, state, NO_ACTIONS);
    return host;
}

function renderPlaying(returnToGame: () => void): HTMLElement {
    const state = createLobbyState(null);
    state.playing = true;
    state.rooms = { myRoomId: "r1", rooms: LISTED_ROOMS };
    const host = document.createElement("main");
    document.body.append(host);
    renderLobby(host, state, { createRoom: () => {}, returnToGame });
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
    vi.useRealTimers();
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

    it("lists each game being played with its wind, time played, one column per seat, East to North, and a link to watch it", () => {
        const now = new Date("2026-11-19T18:00:00Z");
        vi.useFakeTimers({ now });
        const state = createLobbyState(null);
        state.games = [
            {
                gameId: "g1",
                gameType: "hanchan",
                players: ["A", "B", "C", "D"],
                startedAt: new Date(now.getTime() - 75 * 60_000 - 59_000),
            },
            {
                gameId: "g2",
                gameType: "tonpusen",
                players: ["E", "F", "G", "H"],
                startedAt: new Date(now.getTime() - 30_000),
            },
        ];
        const host = document.createElement("main");
        document.body.append(host);
        renderLobby(host, state, NO_ACTIONS);

        const games = [...host.querySelectorAll(".current-games .current-game")];
        expect(
            games.map((game) => [
                game.querySelector(".current-game-wind")?.textContent,
                game.querySelector(".current-game-wind")?.getAttribute("title"),
                game.querySelector("time")?.textContent,
                [...game.querySelectorAll(".seat-name")].map((seat) => seat.textContent),
                game.querySelector("a")?.textContent,
                game.querySelector("a")?.getAttribute("href"),
            ]),
        ).toEqual([
            ["南", "Hanchan", "1 h 15 min", ["A", "B", "C", "D"], "Watch", "/play/observe/g1"],
            ["東", "Tonpuu", "Just started", ["E", "F", "G", "H"], "Watch", "/play/observe/g2"],
        ]);
        expect(host.querySelector(".current-games .lobby-table-count")?.textContent).toBe(
            "2 playing",
        );
    });

    it("offers a playing user only the way back into their game, even over the table whose game it is", () => {
        const returnToGame = vi.fn();
        const host = renderPlaying(returnToGame);

        host.querySelector<HTMLButtonElement>(".lobby-return-btn")?.click();

        expect(returnToGame).toHaveBeenCalledOnce();
        expect(host.querySelector(".lobby-action-label")?.textContent).toBe("Return to game");
        expect(host.querySelector('a[href="/matchmaking"]')).toBeNull();
        expect(host.querySelector<HTMLButtonElement>(".lobby-create-btn")?.disabled).toBe(true);
        expect(host.querySelector(".lobby-room-row .lobby-join-btn")).toBeNull();
        expect(host.querySelector(".lobby-seated-hint")).toBeNull();
    });
});
