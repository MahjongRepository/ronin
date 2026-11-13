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

function faceArtViewBox(suit: FaceSuit): FaceBox {
    const { inkCentreX, inkCentreY, scale } = FACE_ART_SUIT_SCALE[suit];
    const width = FACE_ART_VIEW.width / scale;
    const height = FACE_ART_VIEW.height / scale;
    return { height, left: inkCentreX - width / 2, top: inkCentreY - height / 2, width };
}

export {
    FACE_ART_ASPECT,
    FACE_ART_SUIT_SCALE,
    FACE_ART_VIEW,
    STANDING_BODY,
    faceArtViewBox,
    standingFaceBox,
};
export type { FaceBox, FaceSuit };
