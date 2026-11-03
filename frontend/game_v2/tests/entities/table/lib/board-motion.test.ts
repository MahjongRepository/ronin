import { describe, expect, expectTypeOf, it } from "vitest";

import {
    BOARD_MOTION,
    type MotionTile,
    type TileMotion,
    planTileMotion,
} from "@/entities/table/lib/board-motion";

function tile(key: string, overrides: Partial<MotionTile> = {}): MotionTile {
    return {
        concealed: false,
        drawn: false,
        id: key,
        index: 0,
        key,
        rect: { height: 40, left: 10, top: 100, width: 30 },
        region: "hand",
        seat: "bottom",
        tsumogiri: false,
        ...overrides,
    };
}

describe("planTileMotion", () => {
    it.each([
        { mode: "step", pause: BOARD_MOTION.discardPause },
        { mode: "replay", pause: 0 },
    ] as const)("follows a discard and closes the hand with the $mode pause", ({ mode, pause }) => {
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
                delay: BOARD_MOTION.flight + pause,
                duration: BOARD_MOTION.reflow,
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
    });

    it("takes a concealed tsumogiri from the separated draw, without inventing its identity", () => {
        const hand = tile("slot", { concealed: true, id: "" });
        const drawn = tile("drawn", { concealed: true, drawn: true, id: "" });
        const discard = tile("river-4", {
            id: "4",
            rect: { ...hand.rect, top: 40 },
            region: "discards",
            tsumogiri: true,
        });
        const result = planTileMotion([hand, drawn], [hand, discard]);
        expect(result).toEqual([
            {
                delay: 0,
                duration: BOARD_MOTION.flight,
                kind: "flight",
                source: drawn.key,
                target: discard.key,
            },
        ]);
    });

    it("assembles a meld from its caller's hand and another seat's river", () => {
        const hand = tile("hand-1", { id: "1" });
        const river = tile("river-2", { id: "2", region: "discards", seat: "left" });
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

    it("fills the concealed hand-discard slot from the separated draw after the throw", () => {
        const hand = tile("slot", { concealed: true, id: "" });
        const drawn = tile("drawn", {
            concealed: true,
            drawn: true,
            id: "",
            rect: { ...hand.rect, left: 60 },
        });
        const discard = tile("river", {
            id: "4",
            rect: { ...hand.rect, top: 40 },
            region: "discards",
        });
        const result = planTileMotion([hand, drawn], [hand, discard]);
        expect(result).toEqual([
            {
                delay: BOARD_MOTION.flight + BOARD_MOTION.discardPause,
                duration: BOARD_MOTION.reflow,
                kind: "reflow",
                source: "drawn",
                target: "slot",
            },
            {
                delay: 0,
                duration: BOARD_MOTION.flight,
                kind: "flight",
                source: "slot",
                target: "river",
            },
        ]);
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
