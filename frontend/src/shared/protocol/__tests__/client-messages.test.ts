import { describe, expect, it } from "vitest";

import {
    buildChatMessage,
    buildChiAction,
    buildConfirmRoundAction,
    buildDiscardAction,
    buildJoinGameMessage,
    buildKanAction,
    buildKyuushuAction,
    buildPassAction,
    buildPingMessage,
    buildPonAction,
    buildReconnectMessage,
    buildRiichiAction,
    buildRonAction,
    buildTsumoAction,
} from "../builders/client-messages";
import { CLIENT_MESSAGE_TYPE, GAME_ACTION, KAN_TYPE } from "../constants";

describe("client message builders", () => {
    describe("session messages", () => {
        it("buildJoinGameMessage creates correct wire format", () => {
            const msg = buildJoinGameMessage("ticket-abc-123");
            expect(msg).toEqual({
                game_ticket: "ticket-abc-123",
                t: CLIENT_MESSAGE_TYPE.JOIN_GAME,
            });
        });

        it("buildReconnectMessage creates correct wire format", () => {
            const msg = buildReconnectMessage("ticket-xyz-789");
            expect(msg).toEqual({
                game_ticket: "ticket-xyz-789",
                t: CLIENT_MESSAGE_TYPE.RECONNECT,
            });
        });

        it("buildPingMessage creates correct wire format", () => {
            const msg = buildPingMessage();
            expect(msg).toEqual({ t: CLIENT_MESSAGE_TYPE.PING });
        });

        it("buildChatMessage creates correct wire format", () => {
            const msg = buildChatMessage("Hello world");
            expect(msg).toEqual({
                t: CLIENT_MESSAGE_TYPE.CHAT,
                text: "Hello world",
            });
        });
    });

    describe("tile-based game actions", () => {
        it("buildDiscardAction creates correct wire format", () => {
            const msg = buildDiscardAction(42);
            expect(msg).toEqual({
                a: GAME_ACTION.DISCARD,
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                ti: 42,
            });
        });

        it("buildRiichiAction creates correct wire format", () => {
            const msg = buildRiichiAction(99);
            expect(msg).toEqual({
                a: GAME_ACTION.DECLARE_RIICHI,
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                ti: 99,
            });
        });

        it("buildPonAction creates correct wire format", () => {
            const msg = buildPonAction(55);
            expect(msg).toEqual({
                a: GAME_ACTION.CALL_PON,
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                ti: 55,
            });
        });

        it("buildChiAction creates correct wire format", () => {
            const msg = buildChiAction(20, [16, 24]);
            expect(msg).toEqual({
                a: GAME_ACTION.CALL_CHI,
                sequence_tiles: [16, 24],
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                ti: 20,
            });
        });

        it("buildKanAction creates correct wire format with open kan", () => {
            const msg = buildKanAction(80, KAN_TYPE.OPEN);
            expect(msg).toEqual({
                a: GAME_ACTION.CALL_KAN,
                kan_type: "open",
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                ti: 80,
            });
        });

        it("buildKanAction creates correct wire format with closed kan", () => {
            const msg = buildKanAction(0, KAN_TYPE.CLOSED);
            expect(msg).toEqual({
                a: GAME_ACTION.CALL_KAN,
                kan_type: "closed",
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                ti: 0,
            });
        });

        it("buildKanAction creates correct wire format with added kan", () => {
            const msg = buildKanAction(36, KAN_TYPE.ADDED);
            expect(msg).toEqual({
                a: GAME_ACTION.CALL_KAN,
                kan_type: "added",
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                ti: 36,
            });
        });
    });

    describe("simple game actions", () => {
        it("buildTsumoAction creates correct wire format", () => {
            const msg = buildTsumoAction();
            expect(msg).toEqual({
                a: GAME_ACTION.DECLARE_TSUMO,
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
            });
        });

        it("buildRonAction creates correct wire format", () => {
            const msg = buildRonAction();
            expect(msg).toEqual({
                a: GAME_ACTION.CALL_RON,
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
            });
        });

        it("buildKyuushuAction creates correct wire format", () => {
            const msg = buildKyuushuAction();
            expect(msg).toEqual({
                a: GAME_ACTION.CALL_KYUUSHU,
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
            });
        });

        it("buildPassAction creates correct wire format", () => {
            const msg = buildPassAction();
            expect(msg).toEqual({
                a: GAME_ACTION.PASS,
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
            });
        });

        it("buildConfirmRoundAction creates correct wire format", () => {
            const msg = buildConfirmRoundAction();
            expect(msg).toEqual({
                a: GAME_ACTION.CONFIRM_ROUND,
                t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
            });
        });
    });
});
