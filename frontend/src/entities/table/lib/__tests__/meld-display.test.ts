import { describe, expect, test } from "vitest";

import { meldToDisplay } from "@/entities/table/lib/meld-display";
import { type MeldRecord } from "@/entities/table/model/types";

// Tile ID reference (136-format):
//   Man: 0-35 (type34 0-8), Pin: 36-71 (type34 9-17), Sou: 72-107 (type34 18-26)
//   Honor: 108-135 (type34 27-33)
//   Each type34 has 4 copies: tileId = type34 * 4 + copyIndex
//   Red fives: 16 (0m), 52 (0p), 88 (0s)

describe("meldToDisplay - chi", () => {
    test("calledTileId at position 0 (leftmost) after sorting", () => {
        // Chi 1m-2m-3m: tiles [0, 4, 8], called tile 0 (1m)
        // After sorting by type34: [0(1m), 4(2m), 8(3m)] → calledTile at index 0
        const meld: MeldRecord = {
            calledTileId: 0,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [4, 0, 8], // unsorted input
        };
        const display = meldToDisplay(meld);

        expect(display).toEqual([
            { face: "1m", kind: "sideways" },
            { face: "2m", kind: "upright" },
            { face: "3m", kind: "upright" },
        ]);
    });

    test("calledTileId at position 1 (middle) after sorting", () => {
        // Chi 1m-2m-3m: tiles [0, 4, 8], called tile 4 (2m)
        const meld: MeldRecord = {
            calledTileId: 4,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [0, 8, 4], // unsorted input
        };
        const display = meldToDisplay(meld);

        expect(display).toEqual([
            { face: "1m", kind: "upright" },
            { face: "2m", kind: "sideways" },
            { face: "3m", kind: "upright" },
        ]);
    });

    test("calledTileId at position 2 (rightmost) after sorting", () => {
        // Chi 1m-2m-3m: tiles [0, 4, 8], called tile 8 (3m)
        const meld: MeldRecord = {
            calledTileId: 8,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [8, 0, 4], // unsorted input
        };
        const display = meldToDisplay(meld);

        expect(display).toEqual([
            { face: "1m", kind: "upright" },
            { face: "2m", kind: "upright" },
            { face: "3m", kind: "sideways" },
        ]);
    });

    test("tiles are sorted by type-34 ascending regardless of input order", () => {
        // Chi 7s-8s-9s: type34 24,25,26
        // tileIds in reverse order
        const meld: MeldRecord = {
            calledTileId: 100,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "chi",
            tileIds: [104, 100, 96], // 9s, 8s, 7s
        };
        const display = meldToDisplay(meld);

        expect(display[0].face).toBe("7s");
        expect(display[1].face).toBe("8s");
        expect(display[2].face).toBe("9s");
    });
});

