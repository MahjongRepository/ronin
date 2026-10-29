import { describe, expect, it } from "vitest";

import { HANDOFF } from "#tests/fixtures/scenario";
import { type SessionState, describePlayerSessionStatus } from "@/entities/session";

const ACTIVE = {
    attempts: { session: 0, transport: 0 },
    connectDeadline: null,
    gameId: "g1",
    handoff: HANDOFF,
    link: "open",
    lostSeat: false,
    retry: null,
    status: "joining",
} as const;

describe("describePlayerSessionStatus", () => {
    it("names each session state in the player's terms, not the machine's", () => {
        const states: readonly SessionState[] = [
            { failedLookups: 0, gameId: "g1", retryAt: null, status: "recovering" },
            ACTIVE,
            { ...ACTIVE, link: "connecting" },
            { ...ACTIVE, status: "playing" },
            { ...ACTIVE, link: "open", status: "reconnecting" },
            { ...ACTIVE, link: "down", lostSeat: true, status: "reconnecting" },
            { gameId: "g1", reason: { kind: "game_ended" }, status: "ended" },
            { gameId: "g1", reason: { code: 4002, kind: "closed", reason: "" }, status: "ended" },
        ];

        expect(states.map((state) => describePlayerSessionStatus(state).label)).toEqual([
            "Finding your game",
            "Joining the game",
            "Connecting",
            "Connected",
            "Connecting",
            "Reconnecting",
            "Game over",
            "Disconnected",
        ]);
    });
});
