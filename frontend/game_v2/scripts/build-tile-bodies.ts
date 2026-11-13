import { writeFile } from "node:fs/promises";

import {
    BODY_VIEW_WIDTH,
    LYING_BODIES,
    LYING_BODY,
    type LyingBodyShape,
    SIDE_STANDING_BACK_BODY,
    STANDING_BACK_BODIES,
    STANDING_BACK_BODY,
    STANDING_BODY,
    type StandingBackShape,
    standingBackSpan,
} from "../src/entities/tile/lib/tile-body.ts";

const OUTPUT = new URL("../src/assets/tiles/sprites/bodies.svg", import.meta.url);
const MASK_COLOUR = "--ronin-tile-ridge";
const RIM_STRENGTH_ON_TOP = 0.55;
const RIM_STRENGTH_ON_CREST = 0.3;
const RIM_STRENGTH_ON_FRONT = 0.8;
const LYING_RIM_STRENGTH_ON_TOP = 0.9;
const LYING_RIM_STRENGTH_ON_EDGE = 0.45;
const LYING_ROLL_LEAD = 0.03;
const LYING_TOP_SHINE = 0.022;
const STANDING_BACK_GLINT = 0.035;
const STANDING_BACK_FOOT = 0.08;

interface Stop {
    readonly at: number;
    readonly colour: string;
    readonly opacity?: number;
}

interface Layer {
    readonly gradient: string;
    readonly mask?: string;
}

interface Size {
    readonly height: number;
    readonly width: number;
}

interface LyingPalette {
    readonly crest: string;
    readonly lit: string;
    readonly middle: string;
    readonly rolled: string;
    readonly underLayer: readonly [string, string];
    readonly upperLayer: readonly [string, string];
}

const FACE_UP_PALETTE: LyingPalette = {
    crest: "--ronin-tile-ridge",
    lit: "--ronin-tile-face-light",
    middle: "--ronin-tile-face",
    rolled: "--ronin-tile-face-rim",
    underLayer: ["--ronin-back-shade", "--ronin-back-end"],
    upperLayer: ["--ronin-tile-side", "--ronin-tile-side-low"],
};

const FACE_DOWN_PALETTE: LyingPalette = {
    crest: "--ronin-back-rim",
    lit: "--ronin-back-light",
    middle: "--ronin-back",
    rolled: "--ronin-back-shade",
    underLayer: ["--ronin-tile-side", "--ronin-tile-side-low"],
    upperLayer: ["--ronin-back-shade", "--ronin-back-end"],
};

function formatNumber(value: number): string {
    return String(Math.round(value * 10_000) / 10_000);
}

function inViewUnits(share: number): number {
    return share * BODY_VIEW_WIDTH;
}

function sizeOf(across: number, down: number): Size {
    return { height: inViewUnits(down), width: inViewUnits(across) };
}

function renderStop({ at, colour, opacity = 1 }: Stop): string {
    const opacityStyle = opacity === 1 ? "" : ` stop-opacity: ${formatNumber(opacity)};`;
    return `<stop offset="${formatNumber(at)}" style="stop-color: var(${colour});${opacityStyle}"/>`;
}

function renderGradient(id: string, direction: "down" | "across", stops: readonly Stop[]): string {
    const end = direction === "down" ? 'x2="0" y2="1"' : 'x2="1" y2="0"';
    return `<linearGradient id="${id}" x1="0" y1="0" ${end}>${stops.map(renderStop).join("")}</linearGradient>`;
}

function renderBox({ width, height }: Size, fill: string, mask?: string): string {
    const maskAttribute = mask === undefined ? "" : ` mask="url(#${mask})"`;
    return `<rect width="${formatNumber(width)}" height="${formatNumber(height)}" fill="url(#${fill})"${maskAttribute}/>`;
}

interface Outline {
    readonly height: number;
    readonly left: number;
    readonly width: number;
}

function renderOutline({ cornerRadius, id, outline, size }: BodySymbol): string {
    const radius = formatNumber(inViewUnits(cornerRadius));
    if (outline === undefined) {
        return `<clipPath id="${id}-outline"><rect width="${formatNumber(size.width)}" height="${formatNumber(size.height)}" rx="${radius}"/></clipPath>`;
    }
    return `<clipPath id="${id}-outline"><rect x="${formatNumber(outline.left)}" width="${formatNumber(outline.width)}" height="${formatNumber(outline.height)}" rx="${radius}"/></clipPath>`;
}

