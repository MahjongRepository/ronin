const STANDING_BODY = {
    backDepth: 0.07,
    cornerRadius: 0.08,
    crestStart: 0.17,
    faceForeshortening: 0.93,
    faceWidth: 0.8,
    footStart: 1.43,
    frontStart: 0.31,
    height: 1.5,
    litRim: 0.06,
    ridge: 0.23,
    shadedRim: 0.11,
    topFlatEnd: 0.19,
} as const;

const BODY_VIEW_WIDTH = 100;
const TILE_BOX_ASPECT = 4 / 3;
const STANDING_OVERHANG = STANDING_BODY.height - TILE_BOX_ASPECT;

const LYING_TOP_SHARE = 0.85;
const LYING_EDGE_SHARE = 0.28;
const STANDING_BACK_EDGE_SHARE = 0.2;

const LYING_BODY = {
    backLayer: 0.35,
    cornerRadius: 0.07,
    edge: LYING_EDGE_SHARE,
    faceWidth: 0.8,
    litRim: 0.05,
    roll: 0.1,
    shadedRim: 0.08,
    topShare: LYING_TOP_SHARE,
} as const;

const STANDING_BACK_BODY = {
    capDepth: 0.62,
    capFaceShare: 0.58,
    capRoll: 0.06,
    cornerRadius: 0.07,
    edge: STANDING_BACK_EDGE_SHARE,
    litRim: 0.035,
    rise: 0.24,
    shadedRim: 0.055,
} as const;

const UPRIGHT_BACK_EDGE = STANDING_BACK_BODY.edge + STANDING_BACK_BODY.rise;

const SIDE_STANDING_BACK_BODY = {
    cornerRadius: 0.07,
    edge: STANDING_BACK_EDGE_SHARE,
    faceShare: 0.58,
    litRim: 0.03,
    roll: 0.045,
    shadedRim: 0.04,
    thickness: 0.72,
} as const;

type BodyMaterial = "back" | "face";

interface LyingBodyShape {
    readonly across: number;
    readonly edge: number;
    readonly joined: boolean;
    readonly material: BodyMaterial;
    readonly top: number;
    readonly turned: boolean;
}

/**
 * A lying body's shape. A `joined` one, laid against the edge of a tile above it on screen, has square top corners, so
 * none of that tile's edge shows through them.
 */
function lyingShape(turned: boolean, material: BodyMaterial, joined = false): LyingBodyShape {
    return {
        across: turned ? TILE_BOX_ASPECT : 1,
        edge: LYING_BODY.edge,
        joined,
        material,
        top: (turned ? 1 : TILE_BOX_ASPECT) * LYING_BODY.topShare,
        turned,
    };
}

const LYING_BODIES = {
    "body-back-lying": lyingShape(false, "back"),
    "body-back-lying-joined": lyingShape(false, "back", true),
    "body-back-lying-sideways": lyingShape(true, "back"),
    "body-back-lying-sideways-joined": lyingShape(true, "back", true),
    "body-lying": lyingShape(false, "face"),
    "body-lying-joined": lyingShape(false, "face", true),
    "body-lying-sideways": lyingShape(true, "face"),
    "body-lying-sideways-joined": lyingShape(true, "face", true),
} as const satisfies Record<string, LyingBodyShape>;

type LyingBodyId = keyof typeof LYING_BODIES;

type BackLayerSide = "bottom" | "left" | "right";

type StandingBackEnd = "covered" | "shown";

interface StandingBackShape {
    readonly across: number;
    readonly backLayerSide: BackLayerSide;
    readonly edge: number;
    readonly end: StandingBackEnd;
    readonly top: number;
}

function uprightBackShape(): StandingBackShape {
    return {
        across: 1,
        backLayerSide: "bottom",
        edge: UPRIGHT_BACK_EDGE,
        end: "shown",
        top: TILE_BOX_ASPECT,
    };
}

function sideBackShape(backLayerSide: "left" | "right", end: StandingBackEnd): StandingBackShape {
    return {
        across: TILE_BOX_ASPECT,
        backLayerSide,
        edge: SIDE_STANDING_BACK_BODY.edge,
        end,
        top: 1,
    };
}

