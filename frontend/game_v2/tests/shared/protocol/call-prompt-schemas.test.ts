import { describe, expect, it } from "vitest";

import { CALL_TYPE, EVENT_TYPE, KAN_TYPE, MELD_CALL_TYPE } from "@/shared/protocol/constants";
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
                wi: 4,
            };
            const result = parseCallPrompt(wire);
            expect(result).toEqual({
                availableCalls: [],
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
                ac: [{ clt: MELD_CALL_TYPE.PON }],
                clt: CALL_TYPE.RON,
                cs: 2,
                el: 1.5,
                frs: 0,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 42,
                wi: 4,
            };
            const result = parseCallPrompt(wire);
            if (result.callType !== CALL_TYPE.RON) {
                throw new Error("wrong type");
            }
            expect(result.availableCalls).toEqual([{ callType: MELD_CALL_TYPE.PON }]);
            expect(result.elapsedSeconds).toBe(1.5);
        });
    });

    describe("chankan prompt (clt=2)", () => {
        it("parses chankan prompt with tileId, fromSeat, callerSeat and the kan it offers to rob", () => {
            const wire = {
                clt: CALL_TYPE.CHANKAN,
                cs: 3,
                frs: 1,
                kty: KAN_TYPE.CLOSED,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 100,
            };
            const result = parseCallPrompt(wire);
            expect(result).toEqual({
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
                clt: CALL_TYPE.CHANKAN,
                cs: 3,
                frs: 1,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 100,
            };
            expect(() => parseCallPrompt(wire)).toThrow();
            expect(() => parseCallPrompt({ ...wire, kty: KAN_TYPE.OPEN })).toThrow();
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

        it.each([
            { ac: [{ clt: MELD_CALL_TYPE.CHI }], name: "a chi with no pair" },
            { ac: [{ clt: MELD_CALL_TYPE.CHI, opt: [] }], name: "a chi with an empty pair list" },
            { ac: [], name: "no call at all" },
        ])("refuses a meld prompt offering $name", ({ ac }) => {
            const wire = {
                ac,
                clt: CALL_TYPE.MELD,
                cs: 2,
                frs: 1,
                t: EVENT_TYPE.CALL_PROMPT,
                ti: 20,
            };
            expect(() => parseCallPrompt(wire)).toThrow();
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
