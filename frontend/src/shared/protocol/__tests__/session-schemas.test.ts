import { describe, expect, it } from "vitest";

import { SESSION_MESSAGE_TYPE } from "@/shared/protocol/constants";
import { parseSessionMessage } from "@/shared/protocol/schemas/session";

describe("parseSessionMessage", () => {
    describe("session_error", () => {
        it("parses error with code and message", () => {
            const wire = {
                code: "action_failed",
                message: "Invalid discard: tile not in hand",
                type: SESSION_MESSAGE_TYPE.ERROR,
            };
            const result = parseSessionMessage(wire);
            expect(result).toEqual({
                code: "action_failed",
                message: "Invalid discard: tile not in hand",
                type: "session_error",
            });
        });

        it("parses reconnect error code", () => {
            const wire = {
                code: "reconnect_game_gone",
                message: "Game no longer exists",
                type: SESSION_MESSAGE_TYPE.ERROR,
            };
            const result = parseSessionMessage(wire);
            expect(result.type).toBe("session_error");
            expect(result).toHaveProperty("code", "reconnect_game_gone");
        });
    });

    describe("pong", () => {
        it("parses pong with minimal output", () => {
            const wire = { type: SESSION_MESSAGE_TYPE.PONG };
            const result = parseSessionMessage(wire);
            expect(result).toEqual({ type: "pong" });
        });
    });

    describe("player_reconnected", () => {
        it("transforms player_name to playerName", () => {
            const wire = {
                player_name: "Alice",
                type: SESSION_MESSAGE_TYPE.PLAYER_RECONNECTED,
            };
            const result = parseSessionMessage(wire);
            expect(result).toEqual({
                playerName: "Alice",
                type: "player_reconnected",
            });
        });
    });

    describe("chat", () => {
        it("parses chat with playerName and text", () => {
            const wire = {
                player_name: "Bob",
                text: "Hello world!",
                type: SESSION_MESSAGE_TYPE.CHAT,
            };
            const result = parseSessionMessage(wire);
            expect(result).toEqual({
                playerName: "Bob",
                text: "Hello world!",
                type: "chat",
            });
        });
    });

    describe("player_left", () => {
        it("transforms player_name to playerName", () => {
            const wire = {
                player_name: "Charlie",
                type: SESSION_MESSAGE_TYPE.PLAYER_LEFT,
            };
            const result = parseSessionMessage(wire);
            expect(result).toEqual({
                playerName: "Charlie",
                type: "player_left",
            });
        });
    });

    describe("game_left", () => {
        it("parses game_left with minimal output", () => {
            const wire = { type: SESSION_MESSAGE_TYPE.GAME_LEFT };
            const result = parseSessionMessage(wire);
            expect(result).toEqual({ type: "game_left" });
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