const STANDING_BACK_BODIES = {
    "body-back-standing": uprightBackShape(),
    "body-back-standing-left": sideBackShape("right", "shown"),
    "body-back-standing-left-covered": sideBackShape("right", "covered"),
    "body-back-standing-right": sideBackShape("left", "shown"),
    "body-back-standing-right-covered": sideBackShape("left", "covered"),
} as const satisfies Record<string, StandingBackShape>;

type StandingBackBodyId = keyof typeof STANDING_BACK_BODIES;

interface StandingBackSpan {
    readonly back: number;
    readonly face: number;
    readonly start: number;
}

function standingBackSpan(shape: StandingBackShape): StandingBackSpan {
    if (shape.backLayerSide === "bottom") {
        const face = STANDING_BACK_BODY.capDepth;
        return { back: shape.top + shape.edge - face, face, start: 0 };
    }
    const { faceShare, thickness } = SIDE_STANDING_BACK_BODY;
    const ownerOnLeft = shape.backLayerSide === "right";
    return {
        back: thickness * (1 - faceShare),
        face: thickness * faceShare,
        start: ownerOnLeft ? 0 : shape.across - thickness,
    };
}

const FACE_ART_ASPECT = 4 / 3;
const FACE_ART_VIEW = { height: 400, width: 300 } as const;

type FaceSuit = "m" | "p" | "s" | "z";

const FACE_ART_SUIT_SCALE = {
    m: { inkCentreY: 189.5, scale: 1.04 },
    p: { inkCentreY: 200, scale: 1 },
    s: { inkCentreY: 200, scale: 1 },
    z: { inkCentreY: 200, scale: 1 },
} as const satisfies Record<FaceSuit, { inkCentreY: number; scale: number }>;

interface FaceBox {
    readonly height: number;
    readonly left: number;
    readonly top: number;
    readonly width: number;
}

function standingFaceBox(): FaceBox {
    const { faceWidth, faceForeshortening, frontStart, footStart } = STANDING_BODY;
    const height = faceWidth * FACE_ART_ASPECT * faceForeshortening;
    return {
        height,
        left: (1 - faceWidth) / 2,
        top: (frontStart + footStart - height) / 2,
        width: faceWidth,
    };
}

interface LyingFaceBox extends FaceBox {
    readonly turned: boolean;
}

function lyingFaceBox(shape: LyingBodyShape): LyingFaceBox {
    const topShare = shape.top / (shape.turned ? 1 : TILE_BOX_ASPECT);
    const along = LYING_BODY.faceWidth * FACE_ART_ASPECT;
    const width = shape.turned ? along : LYING_BODY.faceWidth;
    const height = (shape.turned ? LYING_BODY.faceWidth : along) * topShare;
    return {
        height,
        left: (shape.across - width) / 2,
        top: (shape.top - height) / 2,
        turned: shape.turned,
        width,
    };
}

const SEAT_TURNS = [0, 90, 180, 270] as const;

type SeatTurn = (typeof SEAT_TURNS)[number];

type TileLay = "lying" | "standing";

interface TileBodyRequest {
    readonly end: StandingBackEnd;
    readonly joined: boolean;
    readonly lay: TileLay;
    readonly material: BodyMaterial;
    readonly sideways: boolean;
    readonly turn: SeatTurn;
}

interface TileSlot {
    readonly across: number;
    readonly down: number;
}

interface TileBody {
    readonly across: number;
    readonly artTurn: SeatTurn;
    readonly edge: number;
    readonly face: LyingFaceBox | null;
    readonly id: LyingBodyId | StandingBackBodyId;
    readonly slot: TileSlot;
    readonly top: number;
    readonly uncoveredId: StandingBackBodyId | null;
}

const STANDING_SLOT: TileSlot = { across: 1, down: 1 };

function lyingSlot(turn: SeatTurn): TileSlot {
    const share = LYING_BODY.topShare;
    return turn % 180 === 0 ? { across: 1, down: share } : { across: share, down: 1 };
}