function renderMask(size: Size, id: string, gradient: string): string {
    return `<mask id="${id}" maskUnits="userSpaceOnUse" x="0" y="0" width="${formatNumber(size.width)}" height="${formatNumber(size.height)}" style="mask-type: alpha">${renderBox(size, gradient)}</mask>`;
}

interface BodySymbol {
    readonly cornerRadius: number;
    readonly gradients: readonly string[];
    readonly id: string;
    readonly layers: readonly Layer[];
    readonly masks: readonly (readonly [string, string])[];
    readonly outline?: Outline;
    readonly size: Size;
}

function renderSymbol(symbol: BodySymbol): string {
    const { id, size, gradients, masks, layers } = symbol;
    const width = formatNumber(size.width);
    const height = formatNumber(size.height);
    return [
        `<symbol id="${id}" viewBox="0 0 ${width} ${height}">`,
        "<defs>",
        renderOutline(symbol),
        ...gradients,
        ...masks.map(([mask, gradient]) => renderMask(size, mask, gradient)),
        "</defs>",
        `<g clip-path="url(#${id}-outline)">`,
        ...layers.map((layer) => renderBox(size, layer.gradient, layer.mask)),
        "</g>",
        "</symbol>",
    ].join("");
}

function strengthStops(points: readonly (readonly [number, number])[]): readonly Stop[] {
    return points.map(([at, opacity]) => ({ at, colour: MASK_COLOUR, opacity }));
}

function rimStops(across: number, litRim: number, shadedRim: number): readonly Stop[] {
    const lit = litRim / across;
    const shaded = shadedRim / across;
    return [
        { at: 0, colour: "--ronin-tile-rim-light", opacity: 0.8 },
        { at: lit * 0.3, colour: "--ronin-tile-rim-light", opacity: 0.45 },
        { at: lit * 0.65, colour: "--ronin-tile-rim-light", opacity: 0.15 },
        { at: lit, colour: "--ronin-tile-rim-light", opacity: 0 },
        { at: 1 - shaded, colour: "--ronin-tile-rim-shade", opacity: 0 },
        { at: 1 - shaded * 0.6, colour: "--ronin-tile-rim-shade", opacity: 0.15 },
        { at: 1 - shaded * 0.3, colour: "--ronin-tile-rim-shade", opacity: 0.45 },
        { at: 1, colour: "--ronin-tile-rim-shade", opacity: 0.9 },
    ];
}

function standingHeightShare(depth: number): number {
    return depth / STANDING_BODY.height;
}

function standingDepthStops(): readonly Stop[] {
    const { backDepth, topFlatEnd, frontStart, footStart } = STANDING_BODY;
    return [
        { at: 0, colour: "--ronin-back-end" },
        { at: standingHeightShare(backDepth), colour: "--ronin-back" },
        { at: standingHeightShare(backDepth), colour: "--ronin-tile-top" },
        { at: standingHeightShare(topFlatEnd), colour: "--ronin-tile-top" },
        { at: standingHeightShare(frontStart - 0.02), colour: "--ronin-tile-front" },
        { at: standingHeightShare(footStart), colour: "--ronin-tile-front-low" },
        { at: 1, colour: "--ronin-tile-front-low" },
    ];
}

function standingCrestStops(): readonly Stop[] {
    const { crestStart, ridge, frontStart } = STANDING_BODY;
    const rise = ridge - crestStart;
    const fall = frontStart - ridge;
    const profile: readonly (readonly [number, number])[] = [
        [crestStart, 0],
        [crestStart + rise * 0.5, 0.3],
        [crestStart + rise * 0.85, 0.7],
        [ridge, 0.8],
        [ridge + fall * 0.2, 0.6],
        [ridge + fall * 0.55, 0.22],
        [frontStart, 0],
    ];
    return profile.map(([depth, opacity]) => ({
        at: standingHeightShare(depth),
        colour: "--ronin-tile-ridge",
        opacity,
    }));
}

