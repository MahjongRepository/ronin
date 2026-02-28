import { describe, expect, it } from "vitest";

import { EVENT_TYPE, SESSION_MESSAGE_TYPE } from "../constants";
import { parseServerMessage } from "../schemas/message";

describe("parseServerMessage", () => {
    describe("session messages (string type field)", () => {
        it("parses a pong message", () => {
            const raw = { type: SESSION_MESSAGE_TYPE.PONG };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({ type: "pong" });
        });

        it("parses a session error message", () => {
            const raw = {
                code: "invalid_ticket",
                message: "Ticket expired",
                type: SESSION_MESSAGE_TYPE.ERROR,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                code: "invalid_ticket",
                message: "Ticket expired",
                type: "session_error",
            });
        });

        it("parses a player_reconnected message", () => {
            const raw = {
                player_name: "Alice",
                type: SESSION_MESSAGE_TYPE.PLAYER_RECONNECTED,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                playerName: "Alice",
                type: "player_reconnected",
            });
        });

        it("parses a chat message", () => {
            const raw = {
                player_name: "Alice",
                text: "Hello!",
                type: SESSION_MESSAGE_TYPE.CHAT,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                playerName: "Alice",
                text: "Hello!",
                type: "chat",
            });
        });

        it("parses a player_left message", () => {
            const raw = {
                player_name: "Bob",
                type: SESSION_MESSAGE_TYPE.PLAYER_LEFT,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                playerName: "Bob",
                type: "player_left",
            });
        });

        it("parses a game_left message", () => {
            const raw = { type: SESSION_MESSAGE_TYPE.GAME_LEFT };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({ type: "game_left" });
        });

        it("parses a game_reconnected message", () => {
            const raw = {
                cp: 2,
                dc: [3, 5],
                dd: [
                    [3, 5],
                    [2, 4],
                ],
                di: [10],
                dl: 0,
                gid: "game-123",
                h: 0,
                mt: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                n: 1,
                p: [
                    { ai: 0, nm: "Alice", s: 0 },
                    { ai: 1, nm: "Bot1", s: 1 },
                    { ai: 1, nm: "Bot2", s: 2 },
                    { ai: 1, nm: "Bot3", s: 3 },
                ],
                pst: [
                    { dsc: [], ml: [], ri: false, s: 0, sc: 250 },
                    { dsc: [{ tg: true, ti: 50 }], ml: [100], ri: false, s: 1, sc: 250 },
                    { dsc: [], ml: [], ri: false, s: 2, sc: 250 },
                    { dsc: [], ml: [], ri: false, s: 3, sc: 250 },
                ],
                r: 0,
                s: 0,
                tr: 60,
                type: SESSION_MESSAGE_TYPE.GAME_RECONNECTED,
                w: 0,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed!.type).toBe("game_reconnected");
        });
    });

    describe("game events (integer t field)", () => {
        it("parses a draw event", () => {
            // seat=0, tileId=5 -> d = 0*136 + 5 = 5
            const raw = { d: 5, t: EVENT_TYPE.DRAW };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                availableActions: [],
                seat: 0,
                tileId: 5,
                type: "draw",
            });
        });

        it("parses a discard event", () => {
            // plain discard: seat=1, tileId=10 -> d = 0*544 + 1*136 + 10 = 146
            const raw = { d: 146, t: EVENT_TYPE.DISCARD };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                isRiichi: false,
                isTsumogiri: false,
                seat: 1,
                tileId: 10,
                type: "discard",
            });
        });

        it("parses a game_started event", () => {
            const raw = {
                dd: [
                    [1, 2],
                    [3, 4],
                ],
                dl: 0,
                gid: "g-abc",
                p: [
                    { ai: 0, nm: "Alice", s: 0 },
                    { ai: 1, nm: "Bot", s: 1 },
                    { ai: 1, nm: "Bot2", s: 2 },
                    { ai: 1, nm: "Bot3", s: 3 },
                ],
                t: EVENT_TYPE.GAME_STARTED,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed!.type).toBe("game_started");
        });

        it("parses a call_prompt event (ron)", () => {
            const raw = {
                clt: 0,
                cs: 2,
                frs: 1,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 50,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                callType: 0,
                callerSeat: 2,
                fromSeat: 1,
                tileId: 50,
                type: "call_prompt",
            });
        });

        it("parses a round_end event (tsumo)", () => {
            const raw = {
                ct: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                hr: { fu: 30, han: 3, yk: [{ han: 1, yi: 0 }] },
                ml: [],
                rc: 1,
                rt: 0,
                sch: { "0": 50, "1": -20, "2": -20, "3": -10 },
                scs: { "0": 300, "1": 250, "2": 250, "3": 200 },
                t: EVENT_TYPE.ROUND_END,
                ws: 0,
                wt: 10,
            };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed!.type).toBe("round_end");
        });

        it("parses a furiten event", () => {
            const raw = { f: true, t: EVENT_TYPE.FURITEN };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({ isFuriten: true, type: "furiten" });
        });

        it("parses a riichi_declared event", () => {
            const raw = { s: 2, t: EVENT_TYPE.RIICHI_DECLARED };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({ seat: 2, type: "riichi_declared" });
        });

        it("parses a dora_revealed event", () => {
            const raw = { t: EVENT_TYPE.DORA_REVEALED, ti: 100 };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({ tileId: 100, type: "dora_revealed" });
        });

        it("parses an error event", () => {
            const raw = { cd: "action_failed", msg: "Not your turn", t: EVENT_TYPE.ERROR };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeNull();
            expect(parsed).toEqual({
                code: "action_failed",
                message: "Not your turn",
                type: "error",
            });
        });
    });

    describe("error handling", () => {
        it("returns error when message has neither type nor t field", () => {
            const raw = { data: "something" };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("neither");
            expect(parsed).toBeNull();
        });

        it("returns error with descriptive message for unknown string type", () => {
            const raw = { type: "nonexistent_type" };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("type=nonexistent_type");
            expect(parsed).toBeNull();
        });

        it("returns error with descriptive message for unknown integer t", () => {
            const raw = { t: 99 };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("t=99");
            expect(parsed).toBeNull();
        });

        it("returns error when valid t but malformed payload", () => {
            // draw event needs a `d` field
            const raw = { t: EVENT_TYPE.DRAW, wrong_field: 5 };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("t=1");
            expect(parsed).toBeNull();
        });

        it("returns error when valid type but malformed payload", () => {
            // session_error needs code and message fields
            const raw = { type: SESSION_MESSAGE_TYPE.ERROR };
            const [err, parsed] = parseServerMessage(raw);
            expect(err).toBeInstanceOf(Error);
            expect(err!.message).toContain("type=session_error");
            expect(parsed).toBeNull();
        });
    });
});
