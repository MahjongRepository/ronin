import { describe, expect, it } from "vitest";

import { SESSION_MESSAGE_TYPE } from "@/shared/protocol/constants";
import { parseSessionMessage } from "@/shared/protocol/schemas/session";

describe("parseSessionMessage", () => {
    describe("session_error", () => {
        it("parses error with code and message", () => {
            const wire = {
                code: "not_in_game",
                message: "You must join a game first",
                type: SESSION_MESSAGE_TYPE.ERROR,
            };
            const result = parseSessionMessage(wire);
            expect(result).toEqual({
                code: "not_in_game",
                message: "You must join a game first",
                type: "session_error",
            });
        });

        it("parses reconnect error code", () => {
            const wire = {
                code: "reconnect_no_session",
                message: "No disconnected session found",
                type: SESSION_MESSAGE_TYPE.ERROR,
            };
            const result = parseSessionMessage(wire);
            expect(result.type).toBe("session_error");
            expect(result).toHaveProperty("code", "reconnect_no_session");
        });
    });

    describe("seat_control", () => {
        it("reads a reason as an AI player standing in for the seat's human, and none as the human's return", () => {
            const away = parseSessionMessage({ r: 1, s: 2, type: "seat_control" });
            const back = parseSessionMessage({ s: 2, type: "seat_control" });

            expect(away).toEqual({ reason: 1, seat: 2, type: "ai_replacement" });
            expect(back).toEqual({ seat: 2, type: "human_return" });
        });
    });

    describe("unknown type", () => {
        it("throws on unknown session message type", () => {
            const wire = { type: "nonexistent_type" };
            expect(() => parseSessionMessage(wire)).toThrow(
                "Unknown session message type: type=nonexistent_type",
            );
        });

        it("throws on numeric type (not a session message)", () => {
            const wire = { type: 8 };
            expect(() => parseSessionMessage(wire)).toThrow("Unknown session message type: type=8");
        });
    });
});
