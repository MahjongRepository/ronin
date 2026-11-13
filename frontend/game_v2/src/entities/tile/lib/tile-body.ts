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

interface StandingBackShape {
    readonly across: number;
    readonly backLayerSide: BackLayerSide;
    readonly edge: number;
    readonly top: number;
}

function standingBackShape(backLayerSide: BackLayerSide): StandingBackShape {
    const upright = backLayerSide === "bottom";
    return {
        across: upright ? 1 : TILE_BOX_ASPECT,
        backLayerSide,
        edge: STANDING_BACK_BODY.edge,
        top: upright ? TILE_BOX_ASPECT : 1,
    };
}

const STANDING_BACK_BODIES = {
    "body-back-standing": standingBackShape("bottom"),
    "body-back-standing-left": standingBackShape("right"),
    "body-back-standing-right": standingBackShape("left"),
} as const satisfies Record<string, StandingBackShape>;

type StandingBackBodyId = keyof typeof STANDING_BACK_BODIES;

function standingBackCap(shape: StandingBackShape): number {
    const depth = shape.backLayerSide === "bottom" ? shape.top + shape.edge : shape.across;
    return depth * STANDING_BACK_BODY.capShare;
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
    0: "body-back-standing",
    180: "body-back-standing",
    270: "body-back-standing-right",
    90: "body-back-standing-left",
} as const satisfies Record<SeatTurn, StandingBackBodyId>;

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

function tileBody({ lay, material, sideways, turn }: TileBodyRequest): TileBody {
    const artTurn = seatTurnOf(turn + (sideways ? 90 : 0));
    if (lay === "standing" && material === "back") {
        const id = STANDING_BACK_BY_TURN[turn];
        const { across, edge, top } = STANDING_BACK_BODIES[id];
        return { across, artTurn, edge, face: null, id, top };
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
    STANDING_BACK_BODY,
    STANDING_BODY,
    STANDING_OVERHANG,
    TILE_EDGE_SHARE,
    faceArtViewBox,
    lyingFaceBox,
    standingBackCap,
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
    StandingBackShape,
    TileBody,
    TileBodyRequest,
    TileLay,
};
