import { describe, expect, it } from "vitest";

import { HANDOFF } from "#tests/fixtures/scenario";
import { type SessionState, describePlayerSessionStatus } from "@/entities/session";

const ACTIVE = {
    attempts: { session: 0, transport: 0 },
    gameId: "g1",
    handoff: HANDOFF,
    link: "open",
    retry: null,
    status: "joining",
} as const;

describe("describePlayerSessionStatus", () => {
    it("names each session state in the player's terms, not the machine's", () => {
        const states: readonly SessionState[] = [
            ACTIVE,
            { ...ACTIVE, link: "connecting" },
            { ...ACTIVE, status: "playing" },
            { ...ACTIVE, link: "down", status: "reconnecting" },
            { gameId: "g1", reason: { kind: "game_ended" }, status: "ended" },
            { gameId: "g1", reason: { code: 4002, kind: "closed", reason: "" }, status: "ended" },
        ];

        expect(states.map((state) => describePlayerSessionStatus(state).label)).toEqual([
            "Joining the game",
            "Connecting",
            "Connected",
            "Reconnecting",
            "Game over",
            "Disconnected, returning to the lobby",
        ]);
    });
});