function standingCrestEndStops(): readonly Stop[] {
    const { litRim, shadedRim } = STANDING_BODY;
    return strengthStops([
        [0, 0],
        [litRim * 0.5, 0.55],
        [litRim * 1.5, 1],
        [1 - shadedRim * 1.5, 1],
        [1 - shadedRim * 0.5, 0.45],
        [1, 0],
    ]);
}

function standingRimContourStops(): readonly Stop[] {
    const { crestStart, ridge, frontStart } = STANDING_BODY;
    return strengthStops([
        [0, RIM_STRENGTH_ON_TOP],
        [standingHeightShare(crestStart), RIM_STRENGTH_ON_TOP],
        [standingHeightShare(ridge), RIM_STRENGTH_ON_CREST],
        [standingHeightShare(frontStart), RIM_STRENGTH_ON_FRONT],
        [1, RIM_STRENGTH_ON_FRONT],
    ]);
}

function standingFootStops(): readonly Stop[] {
    const start = standingHeightShare(STANDING_BODY.footStart);
    return [
        { at: start, colour: "--ronin-tile-rim-shade", opacity: 0 },
        { at: start + (1 - start) * 0.55, colour: "--ronin-tile-rim-shade", opacity: 0.3 },
        { at: 1, colour: "--ronin-tile-rim-shade", opacity: 0.85 },
    ];
}

function renderStandingBody(): string {
    const id = "body-standing";
    const size = sizeOf(1, STANDING_BODY.height);
    return renderSymbol({
        cornerRadius: STANDING_BODY.cornerRadius,
        gradients: [
            renderGradient(`${id}-depth`, "down", standingDepthStops()),
            renderGradient(`${id}-crest`, "down", standingCrestStops()),
            renderGradient(`${id}-crest-ends-fade`, "across", standingCrestEndStops()),
            renderGradient(
                `${id}-rims`,
                "across",
                rimStops(1, STANDING_BODY.litRim, STANDING_BODY.shadedRim),
            ),
            renderGradient(`${id}-rim-contour-fade`, "down", standingRimContourStops()),
            renderGradient(`${id}-foot`, "down", standingFootStops()),
        ],
        id,
        layers: [
            { gradient: `${id}-depth` },
            { gradient: `${id}-crest`, mask: `${id}-crest-ends` },
            { gradient: `${id}-rims`, mask: `${id}-rim-contour` },
            { gradient: `${id}-foot` },
        ],
        masks: [
            [`${id}-crest-ends`, `${id}-crest-ends-fade`],
            [`${id}-rim-contour`, `${id}-rim-contour-fade`],
        ],
        size,
    });
}

function lyingDepthStops(shape: LyingBodyShape, palette: LyingPalette): readonly Stop[] {
    const height = shape.top + shape.edge;
    const upperLayer = shape.material === "face" ? 1 - LYING_BODY.backLayer : LYING_BODY.backLayer;
    const rollEnd = shape.top + shape.edge * LYING_BODY.roll;
    const layerEnd = shape.top + shape.edge * upperLayer;
    return [
        { at: 0, colour: palette.crest },
        { at: LYING_TOP_SHINE / height, colour: palette.lit },
        { at: (shape.top * 0.55) / height, colour: palette.middle },
        { at: (shape.top - LYING_ROLL_LEAD) / height, colour: palette.rolled },
        { at: rollEnd / height, colour: palette.upperLayer[0] },
        { at: layerEnd / height, colour: palette.upperLayer[1] },
        { at: layerEnd / height, colour: palette.underLayer[0] },
        { at: 1, colour: palette.underLayer[1] },
    ];
}

function lyingRimContourStops(shape: LyingBodyShape): readonly Stop[] {
    const height = shape.top + shape.edge;
    return strengthStops([
        [0, LYING_RIM_STRENGTH_ON_TOP],
        [(shape.top - LYING_ROLL_LEAD) / height, LYING_RIM_STRENGTH_ON_TOP],
        [(shape.top + shape.edge * LYING_BODY.roll) / height, LYING_RIM_STRENGTH_ON_EDGE],
        [1, LYING_RIM_STRENGTH_ON_EDGE],
    ]);
}

