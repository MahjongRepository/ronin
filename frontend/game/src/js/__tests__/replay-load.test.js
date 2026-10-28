import { afterEach, describe, expect, it, vi } from "vitest";

import { loadReplay, REPLAY_ERROR } from "../replay/load.js";
import wire from "../ronin/wire.js";
import FULL_GAME from "./fixtures/replays/full_game.txt?raw";
import RIICHI from "./fixtures/replays/riichi.txt?raw";

function stubFetch(response) {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

function loadText(text) {
    stubFetch(new Response(text));
    return loadReplay("g-1");
}

function replaceLine(text, number, line) {
    return text
        .split("\n")
        .map((current, index) => (index + 1 === number ? line : current))
        .join("\n");
}

describe("loadReplay", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        vi.useRealTimers();
    });

    it("loads a recorded game's events from game_started on", async () => {
        const fetchMock = stubFetch(new Response(`\n${FULL_GAME}`));

        const { lines, lineNumbers } = await loadReplay("g 1");

        expect(fetchMock).toHaveBeenCalledWith("/api/replays/g%201");
        expect(lines).toHaveLength(FULL_GAME.trim().split("\n").length - 1);
        expect(lines[0].t).toBe(wire.E.GAME_STARTED);
        expect(lines.at(-1).t).toBe(wire.E.GAME_END);
        expect(lineNumbers.slice(0, 2)).toEqual([3, 4]);
    });

    it("refuses a replay of another version", async () => {
        const result = await loadText(replaceLine(RIICHI, 1, '{"version": "0.2"}'));

        expect(result).toEqual({ error: { kind: REPLAY_ERROR.VERSION } });
    });

    it("names the line a malformed replay breaks at", async () => {
        const broken = replaceLine(RIICHI, 4, '{"t": 1, "d": 1');

        expect(await loadText(`\n${broken}`)).toEqual({
            error: { kind: REPLAY_ERROR.MALFORMED, line: 5 },
        });
        expect(await loadText(replaceLine(RIICHI, 2, '{"t": 9}'))).toEqual({
            error: { kind: REPLAY_ERROR.MALFORMED, line: 2 },
        });
        expect(await loadText(replaceLine(RIICHI, 2, ""))).toEqual({
            error: { kind: REPLAY_ERROR.MALFORMED, line: 3 },
        });
        expect(await loadText("\n")).toEqual({ error: { kind: REPLAY_ERROR.MALFORMED } });
    });

    it("fails a load the server refuses or never answers at once, without retrying it", async () => {
        stubFetch(new Response("", { status: 500 }));
        expect(await loadReplay("g-1")).toEqual({ error: { kind: REPLAY_ERROR.FAILED } });

        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
        expect(await loadReplay("g-1")).toEqual({ error: { kind: REPLAY_ERROR.FAILED } });
    });

    it("retries a missing replay, waiting once, until it is found", async () => {
        vi.useFakeTimers();
        const fetchMock = vi
            .fn()
            .mockResolvedValueOnce(new Response("Not found", { status: 404 }))
            .mockResolvedValueOnce(new Response("Not found", { status: 404 }))
            .mockResolvedValueOnce(new Response(RIICHI));
        vi.stubGlobal("fetch", fetchMock);
        const onWait = vi.fn();
        const found = loadReplay("g-1", { onWait });

        await vi.advanceTimersByTimeAsync(1_499);
        expect(fetchMock).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(1);
        expect((await found).lines[0].t).toBe(wire.E.GAME_STARTED);
        expect(fetchMock).toHaveBeenCalledTimes(3);
        expect(onWait).toHaveBeenCalledTimes(1);
    });

    it("gives up on a replay still missing after its fourth try", async () => {
        vi.useFakeTimers();
        const fetchMock = vi.fn(async () => new Response("Not found", { status: 404 }));
        vi.stubGlobal("fetch", fetchMock);
        const missing = loadReplay("g-1");

        await vi.advanceTimersByTimeAsync(3_499);
        expect(fetchMock).toHaveBeenCalledTimes(3);
        await vi.advanceTimersByTimeAsync(1);
        expect(await missing).toEqual({ error: { kind: REPLAY_ERROR.NOT_FOUND } });
        expect(fetchMock).toHaveBeenCalledTimes(4);
    });
});
