import { describe, expect, it } from "vitest";

import { WIRE_KEY } from "@/shared/protocol";
import {
    buildChiAction,
    buildConfirmRoundAction,
    buildDiscardAction,
    buildJoinGameMessage,
    buildKanAction,
    buildKyuushuAction,
    buildPassAction,
    buildPonAction,
    buildReconnectMessage,
    buildRiichiAction,
    buildRonAction,
    buildTsumoAction,
} from "@/shared/protocol/builders/client-messages";
import { CLIENT_MESSAGE_TYPE, GAME_ACTION, KAN_TYPE } from "@/shared/protocol/constants";

describe("client message builders", () => {
    describe("session messages", () => {
        it("buildJoinGameMessage creates correct wire format", () => {
            const msg = buildJoinGameMessage("ticket-abc-123");
            expect(msg).toEqual({
                [WIRE_KEY.GAME_TICKET]: "ticket-abc-123",
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.JOIN_GAME,
            });
        });

        it("buildReconnectMessage creates correct wire format", () => {
            const msg = buildReconnectMessage("ticket-xyz-789");
            expect(msg).toEqual({
                [WIRE_KEY.GAME_TICKET]: "ticket-xyz-789",
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.RECONNECT,
            });
        });
    });

    describe("tile-based game actions", () => {
        it("buildDiscardAction creates correct wire format", () => {
            const msg = buildDiscardAction(42, 7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.DISCARD,
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.TILE_ID]: 42,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildRiichiAction creates correct wire format", () => {
            const msg = buildRiichiAction(99, 7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.DECLARE_RIICHI,
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.TILE_ID]: 99,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildPonAction creates correct wire format", () => {
            const msg = buildPonAction(55, 7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.CALL_PON,
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.TILE_ID]: 55,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildChiAction creates correct wire format", () => {
            const msg = buildChiAction(20, [16, 24], 7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.CALL_CHI,
                [WIRE_KEY.SEQUENCE_TILES]: [16, 24],
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.TILE_ID]: 20,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildKanAction creates correct wire format with open kan", () => {
            const msg = buildKanAction(80, KAN_TYPE.OPEN, 7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.CALL_KAN,
                [WIRE_KEY.ACTION_KAN_TYPE]: "open",
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.TILE_ID]: 80,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildKanAction creates correct wire format with closed kan", () => {
            const msg = buildKanAction(0, KAN_TYPE.CLOSED, 7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.CALL_KAN,
                [WIRE_KEY.ACTION_KAN_TYPE]: "closed",
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.TILE_ID]: 0,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildKanAction creates correct wire format with added kan", () => {
            const msg = buildKanAction(36, KAN_TYPE.ADDED, 7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.CALL_KAN,
                [WIRE_KEY.ACTION_KAN_TYPE]: "added",
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.TILE_ID]: 36,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });
    });

    describe("simple game actions", () => {
        it("buildTsumoAction creates correct wire format", () => {
            const msg = buildTsumoAction(7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.DECLARE_TSUMO,
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildRonAction creates correct wire format", () => {
            const msg = buildRonAction(7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.CALL_RON,
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildKyuushuAction creates correct wire format", () => {
            const msg = buildKyuushuAction(7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.CALL_KYUUSHU,
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildPassAction creates correct wire format", () => {
            const msg = buildPassAction(7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.PASS,
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });

        it("buildConfirmRoundAction creates correct wire format", () => {
            const msg = buildConfirmRoundAction(7);
            expect(msg).toEqual({
                [WIRE_KEY.ACTION]: GAME_ACTION.CONFIRM_ROUND,
                [WIRE_KEY.EVENT_TYPE]: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                [WIRE_KEY.WAIT_ID]: 7,
            });
        });
    });
});
