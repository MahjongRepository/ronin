import { describe, expect, expectTypeOf, it } from "vitest";

import { WIRE_KEY } from "@/shared/protocol";
import { CALL_TYPE, EVENT_TYPE, KAN_TYPE, MELD_CALL_TYPE } from "@/shared/protocol/constants";
import { parseCallPrompt } from "@/shared/protocol/schemas/call-prompt";

describe("parseCallPrompt", () => {
    describe("ron prompt (CALL_TYPE=0)", () => {
        it("parses ron prompt with tileId, fromSeat, callerSeat", () => {
            const wire = {
                [WIRE_KEY.CALL_TYPE]: CALL_TYPE.RON,
                [WIRE_KEY.CALLER_SEAT]: 2,
                [WIRE_KEY.FROM_SEAT]: 0,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 42,
                [WIRE_KEY.WAIT_ID]: 4,
            };
            const result = parseCallPrompt(wire);
            expect(result).toEqual({
                availableCalls: [],
                bankSeconds: null,
                callType: CALL_TYPE.RON,
                callerSeat: 2,
                elapsedSeconds: null,
                fromSeat: 0,
                tileId: 42,
                type: "call_prompt",
                waitId: 4,
            });
        });

        it("reads the meld choices offered beside the ron and a re-send's elapsed seconds", () => {
            const wire = {
                [WIRE_KEY.AVAILABLE_CALLS]: [{ [WIRE_KEY.CALL_TYPE]: MELD_CALL_TYPE.PON }],
                [WIRE_KEY.BANK_SECONDS]: 17,
                [WIRE_KEY.CALL_TYPE]: CALL_TYPE.RON,
                [WIRE_KEY.CALLER_SEAT]: 2,
                [WIRE_KEY.WAIT_ELAPSED]: 6.5,
                [WIRE_KEY.FROM_SEAT]: 0,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 42,
                [WIRE_KEY.WAIT_ID]: 4,
            };
            const result = parseCallPrompt(wire);
            if (result.callType !== CALL_TYPE.RON) {
                throw new Error("wrong type");
            }
            expect(result.availableCalls).toEqual([{ callType: MELD_CALL_TYPE.PON }]);
            expect(result.elapsedSeconds).toBe(6.5);
            expect(result.bankSeconds).toBe(17);
            expectTypeOf(result.bankSeconds).toEqualTypeOf<number | null>();
        });
    });

    describe("chankan prompt (CALL_TYPE=2)", () => {
        it("parses chankan prompt with tileId, fromSeat, callerSeat and the kan it offers to rob", () => {
            const wire = {
                [WIRE_KEY.CALL_TYPE]: CALL_TYPE.CHANKAN,
                [WIRE_KEY.CALLER_SEAT]: 3,
                [WIRE_KEY.FROM_SEAT]: 1,
                [WIRE_KEY.KAN_TYPE]: KAN_TYPE.CLOSED,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 100,
            };
            const result = parseCallPrompt(wire);
            expect(result).toEqual({
                bankSeconds: null,
                callType: CALL_TYPE.CHANKAN,
                callerSeat: 3,
                elapsedSeconds: null,
                fromSeat: 1,
                kanType: KAN_TYPE.CLOSED,
                tileId: 100,
                type: "call_prompt",
                waitId: null,
            });
        });

        it("refuses a chankan prompt that names no kan, or an open one, which chankan never robs", () => {
            const wire = {
                [WIRE_KEY.CALL_TYPE]: CALL_TYPE.CHANKAN,
                [WIRE_KEY.CALLER_SEAT]: 3,
                [WIRE_KEY.FROM_SEAT]: 1,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 100,
            };
            expect(() => parseCallPrompt(wire)).toThrow();
            expect(() =>
                parseCallPrompt({ ...wire, [WIRE_KEY.KAN_TYPE]: KAN_TYPE.OPEN }),
            ).toThrow();
        });
    });

    describe("meld prompt (CALL_TYPE=1)", () => {
        it("parses meld prompt with chi options (tuple pairs)", () => {
            const wire = {
                [WIRE_KEY.AVAILABLE_CALLS]: [
                    {
                        [WIRE_KEY.CALL_TYPE]: MELD_CALL_TYPE.CHI,
                        [WIRE_KEY.CALL_OPTIONS]: [
                            [4, 8],
                            [8, 12],
                        ],
                    },
                ],
                [WIRE_KEY.CALL_TYPE]: CALL_TYPE.MELD,
                [WIRE_KEY.CALLER_SEAT]: 1,
                [WIRE_KEY.FROM_SEAT]: 0,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 6,
            };
            const result = parseCallPrompt(wire);
            expect(result.type).toBe("call_prompt");
            expect(result.callType).toBe(CALL_TYPE.MELD);
            expect(result.callerSeat).toBe(1);
            expect(result.fromSeat).toBe(0);
            expect(result.tileId).toBe(6);
            expect("availableCalls" in result && result.availableCalls).toEqual([
                {
                    callType: MELD_CALL_TYPE.CHI,
                    options: [
                        [4, 8],
                        [8, 12],
                    ],
                },
            ]);
        });

        it.each([
            {
                [WIRE_KEY.AVAILABLE_CALLS]: [{ [WIRE_KEY.CALL_TYPE]: MELD_CALL_TYPE.CHI }],
                name: "a chi with no pair",
            },
            {
                [WIRE_KEY.AVAILABLE_CALLS]: [
                    { [WIRE_KEY.CALL_TYPE]: MELD_CALL_TYPE.CHI, [WIRE_KEY.CALL_OPTIONS]: [] },
                ],
                name: "a chi with an empty pair list",
            },
            { [WIRE_KEY.AVAILABLE_CALLS]: [], name: "no call at all" },
        ])("refuses a meld prompt offering $name", ({ [WIRE_KEY.AVAILABLE_CALLS]: ac }) => {
            const wire = {
                [WIRE_KEY.AVAILABLE_CALLS]: ac,
                [WIRE_KEY.CALL_TYPE]: CALL_TYPE.MELD,
                [WIRE_KEY.CALLER_SEAT]: 2,
                [WIRE_KEY.FROM_SEAT]: 1,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 20,
            };
            expect(() => parseCallPrompt(wire)).toThrow();
        });

        it("parses meld prompt with multiple available calls", () => {
            const wire = {
                [WIRE_KEY.AVAILABLE_CALLS]: [
                    { [WIRE_KEY.CALL_TYPE]: MELD_CALL_TYPE.PON },
                    { [WIRE_KEY.CALL_TYPE]: MELD_CALL_TYPE.CHI, [WIRE_KEY.CALL_OPTIONS]: [[0, 8]] },
                ],
                [WIRE_KEY.CALL_TYPE]: CALL_TYPE.MELD,
                [WIRE_KEY.CALLER_SEAT]: 1,
                [WIRE_KEY.FROM_SEAT]: 0,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 4,
            };
            const result = parseCallPrompt(wire);
            expect("availableCalls" in result && result.availableCalls).toHaveLength(2);
        });
    });

    describe("unknown call type", () => {
        it("throws on unknown clt value", () => {
            const wire = {
                [WIRE_KEY.CALL_TYPE]: 99,
                [WIRE_KEY.CALLER_SEAT]: 0,
                [WIRE_KEY.FROM_SEAT]: 1,
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.CALL_PROMPT,
                [WIRE_KEY.TILE_ID]: 10,
            };
            expect(() => parseCallPrompt(wire)).toThrow("Unknown call prompt type: CALL_TYPE=99");
        });
    });
});
