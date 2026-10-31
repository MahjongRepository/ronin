import { describe, expect, it } from "vitest";

import { GAME_ID, HANDOFF, clientEvent } from "#tests/fixtures/scenario";
import { WIRE_GAME_JOINED, WIRE_GAME_STARTED } from "#tests/fixtures/wire";
import { serverSilenceLimitMs, startGameClient, stepGameClient } from "@/entities/client";

const { message, opened } = clientEvent;

describe("serverSilenceLimitMs", () => {
    it("waits out a round advance over three winners' pages, the most rons one discard can make", () => {
        const timer = { bk: 20, gp: 3, mb: 60, md: 5, ra: 40, rb: 10, tb: 5 };
        const started = [
            opened(0),
            message(0, WIRE_GAME_JOINED),
            message(10, { ...WIRE_GAME_STARTED, s: 0, tm: timer }),
        ].reduce(
            (state, event) => stepGameClient(state, event).state,
            startGameClient(GAME_ID, HANDOFF, 0).state,
        );

        expect(serverSilenceLimitMs(started)).toBe(3 * 40_000 + 25_000);
    });
});
