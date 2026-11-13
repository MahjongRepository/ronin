import { writeFile } from "node:fs/promises";

import { STANDING_BODY } from "../src/entities/tile/lib/tile-body.ts";

const OUTPUT = new URL("../src/assets/tiles/sprites/bodies.svg", import.meta.url);
const BODY_WIDTH = 100;
const BODY_HEIGHT = String(STANDING_BODY.height * BODY_WIDTH);
const MASK_COLOUR = "--ronin-tile-ridge";
const RIM_STRENGTH_ON_TOP = 0.55;
const RIM_STRENGTH_ON_CREST = 0.3;
const RIM_STRENGTH_ON_FRONT = 0.8;

interface Stop {
    readonly at: number;
    readonly colour: string;
    readonly opacity?: number;
}

interface Layer {
    readonly gradient: string;
    readonly mask?: string;
}

function formatNumber(value: number): string {
    return String(Math.round(value * 10_000) / 10_000);
}

function renderStop({ at, colour, opacity = 1 }: Stop): string {
    const opacityStyle = opacity === 1 ? "" : ` stop-opacity: ${formatNumber(opacity)};`;
    return `<stop offset="${formatNumber(at)}" style="stop-color: var(${colour});${opacityStyle}"/>`;
}

function renderGradient(id: string, direction: "down" | "across", stops: readonly Stop[]): string {
    const end = direction === "down" ? 'x2="0" y2="1"' : 'x2="1" y2="0"';
    return `<linearGradient id="${id}" x1="0" y1="0" ${end}>${stops.map(renderStop).join("")}</linearGradient>`;
}

function renderBox(fill: string, mask?: string): string {
    const maskAttribute = mask === undefined ? "" : ` mask="url(#${mask})"`;
    return `<rect width="${BODY_WIDTH}" height="${BODY_HEIGHT}" fill="url(#${fill})"${maskAttribute}/>`;
}

function renderMask(id: string, gradient: string): string {
    return `<mask id="${id}" maskUnits="userSpaceOnUse" x="0" y="0" width="${BODY_WIDTH}" height="${BODY_HEIGHT}" style="mask-type: alpha">${renderBox(gradient)}</mask>`;
}

function standingHeightShare(depth: number): number {
    return depth / STANDING_BODY.height;
}

function strengthStops(points: readonly (readonly [number, number])[]): readonly Stop[] {
    return points.map(([at, opacity]) => ({ at, colour: MASK_COLOUR, opacity }));
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

function standingRimStops(): readonly Stop[] {
    const { litRim, shadedRim } = STANDING_BODY;
    return [
        { at: 0, colour: "--ronin-tile-rim-light", opacity: 0.8 },
        { at: litRim * 0.3, colour: "--ronin-tile-rim-light", opacity: 0.45 },
        { at: litRim * 0.65, colour: "--ronin-tile-rim-light", opacity: 0.15 },
        { at: litRim, colour: "--ronin-tile-rim-light", opacity: 0 },
        { at: 1 - shadedRim, colour: "--ronin-tile-rim-shade", opacity: 0 },
        { at: 1 - shadedRim * 0.6, colour: "--ronin-tile-rim-shade", opacity: 0.15 },
        { at: 1 - shadedRim * 0.3, colour: "--ronin-tile-rim-shade", opacity: 0.45 },
        { at: 1, colour: "--ronin-tile-rim-shade", opacity: 0.9 },
    ];
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
    const radius = formatNumber(STANDING_BODY.cornerRadius * BODY_WIDTH);
    const layers: readonly Layer[] = [
        { gradient: `${id}-depth` },
        { gradient: `${id}-crest`, mask: `${id}-crest-ends` },
        { gradient: `${id}-rims`, mask: `${id}-rim-contour` },
        { gradient: `${id}-foot` },
    ];
    return [
        `<symbol id="${id}" viewBox="0 0 ${BODY_WIDTH} ${BODY_HEIGHT}">`,
        "<defs>",
        `<clipPath id="${id}-outline"><rect width="${BODY_WIDTH}" height="${BODY_HEIGHT}" rx="${radius}"/></clipPath>`,
        renderGradient(`${id}-depth`, "down", standingDepthStops()),
        renderGradient(`${id}-crest`, "down", standingCrestStops()),
        renderGradient(`${id}-crest-ends-fade`, "across", standingCrestEndStops()),
        renderGradient(`${id}-rims`, "across", standingRimStops()),
        renderGradient(`${id}-rim-contour-fade`, "down", standingRimContourStops()),
        renderGradient(`${id}-foot`, "down", standingFootStops()),
        renderMask(`${id}-crest-ends`, `${id}-crest-ends-fade`),
        renderMask(`${id}-rim-contour`, `${id}-rim-contour-fade`),
        "</defs>",
        `<g clip-path="url(#${id}-outline)">`,
        ...layers.map((layer) => renderBox(layer.gradient, layer.mask)),
        "</g>",
        "</symbol>",
    ].join("");
}

async function main(): Promise<void> {
    const sprite = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute" aria-hidden="true">',
        renderStandingBody(),
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