describe("meldToDisplay - pon", () => {
    test("sideways tile on left when called from kamicha (relative 1)", () => {
        // Seat 0 calls pon from seat 1 → relative = (1-0+4)%4 = 1 → position 0 (left)
        const meld: MeldRecord = {
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "pon",
            tileIds: [0, 1, 2],
        };
        const display = meldToDisplay(meld);

        expect(display[0]).toEqual({ face: "1m", kind: "sideways" });
        expect(display[1]).toEqual({ face: "1m", kind: "upright" });
        expect(display[2]).toEqual({ face: "1m", kind: "upright" });
    });

    test("sideways tile in middle when called from toimen (relative 2)", () => {
        // Seat 0 calls pon from seat 2 → relative = (2-0+4)%4 = 2 → position 1 (middle)
        const meld: MeldRecord = {
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 2,
            meldType: "pon",
            tileIds: [0, 1, 2],
        };
        const display = meldToDisplay(meld);

        expect(display[0]).toEqual({ face: "1m", kind: "upright" });
        expect(display[1]).toEqual({ face: "1m", kind: "sideways" });
        expect(display[2]).toEqual({ face: "1m", kind: "upright" });
    });

    test("sideways tile on right when called from shimocha (relative 3)", () => {
        // Seat 0 calls pon from seat 3 → relative = (3-0+4)%4 = 3 → position 2 (right)
        const meld: MeldRecord = {
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "pon",
            tileIds: [0, 1, 2],
        };
        const display = meldToDisplay(meld);

        expect(display[0]).toEqual({ face: "1m", kind: "upright" });
        expect(display[1]).toEqual({ face: "1m", kind: "upright" });
        expect(display[2]).toEqual({ face: "1m", kind: "sideways" });
    });

    test("handles wrap-around seat positions", () => {
        // Seat 3 calls pon from seat 1 → relative = (1-3+4)%4 = 2 → position 1 (middle)
        const meld: MeldRecord = {
            calledTileId: 38,
            callerSeat: 3,
            fromSeat: 1,
            meldType: "pon",
            tileIds: [36, 37, 38],
        };
        const display = meldToDisplay(meld);

        expect(display[0]).toEqual({ face: "1p", kind: "upright" });
        expect(display[1]).toEqual({ face: "1p", kind: "sideways" });
        expect(display[2]).toEqual({ face: "1p", kind: "upright" });
    });
});

describe("meldToDisplay - open_kan", () => {
    test("sideways tile at correct position with 4 tiles", () => {
        // Seat 0 calls open_kan from seat 1 → relative 1 → position 0 (left)
        const meld: MeldRecord = {
            calledTileId: 3,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "open_kan",
            tileIds: [0, 1, 2, 3],
        };
        const display = meldToDisplay(meld);

        expect(display).toHaveLength(4);
        expect(display[0]).toEqual({ face: "1m", kind: "sideways" });
        expect(display[1]).toEqual({ face: "1m", kind: "upright" });
        expect(display[2]).toEqual({ face: "1m", kind: "upright" });
        expect(display[3]).toEqual({ face: "1m", kind: "upright" });
    });

    test("sideways tile from toimen (relative 2)", () => {
        // Seat 0 from seat 2 → position 1
        const meld: MeldRecord = {
            calledTileId: 3,
            callerSeat: 0,
            fromSeat: 2,
            meldType: "open_kan",
            tileIds: [0, 1, 2, 3],
        };
        const display = meldToDisplay(meld);

        expect(display[0]).toEqual({ face: "1m", kind: "upright" });
        expect(display[1]).toEqual({ face: "1m", kind: "sideways" });
        expect(display[2]).toEqual({ face: "1m", kind: "upright" });
        expect(display[3]).toEqual({ face: "1m", kind: "upright" });
    });
});

describe("meldToDisplay - closed_kan", () => {
    test("first and last tiles are facedown, middle two are upright", () => {
        const meld: MeldRecord = {
            calledTileId: null,
            callerSeat: 0,
            fromSeat: null,
            meldType: "closed_kan",
            tileIds: [0, 1, 2, 3],
        };
        const display = meldToDisplay(meld);

        expect(display).toHaveLength(4);
        expect(display[0]).toEqual({ face: "1m", kind: "facedown" });
        expect(display[1]).toEqual({ face: "1m", kind: "upright" });
        expect(display[2]).toEqual({ face: "1m", kind: "upright" });
        expect(display[3]).toEqual({ face: "1m", kind: "facedown" });
    });

    test("uses correct tile faces for each position", () => {
        // Honor tiles: east wind (type34=27), tileIds 108-111
        const meld: MeldRecord = {
            calledTileId: null,
            callerSeat: 2,
            fromSeat: null,
            meldType: "closed_kan",
            tileIds: [108, 109, 110, 111],
        };
        const display = meldToDisplay(meld);

        expect(display[0]).toEqual({ face: "1z", kind: "facedown" });
        expect(display[1]).toEqual({ face: "1z", kind: "upright" });
        expect(display[2]).toEqual({ face: "1z", kind: "upright" });
        expect(display[3]).toEqual({ face: "1z", kind: "facedown" });
    });
});