function renderLyingBody(id: string, shape: LyingBodyShape): string {
    const palette = shape.material === "face" ? FACE_UP_PALETTE : FACE_DOWN_PALETTE;
    return renderSymbol({
        cornerRadius: LYING_BODY.cornerRadius,
        gradients: [
            renderGradient(`${id}-depth`, "down", lyingDepthStops(shape, palette)),
            renderGradient(
                `${id}-rims`,
                "across",
                rimStops(shape.across, LYING_BODY.litRim, LYING_BODY.shadedRim),
            ),
            renderGradient(`${id}-rim-contour-fade`, "down", lyingRimContourStops(shape)),
        ],
        id,
        layers: [
            { gradient: `${id}-depth` },
            { gradient: `${id}-rims`, mask: `${id}-rim-contour` },
        ],
        masks: [[`${id}-rim-contour`, `${id}-rim-contour-fade`]],
        size: sizeOf(shape.across, shape.top + shape.edge),
    });
}

interface StandingBackPalette {
    readonly crest: string;
    readonly lit: string;
    readonly middle: string;
    readonly rolled: string;
    readonly side: readonly [string, string];
}

const STANDING_FACE_LAYER: StandingBackPalette = {
    crest: "--ronin-tile-ridge",
    lit: "--ronin-tile-ridge",
    middle: "--ronin-tile-top",
    rolled: "--ronin-tile-face-rim",
    side: ["--ronin-tile-side", "--ronin-tile-side-low"],
};

const STANDING_BACK_LAYER: StandingBackPalette = {
    crest: "--ronin-back-shade",
    lit: "--ronin-back-dim",
    middle: "--ronin-back-dim",
    rolled: "--ronin-back-dim-low",
    side: ["--ronin-back-dim-low", "--ronin-back-dim-low"],
};

const SIDE_FACE_LAYER: StandingBackPalette = {
    crest: "--ronin-tile-ridge",
    lit: "--ronin-tile-ridge",
    middle: "--ronin-tile-face",
    rolled: "--ronin-tile-face-rim",
    side: ["--ronin-tile-side", "--ronin-tile-side-low"],
};

const SIDE_BACK_LAYER: StandingBackPalette = {
    crest: "--ronin-back-rim",
    lit: "--ronin-back",
    middle: "--ronin-back",
    rolled: "--ronin-back-shade",
    side: ["--ronin-back-shade", "--ronin-back-end"],
};

function sideTopStops(shape: StandingBackShape, palette: StandingBackPalette): readonly Stop[] {
    const height = shape.top + shape.edge;
    const rollStart = shape.top - SIDE_STANDING_BACK_BODY.roll;
    return [
        { at: 0, colour: palette.crest },
        { at: LYING_TOP_SHINE / height, colour: palette.lit },
        { at: rollStart / height, colour: palette.middle },
        { at: shape.top / height, colour: palette.rolled },
        { at: shape.top / height, colour: palette.side[0] },
        { at: 1, colour: palette.side[1] },
    ];
}

function standingCapStops(shape: StandingBackShape): readonly Stop[] {
    const height = shape.top + shape.edge;
    const cap = standingBackSpan(shape).face;
    return [
        { at: 0, colour: STANDING_FACE_LAYER.crest },
        { at: LYING_TOP_SHINE / height, colour: STANDING_FACE_LAYER.lit },
        { at: (cap * 0.5) / height, colour: STANDING_FACE_LAYER.middle },
        { at: cap / height, colour: STANDING_FACE_LAYER.rolled },
        { at: 1, colour: STANDING_FACE_LAYER.rolled },
    ];
}

function standingBackFaceStops(shape: StandingBackShape): readonly Stop[] {
    const height = shape.top + shape.edge;
    const cap = standingBackSpan(shape).face;
    return [
        { at: 0, colour: STANDING_BACK_LAYER.crest },
        { at: cap / height, colour: STANDING_BACK_LAYER.crest },
        { at: (cap + STANDING_BACK_GLINT) / height, colour: STANDING_BACK_LAYER.lit },
        { at: (cap + (height - cap) * 0.45) / height, colour: STANDING_BACK_LAYER.middle },
        { at: (height - STANDING_BACK_FOOT) / height, colour: STANDING_BACK_LAYER.rolled },
        { at: 1, colour: STANDING_BACK_LAYER.side[1] },
    ];
}

