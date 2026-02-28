import { type MeldType } from "../constants";

export interface DecodedMeld {
    calledTileId: number | null;
    callerSeat: number;
    fromSeat: number | null;
    meldType: MeldType;
    tileIds: number[];
}

// IMME offset ranges
const CHI_OFFSET = 0;
const CHI_COUNT = 4032; // 21 * 64 * 3
const PON_OFFSET = CHI_OFFSET + CHI_COUNT; // 4032
const PON_COUNT = 1224; // 34 * 4 * 3 * 3
const SHOUMINKAN_OFFSET = PON_OFFSET + PON_COUNT; // 5256
const SHOUMINKAN_COUNT = 408; // 34 * 4 * 3
const DAIMINKAN_OFFSET = SHOUMINKAN_OFFSET + SHOUMINKAN_COUNT; // 5664
const DAIMINKAN_COUNT = 408; // 34 * 4 * 3
const ANKAN_OFFSET = DAIMINKAN_OFFSET + DAIMINKAN_COUNT; // 6072
const ANKAN_COUNT = 34;

// Total: 6106 meld indices x 4 seats = 24424 values (fits in 15 bits)
const MAX_VALUE = (ANKAN_OFFSET + ANKAN_COUNT) * 4 - 1; // 24423

const CHI_SEQS_PER_SUIT = 7;
const MISSING_COPIES = 4;
const CALLED_POSITIONS = 3;
const FROM_OFFSETS = 3;
const CALLED_COPIES = 4;

function allFourCopies(tile34: number): number[] {
    return [tile34 * 4, tile34 * 4 + 1, tile34 * 4 + 2, tile34 * 4 + 3];
}

function copiesExcluding(tile34: number, missingCopy: number): number[] {
    return allFourCopies(tile34).filter((_tileId, copyIdx) => copyIdx !== missingCopy);
}

function extractChiBase(meldIndex: number) {
    const calledPos = meldIndex % 3;
    const remainder = Math.trunc(meldIndex / 3);
    const copyIndex = remainder % 64;
    const baseIndex = Math.trunc(remainder / 64);
    return { baseIndex, calledPos, copyIndex };
}

function extractChiTiles(baseIndex: number, copyIndex: number) {
    const suitIndex = Math.trunc(baseIndex / CHI_SEQS_PER_SUIT);
    const startInSuit = baseIndex % CHI_SEQS_PER_SUIT;
    const tile34Lo = suitIndex * 9 + startInSuit;

    const copyLo = Math.trunc(copyIndex / 16);
    const copyMid = Math.trunc(copyIndex / 4) % 4;
    const copyHi = copyIndex % 4;

    return [tile34Lo * 4 + copyLo, (tile34Lo + 1) * 4 + copyMid, (tile34Lo + 2) * 4 + copyHi];
}

function decodeChi(meldIndex: number, callerSeat: number): DecodedMeld {
    const { baseIndex, calledPos, copyIndex } = extractChiBase(meldIndex);
    const tileIds = extractChiTiles(baseIndex, copyIndex);

    return {
        calledTileId: tileIds[calledPos],
        callerSeat,
        fromSeat: (callerSeat + 3) % 4,
        meldType: "chi",
        tileIds,
    };
}

function extractPonFields(ponIndex: number) {
    const fromOffset = ponIndex % FROM_OFFSETS;
    let remainder = Math.trunc(ponIndex / FROM_OFFSETS);
    const calledPos = remainder % CALLED_POSITIONS;
    remainder = Math.trunc(remainder / CALLED_POSITIONS);
    const missingCopy = remainder % MISSING_COPIES;
    const tile34 = Math.trunc(remainder / MISSING_COPIES);
    return { calledPos, fromOffset, missingCopy, tile34 };
}

function decodePon(ponIndex: number, callerSeat: number): DecodedMeld {
    const { calledPos, fromOffset, missingCopy, tile34 } = extractPonFields(ponIndex);
    const tileIds = copiesExcluding(tile34, missingCopy);

    return {
        calledTileId: tileIds[calledPos],
        callerSeat,
        fromSeat: (callerSeat + fromOffset + 1) % 4,
        meldType: "pon",
        tileIds,
    };
}

function decodeOpenKan(localIndex: number, callerSeat: number, meldType: MeldType): DecodedMeld {
    const fromOffset = localIndex % FROM_OFFSETS;
    const remainder = Math.trunc(localIndex / FROM_OFFSETS);
    const calledCopy = remainder % CALLED_COPIES;
    const tile34 = Math.trunc(remainder / CALLED_COPIES);

    return {
        calledTileId: tile34 * 4 + calledCopy,
        callerSeat,
        fromSeat: (callerSeat + fromOffset + 1) % 4,
        meldType,
        tileIds: allFourCopies(tile34),
    };
}

function decodeAnkan(localIndex: number, callerSeat: number): DecodedMeld {
    return {
        calledTileId: null,
        callerSeat,
        fromSeat: null,
        meldType: "closed_kan",
        tileIds: allFourCopies(localIndex),
    };
}

type MeldDecoder = (localIndex: number, callerSeat: number) => DecodedMeld;

// Dispatch table: [offset, count, decoder] sorted by offset ascending
const MELD_RANGES: [number, number, MeldDecoder][] = [
    [CHI_OFFSET, CHI_COUNT, decodeChi],
    [PON_OFFSET, PON_COUNT, decodePon],
    [SHOUMINKAN_OFFSET, SHOUMINKAN_COUNT, (li, cs) => decodeOpenKan(li, cs, "added_kan")],
    [DAIMINKAN_OFFSET, DAIMINKAN_COUNT, (li, cs) => decodeOpenKan(li, cs, "open_kan")],
    [ANKAN_OFFSET, ANKAN_COUNT, decodeAnkan],
];

export function decodeMeldCompact(value: number): DecodedMeld {
    if (!Number.isInteger(value) || value < 0 || value > MAX_VALUE) {
        throw new RangeError(`IMME value must be 0-${MAX_VALUE}, got ${value}`);
    }

    const callerSeat = value % 4;
    const meldIndex = Math.trunc(value / 4);

    for (const [offset, count, decoder] of MELD_RANGES) {
        if (meldIndex < offset + count) {
            return decoder(meldIndex - offset, callerSeat);
        }
    }

    throw new RangeError(`IMME value ${value} (meld_index=${meldIndex}) out of range`);
}
