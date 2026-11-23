import { describe, expect, expectTypeOf, it } from "vitest";

import {
    BOARD_MOTION,
    type MotionTile,
    type TileMotion,
    planTileMotion,
} from "@/entities/table/lib/board-motion";

function tile(key: string, overrides: Partial<MotionTile> = {}): MotionTile {
    const rect = overrides.rect ?? { height: 40, left: 10, top: 100, width: 30 };
    return {
        concealed: false,
        drawn: false,
        id: key,
        index: 0,
        key,
        latest: false,
        painted: rect,
        rect,
        region: "hand",
        seat: "bottom",
        tsumogiri: false,
        ...overrides,
    };
}

function heldDraw(target: string): TileMotion {
    return { delay: 0, duration: 0, kind: "hold", source: null, target };
}

function openingHold(target: string): TileMotion {
    return { ...heldDraw(target), delay: BOARD_MOTION.drawHold };
}

describe("planTileMotion", () => {
    it("resizes a laid meld tile even when its corner stays fixed", () => {
        const hand = tile("hand");
        const meld = tile("meld", { region: "melds" });
        const resized = { ...meld, rect: { ...meld.rect, height: 32, width: 24 } };
        const result = planTileMotion([hand, meld], [hand, resized]);
        expect(result).toEqual([
            {
                delay: 0,
                duration: BOARD_MOTION.meldShift,
                kind: "reflow",
                source: meld.key,
                target: meld.key,
            },
        ]);
    });

    it.each(["step", "replay"] as const)(
        "follows a discard and closes the hand at its landing in %s mode",
        (mode) => {
            const first = tile("0");
            const second = tile("1", { rect: { ...first.rect, left: 40 } });
            const discarded = tile("river-1", {
                id: "1",
                rect: { ...first.rect, left: 60, top: 40 },
                region: "discards",
            });
            const moved = tile("0", { rect: { ...first.rect, left: 20 } });
            const result = planTileMotion([first, second], [moved, discarded], mode);
            expect(result).toEqual([
                {
                    delay: BOARD_MOTION.landing,
                    duration: BOARD_MOTION.handClose,
                    kind: "reflow",
                    source: "0",
                    target: "0",
                },
                {
                    delay: 0,
                    duration: BOARD_MOTION.flight,
                    kind: "flight",
                    source: "1",
                    target: "river-1",
                },
            ]);
            expectTypeOf(result).toEqualTypeOf<readonly TileMotion[]>();
        },
    );

    it("assembles a meld from its caller's hand and another seat's river", () => {
        const hand = tile("hand-1", { id: "1" });
        const river = tile("river-2", {
            id: "2",
            region: "discards",
            seat: "left",
        });
        const meld = [hand, river].map((source) =>
            tile(`meld-${source.id}`, {
                id: source.id,
                rect: { ...source.rect, left: 200 },
                region: "melds",
            }),
        );
        const result = planTileMotion([hand, river], meld);
        expect(result.map(({ source, target, kind }) => ({ kind, source, target }))).toEqual([
            { kind: "flight", source: "hand-1", target: "meld-1" },
            { kind: "flight", source: "river-2", target: "meld-2" },
        ]);
    });

    it("opens a hole in the middle of an opponent's concealed hand for a tedashi and closes it after the landing, but not for a tsumogiri", () => {
        const hand = [0, 1, 2, 3].map((index) =>
            tile(`slot-${index}`, {
                concealed: true,
                id: "",
                index,
                rect: { height: 40, left: 10 + 30 * index, top: 100, width: 30 },
                seat: "right",
            }),
        );
        const drawn = tile("drawn", {
            concealed: true,
            drawn: true,
            id: "",
            rect: { height: 40, left: 140, top: 100, width: 30 },
            seat: "right",
        });
        const tedashi = tile("river", {
            id: "4",
            region: "discards",
            seat: "right",
        });
        const flight = {
            delay: 0,
            duration: BOARD_MOTION.flight,
            kind: "flight",
            target: "river",
        };
        const shift = {
            delay: BOARD_MOTION.landing + BOARD_MOTION.holeHold,
            duration: BOARD_MOTION.handClose,
            kind: "reflow",
        };
        expect(planTileMotion([...hand, drawn], [...hand, tedashi])).toEqual([
            { ...shift, source: "slot-2", target: "slot-1" },
            { ...shift, source: "slot-3", target: "slot-2" },
            { ...shift, source: "drawn", target: "slot-3" },
            { ...flight, source: "slot-1" },
        ]);
        expect(
            planTileMotion([...hand, drawn], [...hand, { ...tedashi, tsumogiri: true }]),
        ).toEqual([{ ...flight, source: "drawn" }]);
    });

    it("holds the viewer's and an opponent's concealed draw in step and observe mode, and nothing in a replay", () => {
        const own = tile("own");
        const ownDrawn = tile("own-drawn", { drawn: true, id: "9" });
        const opponent = tile("right-slot", {
            concealed: true,
            id: "",
            seat: "right",
        });
        const opponentDrawn = tile("right-drawn", {
            concealed: true,
            drawn: true,
            id: "",
            seat: "right",
        });
        const river = tile("river", { region: "discards", seat: "left" });
        const before = [own, opponent, river];
        const after = [own, ownDrawn, opponent, opponentDrawn, river];
        expect(
            (["step", "observe", "replay"] as const).map((mode) =>
                planTileMotion(before, after, mode),
            ),
        ).toEqual([
            [heldDraw("own-drawn"), heldDraw("right-drawn")],
            [heldDraw("own-drawn"), heldDraw("right-drawn")],
            [],
        ]);
    });

    it("holds an opponent's face-up draw only while observing", () => {
        const before = [
            tile("own"),
            tile("right-face", { id: "5", seat: "right" }),
            tile("river", { region: "discards", seat: "left" }),
        ];
        const after = [
            ...before,
            tile("right-face-drawn", { drawn: true, id: "6", seat: "right" }),
        ];
        expect(
            (["observe", "step", "replay"] as const).map((mode) =>
                planTileMotion(before, after, mode),
            ),
        ).toEqual([[heldDraw("right-face-drawn")], [], []]);
    });

    it("holds the round's opening draw for any seat by the draw hold, with or after its deal, but not in a replay", () => {
        const own = tile("own");
        const opponent = tile("right-slot", {
            concealed: true,
            id: "",
            seat: "right",
        });
        const dealerDrawn = tile("own-drawn", { drawn: true, id: "9" });
        const opponentDrawn = tile("right-drawn", {
            concealed: true,
            drawn: true,
            id: "",
            seat: "right",
        });
        expect(planTileMotion([], [own, dealerDrawn, opponent], "step")).toEqual([
            openingHold("own-drawn"),
        ]);
        expect(planTileMotion([own, opponent], [own, opponent, opponentDrawn], "observe")).toEqual([
            openingHold("right-drawn"),
        ]);
        expect(planTileMotion([], [own, dealerDrawn, opponent], "replay")).toEqual([]);
    });

    it("reveals unknown hand slots in order without turning another seat's hidden tiles face up", () => {
        const before = [0, 1].map((index) =>
            tile(`slot-${index}`, { concealed: true, id: "", index }),
        );
        const after = before.map((_source, index) =>
            tile(`face-${index}`, { concealed: false, id: String(index), index }),
        );
        const result = planTileMotion(before, after);
        expect(result.map(({ source, delay, kind }) => ({ delay, kind, source }))).toEqual([
            { delay: 0, kind: "reveal", source: "slot-0" },
            { delay: BOARD_MOTION.revealTile, kind: "reveal", source: "slot-1" },
        ]);
        expect(planTileMotion(before, before)).toEqual([]);
    });
});