describe("meldToDisplay - added_kan", () => {
    test("stacked tile at correct position from kamicha (left)", () => {
        // Seat 0 added_kan, original pon from seat 1 → relative 1 → position 0 (left)
        // calledTileId is the original pon's called tile; addedTileId is the 4th tile from hand
        const meld: MeldRecord = {
            addedTileId: 3,
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 1,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const display = meldToDisplay(meld);

        expect(display).toHaveLength(3);
        expect(display[0]).toEqual({ bottom: "1m", kind: "stacked", top: "1m" });
        expect(display[1]).toEqual({ face: "1m", kind: "upright" });
        expect(display[2]).toEqual({ face: "1m", kind: "upright" });
    });

    test("stacked tile at correct position from toimen (middle)", () => {
        // Seat 0 from seat 2 → position 1 (middle)
        const meld: MeldRecord = {
            addedTileId: 3,
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 2,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const display = meldToDisplay(meld);

        expect(display).toHaveLength(3);
        expect(display[0]).toEqual({ face: "1m", kind: "upright" });
        expect(display[1]).toEqual({ bottom: "1m", kind: "stacked", top: "1m" });
        expect(display[2]).toEqual({ face: "1m", kind: "upright" });
    });

    test("stacked tile at correct position from shimocha (right)", () => {
        // Seat 0 from seat 3 → position 2 (right)
        const meld: MeldRecord = {
            addedTileId: 3,
            calledTileId: 2,
            callerSeat: 0,
            fromSeat: 3,
            meldType: "added_kan",
            tileIds: [0, 1, 2, 3],
        };
        const display = meldToDisplay(meld);

        expect(display).toHaveLength(3);
        expect(display[0]).toEqual({ face: "1m", kind: "upright" });
        expect(display[1]).toEqual({ face: "1m", kind: "upright" });
        expect(display[2]).toEqual({ bottom: "1m", kind: "stacked", top: "1m" });
    });

    test("red five: original called tile on bottom, added tile on top", () => {
        // Pon of 5p (type34=13): tiles 52(0p/red), 53(5p), 54(5p)
        // Original pon called tile was 54 (normal 5p) from opponent
        // Added tile 55 (5p, fourth copy) from hand
        // Seat 1 from seat 2 → relative = (2-1+4)%4 = 1 → position 0
        const meld: MeldRecord = {
            addedTileId: 55,
            calledTileId: 54,
            callerSeat: 1,
            fromSeat: 2,
            meldType: "added_kan",
            tileIds: [52, 53, 54, 55],
        };
        const display = meldToDisplay(meld);

        expect(display).toHaveLength(3);
        // Position 0: stacked with original called tile 54 (5p) on bottom, added tile 55 (5p) on top
        expect(display[0]).toEqual({ bottom: "5p", kind: "stacked", top: "5p" });
        // Remaining tiles: 52 (0p/red) and 53 (5p) as uprights
        expect(display[1]).toEqual({ face: "0p", kind: "upright" });
        expect(display[2]).toEqual({ face: "5p", kind: "upright" });
    });

    test("red five as the original called tile stays on stack bottom", () => {
        // Pon called the red five (52=0p) from opponent, other tiles 53, 54
        // Added tile 55 from hand
        // Seat 1 from seat 2 → position 0
        const meld: MeldRecord = {
            addedTileId: 55,
            calledTileId: 52,
            callerSeat: 1,
            fromSeat: 2,
            meldType: "added_kan",
            tileIds: [52, 53, 54, 55],
        };
        const display = meldToDisplay(meld);

        expect(display).toHaveLength(3);
        // Position 0: stacked with red five 52 (0p) on bottom, added tile 55 (5p) on top
        expect(display[0]).toEqual({ bottom: "0p", kind: "stacked", top: "5p" });
        expect(display[1]).toEqual({ face: "5p", kind: "upright" });
        expect(display[2]).toEqual({ face: "5p", kind: "upright" });
    });
});
