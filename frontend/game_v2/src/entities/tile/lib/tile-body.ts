const STANDING_BODY = {
    backDepth: 0.1,
    cornerRadius: 0.08,
    crestStart: 0.24,
    faceForeshortening: 0.93,
    faceWidth: 0.8,
    footStart: 1.43,
    frontStart: 0.44,
    height: 1.5,
    litRim: 0.06,
    ridge: 0.33,
    shadedRim: 0.11,
    topFlatEnd: 0.27,
} as const;

const BODY_VIEW_WIDTH = 100;
const TILE_BOX_ASPECT = 4 / 3;
const STANDING_OVERHANG = STANDING_BODY.height - TILE_BOX_ASPECT;

const TILE_EDGE_SHARE = 0.2;

const LYING_BODY = {
    backLayer: 0.35,
    cornerRadius: 0.07,
    edge: TILE_EDGE_SHARE,
    faceWidth: 0.8,
    litRim: 0.05,
    ownEdge: 0.25,
    ownTopShare: 0.92,
    roll: 0.1,
    shadedRim: 0.08,
} as const;

const STANDING_BACK_BODY = {
    capShare: 0.22,
    cornerRadius: 0.07,
    edge: TILE_EDGE_SHARE,
    litRim: 0.035,
    shadedRim: 0.055,
} as const;

const SIDE_STANDING_BACK_BODY = {
    cornerRadius: 0.07,
    edge: TILE_EDGE_SHARE,
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
    readonly material: BodyMaterial;
    readonly top: number;
    readonly turned: boolean;
}

function lyingShape(turned: boolean, own: boolean, material: BodyMaterial): LyingBodyShape {
    const topShare = own ? LYING_BODY.ownTopShare : 1;
    return {
        across: turned ? TILE_BOX_ASPECT : 1,
        edge: own ? LYING_BODY.ownEdge : LYING_BODY.edge,
        material,
        top: (turned ? 1 : TILE_BOX_ASPECT) * topShare,
        turned,
    };
}

const LYING_BODIES = {
    "body-back-lying": lyingShape(false, false, "back"),
    "body-back-lying-own": lyingShape(false, true, "back"),
    "body-back-lying-own-sideways": lyingShape(true, true, "back"),
    "body-back-lying-sideways": lyingShape(true, false, "back"),
    "body-lying": lyingShape(false, false, "face"),
    "body-lying-own": lyingShape(false, true, "face"),
    "body-lying-own-sideways": lyingShape(true, true, "face"),
    "body-lying-sideways": lyingShape(true, false, "face"),
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
        edge: STANDING_BACK_BODY.edge,
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
        const depth = shape.top + shape.edge;
        const face = depth * STANDING_BACK_BODY.capShare;
        return { back: depth - face, face, start: 0 };
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
    m: { inkCentreX: 149, inkCentreY: 189.5, scale: 1.04 },
    p: { inkCentreX: 150, inkCentreY: 200, scale: 1 },
    s: { inkCentreX: 150, inkCentreY: 200, scale: 1 },
    z: { inkCentreX: 150, inkCentreY: 200, scale: 1 },
} as const satisfies Record<FaceSuit, { inkCentreX: number; inkCentreY: number; scale: number }>;

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

type TileLay = "lying" | "own" | "standing";

interface TileBodyRequest {
    readonly end: StandingBackEnd;
    readonly lay: TileLay;
    readonly material: BodyMaterial;
    readonly sideways: boolean;
    readonly turn: SeatTurn;
}

interface TileBody {
    readonly across: number;
    readonly artTurn: SeatTurn;
    readonly edge: number;
    readonly face: LyingFaceBox | null;
    readonly id: LyingBodyId | StandingBackBodyId;
    readonly top: number;
    readonly uncoveredId: StandingBackBodyId | null;
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

function lyingBodyId(material: BodyMaterial, own: boolean, turned: boolean): LyingBodyId {
    if (material === "face") {
        if (own) {
            return turned ? "body-lying-own-sideways" : "body-lying-own";
        }
        return turned ? "body-lying-sideways" : "body-lying";
    }
    if (own) {
        return turned ? "body-back-lying-own-sideways" : "body-back-lying-own";
    }
    return turned ? "body-back-lying-sideways" : "body-back-lying";
}

function tileBody({ end, lay, material, sideways, turn }: TileBodyRequest): TileBody {
    const artTurn = seatTurnOf(turn + (sideways ? 90 : 0));
    if (lay === "standing" && material === "back") {
        const id = STANDING_BACK_BY_TURN[turn][end];
        const { shown } = STANDING_BACK_BY_TURN[turn];
        const { across, edge, top } = STANDING_BACK_BODIES[id];
        const uncoveredId = id === shown ? null : shown;
        return { across, artTurn, edge, face: null, id, top, uncoveredId };
    }
    const id = lyingBodyId(material, lay === "own", artTurn % 180 === 90);
    const shape = LYING_BODIES[id];
    return {
        across: shape.across,
        artTurn,
        edge: shape.edge,
        face: material === "face" ? lyingFaceBox(shape) : null,
        id,
        top: shape.top,
        uncoveredId: null,
    };
}

function faceArtViewBox(suit: FaceSuit): FaceBox {
    const { inkCentreX, inkCentreY, scale } = FACE_ART_SUIT_SCALE[suit];
    const width = FACE_ART_VIEW.width / scale;
    const height = FACE_ART_VIEW.height / scale;
    return { height, left: inkCentreX - width / 2, top: inkCentreY - height / 2, width };
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
    STANDING_BODY,
    STANDING_OVERHANG,
    TILE_EDGE_SHARE,
    faceArtViewBox,
    lyingFaceBox,
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
};