function standingBackSplitStops(shape: StandingBackShape): readonly Stop[] {
    const { face, start } = standingBackSpan(shape);
    if (shape.backLayerSide === "bottom") {
        const split = face / (shape.top + shape.edge);
        return strengthStops([
            [0, 0],
            [split, 0],
            [split, 1],
            [1, 1],
        ]);
    }
    const ownerOnLeft = shape.backLayerSide === "right";
    const split = (ownerOnLeft ? start + face : shape.across - face) / shape.across;
    const [before, after] = ownerOnLeft ? [0, 1] : [1, 0];
    return strengthStops([
        [0, before],
        [split, before],
        [split, after],
        [1, after],
    ]);
}

function spanRimStops(shape: StandingBackShape): readonly Stop[] {
    const { back, face, start } = standingBackSpan(shape);
    const thickness = face + back;
    const { litRim, shadedRim } = SIDE_STANDING_BACK_BODY;
    return rimStops(thickness, litRim, shadedRim).map(({ at, colour, opacity }) => ({
        at: (start + at * thickness) / shape.across,
        colour,
        opacity,
    }));
}

function renderUprightBackBody(id: string, shape: StandingBackShape): string {
    return renderSymbol({
        cornerRadius: STANDING_BACK_BODY.cornerRadius,
        gradients: [
            renderGradient(`${id}-face`, "down", standingCapStops(shape)),
            renderGradient(`${id}-back`, "down", standingBackFaceStops(shape)),
            renderGradient(`${id}-split-fade`, "down", standingBackSplitStops(shape)),
            renderGradient(
                `${id}-rims`,
                "across",
                rimStops(shape.across, STANDING_BACK_BODY.litRim, STANDING_BACK_BODY.shadedRim),
            ),
        ],
        id,
        layers: [
            { gradient: `${id}-face` },
            { gradient: `${id}-back`, mask: `${id}-split` },
            { gradient: `${id}-rims` },
        ],
        masks: [[`${id}-split`, `${id}-split-fade`]],
        size: sizeOf(shape.across, shape.top + shape.edge),
    });
}

function renderSideBackBody(id: string, shape: StandingBackShape): string {
    const { back, face, start } = standingBackSpan(shape);
    const painted = shape.end === "shown" ? shape.top + shape.edge : shape.top;
    return renderSymbol({
        cornerRadius: SIDE_STANDING_BACK_BODY.cornerRadius,
        gradients: [
            renderGradient(`${id}-face`, "down", sideTopStops(shape, SIDE_FACE_LAYER)),
            renderGradient(`${id}-back`, "down", sideTopStops(shape, SIDE_BACK_LAYER)),
            renderGradient(`${id}-split-fade`, "across", standingBackSplitStops(shape)),
            renderGradient(`${id}-rims`, "across", spanRimStops(shape)),
        ],
        id,
        layers: [
            { gradient: `${id}-face` },
            { gradient: `${id}-back`, mask: `${id}-split` },
            { gradient: `${id}-rims` },
        ],
        masks: [[`${id}-split`, `${id}-split-fade`]],
        outline: {
            height: inViewUnits(painted),
            left: inViewUnits(start),
            width: inViewUnits(face + back),
        },
        size: sizeOf(shape.across, shape.top + shape.edge),
    });
}

function renderStandingBackBody(id: string, shape: StandingBackShape): string {
    return shape.backLayerSide === "bottom"
        ? renderUprightBackBody(id, shape)
        : renderSideBackBody(id, shape);
}

async function main(): Promise<void> {
    const sprite = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute" aria-hidden="true">',
        renderStandingBody(),
        ...Object.entries(LYING_BODIES).map(([id, shape]) => renderLyingBody(id, shape)),
        ...Object.entries(STANDING_BACK_BODIES).map(([id, shape]) =>
            renderStandingBackBody(id, shape),
        ),
        "</svg>",
        "",
    ].join("\n");
    await writeFile(OUTPUT, sprite);
    console.log(`Bodies: ${Buffer.byteLength(sprite)} bytes`);
}

main().catch((error: unknown) => {
    console.error("Body sprite generation failed:", error);
    process.exit(1);
});
