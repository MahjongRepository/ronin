import { describe, expect, it } from "vitest";

import { HANDOFF } from "#tests/fixtures/scenario";
import { type SessionState, describePlayerSessionStatus } from "@/entities/session";

const SEAT = { gameId: "g1", handoff: HANDOFF } as const;
const NO_ATTEMPTS = { session: 0, transport: 0 } as const;
const JOIN = { kind: "join" } as const;

describe("describePlayerSessionStatus", () => {
    it("names each session state in the player's terms, not the machine's, toned by its socket or, once ended, by whether it failed", () => {
        const states: readonly SessionState[] = [
            { failedLookups: 0, gameId: "g1", retryAt: null, status: "recovering" },
            {
                ...SEAT,
                attempts: NO_ATTEMPTS,
                identity: JOIN,
                sessionRetryAt: null,
                status: "identifying",
            },
            {
                ...SEAT,
                attempts: NO_ATTEMPTS,
                connectDeadline: 0,
                identity: JOIN,
                status: "connecting",
            },
            { ...SEAT, status: "playing" },
            {
                ...SEAT,
                attempts: NO_ATTEMPTS,
                identity: { kind: "reconnect", lostSeat: false },
                sessionRetryAt: null,
                status: "identifying",
            },
            {
                ...SEAT,
                attempts: { session: 0, transport: 1 },
                dueAt: 0,
                identity: { kind: "reconnect", lostSeat: true },
                status: "awaiting_retry",
            },
            { gameId: "g1", reason: { kind: "game_ended" }, status: "ended" },
            { gameId: "g1", reason: { code: 4002, kind: "closed", reason: "" }, status: "ended" },
            { gameId: "g1", reason: { code: 1006, kind: "closed", reason: "" }, status: "ended" },
            { gameId: "g1", reason: { kind: "left" }, status: "ended" },
            { gameId: "g1", reason: { code: 1008, kind: "closed", reason: "" }, status: "ended" },
            { gameId: "g1", reason: { code: "internal_error", kind: "refused" }, status: "ended" },
            { gameId: "g1", reason: { detail: "boom", kind: "failed" }, status: "ended" },
            { gameId: "g1", reason: { detail: "503", kind: "recovery_failed" }, status: "ended" },
        ];

        const shown = states.map((state) => describePlayerSessionStatus(state));
        expect(shown.map(({ label, tone, word }) => [label, tone, word])).toEqual([
            ["Finding your game", "connecting", "Connecting"],
            ["Joining the game", "connected", ""],
            ["Connecting", "connecting", "Connecting"],
            ["Connected", "connected", ""],
            ["Connecting", "connected", ""],
            ["Reconnecting", "disconnected", "Offline"],
            ["Game over", "disconnected", "Ended"],
            ["Opened in another tab", "disconnected", "Replaced"],
            ["Disconnected", "error", "Offline"],
            ["You left the game", "disconnected", ""],
            ["Removed from the game", "error", "Removed"],
            ["Disconnected", "error", "Error"],
            ["Something went wrong", "error", "Error"],
            ["Can't reach the lobby", "error", "Error"],
        ]);
    });
});
