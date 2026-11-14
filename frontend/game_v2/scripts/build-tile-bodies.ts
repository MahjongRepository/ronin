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
const LYING_FACE_SHINE_FALLOFF = 0.15;
const LYING_FACE_BEVEL = 0.1;

interface Stop {
    readonly at: number;
    readonly colour: string;
    readonly opacity?: number;
}

interface Panel {
    readonly radius: number;
    readonly top: number;
}

interface Layer {
    readonly gradient: string;
    readonly mask?: string;
    readonly panel?: Panel;
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

function panelHeight(size: Size, { radius, top }: Panel): number {
    return size.height - top + radius;
}

function renderPanel(size: Size, fill: string, panel: Panel): string {
    const radius = formatNumber(panel.radius);
    return `<rect y="${formatNumber(panel.top)}" width="${formatNumber(size.width)}" height="${formatNumber(panelHeight(size, panel))}" rx="${radius}" ry="${radius}" fill="url(#${fill})"/>`;
}

function renderLayer(size: Size, { gradient, mask, panel }: Layer): string {
    return panel === undefined
        ? renderBox(size, gradient, mask)
        : renderPanel(size, gradient, panel);
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
        ...layers.map((layer) => renderLayer(size, layer)),
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

/**
 * The shading across a lying tile's top, from its far end: a face holds its middle tone from a short shine
 * to a narrow bevel at its near end, so a row laid against it meets the same tone rather than a darker band; a back
 * shades across its whole top.
 */
function lyingTopStops(shape: LyingBodyShape, palette: LyingPalette): readonly Stop[] {
    const height = shape.top + shape.edge;
    const rolled = { at: (shape.top - LYING_ROLL_LEAD) / height, colour: palette.rolled };
    if (shape.material === "back") {
        return [{ at: (shape.top * 0.55) / height, colour: palette.middle }, rolled];
    }
    return [
        { at: LYING_FACE_SHINE_FALLOFF / height, colour: palette.middle },
        { at: (shape.top - LYING_FACE_BEVEL) / height, colour: palette.middle },
        rolled,
    ];
}

function lyingDepthStops(shape: LyingBodyShape, palette: LyingPalette): readonly Stop[] {
    const height = shape.top + shape.edge;
    const upperLayer = shape.material === "face" ? 1 - LYING_BODY.backLayer : LYING_BODY.backLayer;
    const rollEnd = shape.top + shape.edge * LYING_BODY.roll;
    const layerEnd = shape.top + shape.edge * upperLayer;
    return [
        { at: 0, colour: palette.crest },
        { at: LYING_TOP_SHINE / height, colour: palette.lit },
        ...lyingTopStops(shape, palette),
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

const SIDE_FACE_LAYER: StandingBackPalette = {
    crest: "--ronin-tile-ridge",
    lit: "--ronin-tile-ridge",
    middle: "--ronin-tile-face",
    rolled: "--ronin-tile-face-rim",
    side: ["--ronin-tile-front", "--ronin-tile-front-low"],
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

function standingCapAcrossStops(): readonly Stop[] {
    return [
        { at: 0, colour: "--ronin-tile-ridge" },
        { at: 0.04, colour: "--ronin-tile-ridge" },
        { at: 0.16, colour: "--ronin-tile-top" },
        { at: 0.84, colour: "--ronin-tile-top" },
        { at: 0.93, colour: "--ronin-tile-front" },
        { at: 1, colour: "--ronin-tile-side" },
    ];
}

function standingCapFootStops(shape: StandingBackShape): readonly Stop[] {
    const height = shape.top + shape.edge;
    const cap = standingBackSpan(shape).face;
    return [
        { at: 0, colour: "--ronin-tile-rim-shade", opacity: 0 },
        { at: (cap - 0.035) / height, colour: "--ronin-tile-rim-shade", opacity: 0 },
        { at: cap / height, colour: "--ronin-tile-rim-shade", opacity: 0.45 },
        { at: 1, colour: "--ronin-tile-rim-shade", opacity: 0.45 },
    ];
}

function uprightBackPanel(shape: StandingBackShape): Panel {
    return {
        radius: inViewUnits(STANDING_BACK_BODY.shoulderRadius),
        top: inViewUnits(standingBackSpan(shape).face),
    };
}

function standingBackDepthStops(): readonly Stop[] {
    return [
        { at: 0, colour: "--ronin-back-light" },
        { at: 0.35, colour: "--ronin-back" },
        { at: 1, colour: "--ronin-back-shade" },
    ];
}

function standingBackEdgeStops(across: number): readonly Stop[] {
    const lit = STANDING_BACK_BODY.litRim / across;
    const shaded = STANDING_BACK_BODY.shadedRim / across;
    return [
        { at: 0, colour: "--ronin-tile-rim-light", opacity: 0.3 },
        { at: lit, colour: "--ronin-tile-rim-light", opacity: 0 },
        { at: 1 - shaded, colour: "--ronin-tile-rim-shade", opacity: 0 },
        { at: 1, colour: "--ronin-tile-rim-shade", opacity: 0.5 },
    ];
}

function sideBackSplitStops(shape: StandingBackShape): readonly Stop[] {
    const { face, start } = standingBackSpan(shape);
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
    const panel = uprightBackPanel(shape);
    return renderSymbol({
        cornerRadius: STANDING_BACK_BODY.cornerRadius,
        gradients: [
            renderGradient(`${id}-cap`, "across", standingCapAcrossStops()),
            renderGradient(`${id}-cap-foot`, "down", standingCapFootStops(shape)),
            renderGradient(`${id}-back`, "down", standingBackDepthStops()),
            renderGradient(`${id}-back-edges`, "across", standingBackEdgeStops(shape.across)),
        ],
        id,
        layers: [
            { gradient: `${id}-cap` },
            { gradient: `${id}-cap-foot` },
            { gradient: `${id}-back`, panel },
            { gradient: `${id}-back-edges`, panel },
        ],
        masks: [],
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
            renderGradient(`${id}-split-fade`, "across", sideBackSplitStops(shape)),
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
