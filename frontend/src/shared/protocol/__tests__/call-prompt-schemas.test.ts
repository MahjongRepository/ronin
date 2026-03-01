import { describe, expect, it } from "vitest";

import { CALL_TYPE, EVENT_TYPE, MELD_CALL_TYPE } from "@/shared/protocol/constants";
import { parseCallPrompt } from "@/shared/protocol/schemas/call-prompt";

describe("parseCallPrompt", () => {
    describe("ron prompt (clt=0)", () => {
        it("parses ron prompt with tileId, fromSeat, callerSeat", () => {
            const wire = {
                clt: CALL_TYPE.RON,
                cs: 2,
                frs: 0,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 42,
            };
            const result = parseCallPrompt(wire);
            expect(result).toEqual({
                callType: CALL_TYPE.RON,
                callerSeat: 2,
                fromSeat: 0,
                tileId: 42,
                type: "call_prompt",
            });
        });
    });

    describe("chankan prompt (clt=2)", () => {
        it("parses chankan prompt with same shape as ron", () => {
            const wire = {
                clt: CALL_TYPE.CHANKAN,
                cs: 3,
                frs: 1,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 100,
            };
            const result = parseCallPrompt(wire);
            expect(result).toEqual({
                callType: CALL_TYPE.CHANKAN,
                callerSeat: 3,
                fromSeat: 1,
                tileId: 100,
                type: "call_prompt",
            });
        });
    });

    describe("meld prompt (clt=1)", () => {
        it("parses meld prompt with chi options (tuple pairs)", () => {
            const wire = {
                ac: [
                    {
                        clt: MELD_CALL_TYPE.CHI,
                        opt: [
                            [4, 8],
                            [8, 12],
                        ],
                    },
                ],
                clt: CALL_TYPE.MELD,
                cs: 1,
                frs: 0,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 6,
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

        it("parses meld prompt with pon (null options)", () => {
            const wire = {
                ac: [{ clt: MELD_CALL_TYPE.PON }],
                clt: CALL_TYPE.MELD,
                cs: 2,
                frs: 3,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 20,
            };
            const result = parseCallPrompt(wire);
            expect("availableCalls" in result && result.availableCalls).toEqual([
                { callType: MELD_CALL_TYPE.PON, options: null },
            ]);
        });

        it("parses meld prompt with multiple available calls", () => {
            const wire = {
                ac: [{ clt: MELD_CALL_TYPE.PON }, { clt: MELD_CALL_TYPE.CHI, opt: [[0, 8]] }],
                clt: CALL_TYPE.MELD,
                cs: 1,
                frs: 0,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 4,
            };
            const result = parseCallPrompt(wire);
            expect("availableCalls" in result && result.availableCalls).toHaveLength(2);
        });
    });

    describe("unknown call type", () => {
        it("throws on unknown clt value", () => {
            const wire = {
                clt: 99,
                cs: 0,
                frs: 1,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 10,
            };
            expect(() => parseCallPrompt(wire)).toThrow("Unknown call prompt type: clt=99");
        });
    });
});
