import { afterEach, describe, expect, it, vi } from "vitest";

import { type CurrentGame } from "@/current-games";
import { watchCurrentGames } from "@/lobby/games-feed";

class FakeWebSocket extends EventTarget {
    static instances: FakeWebSocket[] = [];
    close = vi.fn();
    readonly url: string;

    constructor(url: string) {
        super();
        this.url = url;
        FakeWebSocket.instances.push(this);
    }

    receive(message: Record<string, unknown>): void {
        this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(message) }));
    }
}

function gamesMessage(...gameIds: string[]): Record<string, unknown> {
    return {
        games: gameIds.map((gameId) => ({
            game_id: gameId,
            players: ["A", "B", "C", "D"],
            started_at: 1_700_000_000,
        })),
        type: "games",
    };
}

function startWatching(): { shown: string[][]; stop: () => void } {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const shown: string[][] = [];
    const stop = watchCurrentGames("ws://test/ws/games", (games: CurrentGame[]) =>
        shown.push(games.map((game) => game.gameId)),
    );
    return { shown, stop };
}

function openWithLists(ws: FakeWebSocket, ...lists: string[][]): void {
    ws.dispatchEvent(new Event("open"));
    for (const gameIds of lists) {
        ws.receive(gamesMessage(...gameIds));
    }
}

function loseConnection(ws: FakeWebSocket): FakeWebSocket {
    ws.dispatchEvent(new Event("close"));
    vi.advanceTimersByTime(60_000);
    return FakeWebSocket.instances.at(-1) ?? ws;
}

describe("watchCurrentGames", () => {
    afterEach(() => {
        FakeWebSocket.instances = [];
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    it("shows every list the socket pushes, reconnects after a lost connection and stops once unwatched", () => {
        const { shown, stop } = startWatching();
        const [first] = FakeWebSocket.instances;
        openWithLists(first, ["g1"], ["g1", "g2"]);

        const second = loseConnection(first);
        second.receive(gamesMessage("g2"));
        stop();
        loseConnection(second);

        expect(shown).toEqual([["g1"], ["g1", "g2"], ["g2"]]);
        expect([second.url, second.close.mock.calls]).toEqual(["ws://test/ws/games", [[1000]]]);
        expect(FakeWebSocket.instances).toHaveLength(2);
    });
});
