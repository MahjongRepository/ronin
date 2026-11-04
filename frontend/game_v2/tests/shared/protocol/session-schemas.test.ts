import { describe, expect, it } from "vitest";

import { WIRE_KEY } from "@/shared/protocol";
import { SESSION_MESSAGE_TYPE } from "@/shared/protocol/constants";
import { parseSessionMessage } from "@/shared/protocol/schemas/session";

describe("parseSessionMessage", () => {
    describe("session_error", () => {
        it("parses error with code and message, and the wait id a rate limit names", () => {
            const wire = {
                [WIRE_KEY.SESSION_ERROR_CODE]: "not_in_game",
                [WIRE_KEY.SESSION_ERROR_MESSAGE]: "You must join a game first",
                [WIRE_KEY.SESSION_TYPE]: SESSION_MESSAGE_TYPE.ERROR,
            };
            const rateLimited = {
                [WIRE_KEY.SESSION_ERROR_CODE]: "rate_limited",
                [WIRE_KEY.SESSION_ERROR_MESSAGE]: "",
                [WIRE_KEY.SESSION_TYPE]: "session_error",
                [WIRE_KEY.WAIT_ID]: 6,
            };

            expect(parseSessionMessage(wire)).toEqual({
                code: "not_in_game",
                message: "You must join a game first",
                type: "session_error",
                waitId: null,
            });
            expect(parseSessionMessage(rateLimited)).toMatchObject({ waitId: 6 });
        });

        it("parses reconnect error code", () => {
            const wire = {
                [WIRE_KEY.SESSION_ERROR_CODE]: "reconnect_no_session",
                [WIRE_KEY.SESSION_ERROR_MESSAGE]: "No disconnected session found",
                [WIRE_KEY.SESSION_TYPE]: SESSION_MESSAGE_TYPE.ERROR,
            };
            const result = parseSessionMessage(wire);
            expect(result.type).toBe("session_error");
            expect(result).toHaveProperty("code", "reconnect_no_session");
        });
    });

    describe("seat_control", () => {
        it("reads a reason as an AI player standing in for the seat's human, and none as the human's return", () => {
            const away = parseSessionMessage({
                [WIRE_KEY.SEAT_CONTROL_REASON]: 1,
                [WIRE_KEY.SEAT]: 2,
                [WIRE_KEY.SESSION_TYPE]: "seat_control",
            });
            const back = parseSessionMessage({
                [WIRE_KEY.SEAT]: 2,
                [WIRE_KEY.SESSION_TYPE]: "seat_control",
            });

            expect(away).toEqual({ reason: 1, seat: 2, type: "ai_replacement" });
            expect(back).toEqual({ seat: 2, type: "human_return" });
        });
    });

    describe("unknown type", () => {
        it("throws on unknown session message type", () => {
            const wire = { [WIRE_KEY.SESSION_TYPE]: "nonexistent_type" };
            expect(() => parseSessionMessage(wire)).toThrow(
                "Unknown session message type: SESSION_TYPE=nonexistent_type",
            );
        });

        it("throws on numeric type (not a session message)", () => {
            const wire = { [WIRE_KEY.SESSION_TYPE]: 8 };
            expect(() => parseSessionMessage(wire)).toThrow(
                "Unknown session message type: SESSION_TYPE=8",
            );
        });
    });
});