function seatTurnOf(degrees: number): SeatTurn {
    const normal = ((degrees % 360) + 360) % 360;
    const turn = SEAT_TURNS.find((candidate) => candidate === normal);
    if (turn === undefined) {
        throw new Error(`A tile turns by quarters, not ${degrees}deg`);
    }
    return turn;
}

const STANDING_BACK_BY_TURN = {
    0: { covered: "body-back-standing", shown: "body-back-standing" },
    180: { covered: "body-back-standing", shown: "body-back-standing" },
    270: { covered: "body-back-standing-right-covered", shown: "body-back-standing-right" },
    90: { covered: "body-back-standing-left-covered", shown: "body-back-standing-left" },
} as const satisfies Record<SeatTurn, Record<StandingBackEnd, StandingBackBodyId>>;

const LYING_BODY_IDS = {
    back: {
        flat: { free: "body-back-lying", joined: "body-back-lying-joined" },
        turned: { free: "body-back-lying-sideways", joined: "body-back-lying-sideways-joined" },
    },
    face: {
        flat: { free: "body-lying", joined: "body-lying-joined" },
        turned: { free: "body-lying-sideways", joined: "body-lying-sideways-joined" },
    },
} as const satisfies Record<
    BodyMaterial,
    Record<"flat" | "turned", Record<"free" | "joined", LyingBodyId>>
>;

function lyingBodyId(material: BodyMaterial, turned: boolean, joined: boolean): LyingBodyId {
    return LYING_BODY_IDS[material][turned ? "turned" : "flat"][joined ? "joined" : "free"];
}

function tileBody({ end, joined, lay, material, sideways, turn }: TileBodyRequest): TileBody {
    const artTurn = seatTurnOf(turn + (sideways ? 90 : 0));
    if (lay === "standing" && material === "back") {
        const id = STANDING_BACK_BY_TURN[turn][end];
        const { shown } = STANDING_BACK_BY_TURN[turn];
        const { across, edge, top } = STANDING_BACK_BODIES[id];
        const uncoveredId = id === shown ? null : shown;
        return { across, artTurn, edge, face: null, id, slot: STANDING_SLOT, top, uncoveredId };
    }
    const id = lyingBodyId(material, artTurn % 180 === 90, joined);
    const shape = LYING_BODIES[id];
    return {
        across: shape.across,
        artTurn,
        edge: shape.edge,
        face: material === "face" ? lyingFaceBox(shape) : null,
        id,
        slot: lyingSlot(turn),
        top: shape.top,
        uncoveredId: null,
    };
}

function faceArtViewBox(suit: FaceSuit): FaceBox {
    const { inkCentreY, scale } = FACE_ART_SUIT_SCALE[suit];
    const width = FACE_ART_VIEW.width / scale;
    const height = FACE_ART_VIEW.height / scale;
    return { height, left: (FACE_ART_VIEW.width - width) / 2, top: inkCentreY - height / 2, width };
}

export {
    BODY_VIEW_WIDTH,
    FACE_ART_ASPECT,
    FACE_ART_SUIT_SCALE,
    FACE_ART_VIEW,
    LYING_BODIES,
    LYING_BODY,
    STANDING_BACK_BODIES,
    SIDE_STANDING_BACK_BODY,
    STANDING_BACK_BODY,
    STANDING_BACK_EDGE_SHARE,
    STANDING_BODY,
    STANDING_OVERHANG,
    UPRIGHT_BACK_EDGE,
    faceArtViewBox,
    lyingFaceBox,
    lyingSlot,
    standingBackSpan,
    standingFaceBox,
    tileBody,
};
export type {
    BackLayerSide,
    BodyMaterial,
    FaceBox,
    FaceSuit,
    LyingBodyId,
    LyingBodyShape,
    LyingFaceBox,
    SeatTurn,
    StandingBackBodyId,
    StandingBackEnd,
    StandingBackShape,
    StandingBackSpan,
    TileBody,
    TileBodyRequest,
    TileLay,
    TileSlot,
};
