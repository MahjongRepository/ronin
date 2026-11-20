import { describe, expect, test } from "vitest";

import {
    LYING_BODIES,
    STANDING_BACK_BODIES,
    lyingFaceBox,
    standingBackSpan,
    tileBody,
} from "@/entities/tile/lib/tile-body";

describe("lyingFaceBox", () => {
    test("keeps each face-up lying body's art inside its top", () => {
        const faceUp = Object.values(LYING_BODIES).filter((shape) => shape.material === "face");
        for (const shape of faceUp) {
            const box = lyingFaceBox(shape);
            expect(box.left).toBeGreaterThan(0);
            expect(box.left + box.width).toBeLessThan(shape.across);
            expect(box.top).toBeGreaterThan(0);
            expect(box.top + box.height).toBeLessThan(shape.top);
        }
    });
});

describe("tileBody", () => {
    test("picks a lying body by the tile's pose on the screen, its art turned with the seat, square-topped when joined", () => {
        const bodies = ([0, 90, 180, 270] as const).flatMap((turn) =>
            [false, true].map((sideways) => {
                const body = tileBody({
                    end: "shown",
                    joined: false,
                    lay: "lying",
                    material: "face",
                    sideways,
                    turn,
                });
                return `${turn}${sideways ? " sideways" : ""}: ${body.id} ${body.artTurn}`;
            }),
        );

        expect(bodies).toEqual([
            "0: body-lying 0",
            "0 sideways: body-lying-sideways 90",
            "90: body-lying-sideways 90",
            "90 sideways: body-lying 180",
            "180: body-lying 180",
            "180 sideways: body-lying-sideways 270",
            "270: body-lying-sideways 270",
            "270 sideways: body-lying 0",
        ]);
        expect(
            (["face", "back"] as const).map(
                (material) =>
                    tileBody({
                        end: "shown",
                        joined: true,
                        lay: "lying",
                        material,
                        sideways: false,
                        turn: 90,
                    }).id,
            ),
        ).toEqual(["body-lying-sideways-joined", "body-back-lying-sideways-joined"]);
    });

    test("stands an opponent's back in its seat's body, a revealed face lying in its stead", () => {
        const backs = ([90, 180, 270] as const).map(
            (turn) =>
                tileBody({
                    end: "shown",
                    joined: false,
                    lay: "standing",
                    material: "back",
                    sideways: false,
                    turn,
                }).id,
        );
        const revealed = tileBody({
            end: "shown",
            joined: false,
            lay: "standing",
            material: "face",
            sideways: false,
            turn: 90,
        });

        expect(backs).toEqual([
            "body-back-standing-left",
            "body-back-standing",
            "body-back-standing-right",
        ]);
        expect([revealed.id, revealed.artTurn]).toEqual(["body-lying-sideways", 90]);
    });
});

describe("standingBackSpan", () => {
    test("paints a side seat's standing back from its owner's edge, the two seats mirrored", () => {
        const [left, right] = (
            ["body-back-standing-left", "body-back-standing-right"] as const
        ).map((id) => {
            const shape = STANDING_BACK_BODIES[id];
            const { back, face, start } = standingBackSpan(shape);
            return { across: shape.across, back, face, start };
        });

        expect(left.start).toBe(0);
        expect(right.start + right.face + right.back).toBeCloseTo(right.across);
        expect([right.face, right.back]).toEqual([left.face, left.back]);
    });
});
