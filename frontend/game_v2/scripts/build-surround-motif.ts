import { readFile, writeFile } from "node:fs/promises";

import { TILE_FACES_SET } from "../src/entities/tile/lib/tile-config.ts";

const SPRITE = new URL(`../src/assets/tiles/sprites/${TILE_FACES_SET}.svg`, import.meta.url);
const OUTPUT = new URL("../src/assets/table/surround-motif.svg", import.meta.url);

const REPEAT = 600;
const INK_OPACITY = 0.03;
const FACE_W = 72;
const FACE_H = 96;
const TILE_REACH = 90;
const INK_COLOURS = ["#000", "#000037", "#004900", "#9a2424", "#c61c1c"];

interface Placement {
    readonly face: string;
    readonly left: number;
    readonly rotate: number;
    readonly scale: number;
    readonly top: number;
}

const TILES: readonly Placement[] = [
    { face: "1p", left: 182, rotate: 0, scale: 0.7, top: 433 },
    { face: "7z", left: 54, rotate: 5, scale: 0.7, top: 12 },
    { face: "3s", left: 480, rotate: -16, scale: 0.85, top: 459 },
    { face: "5p", left: 322, rotate: -19, scale: 1.15, top: 166 },
    { face: "2z", left: 589, rotate: -17, scale: 1, top: 254 },
    { face: "1s", left: 275, rotate: 10, scale: 0.55, top: 579 },
    { face: "9m", left: 493, rotate: 17, scale: 0.55, top: 55 },
];

function faceSymbolAsMask(sprite: string, face: string): string {
    const symbol = new RegExp(`<symbol id="tile-${face}".*?</symbol>`, "s").exec(sprite)?.[0];
    if (symbol === undefined) {
        throw new Error(`The sprite holds no face ${face}`);
    }
    const inkPattern = INK_COLOURS.map((colour) => colour.slice(1)).join("|");
    return symbol
        .replaceAll(/(?<paint>fill|stroke)="#fff"/g, '$<paint>="HOLE"')
        .replaceAll(
            new RegExp(`(?<paint>fill|stroke)="#(?:${inkPattern})"`, "g"),
            '$<paint>="#fff"',
        )
        .replaceAll('"HOLE"', '"#000"');
}

function isInRepeat(at: number, reach: number): boolean {
    return at > -reach && at < REPEAT + reach;
}

function wrappedCopies(tile: Placement): { left: number; top: number }[] {
    const reach = TILE_REACH * tile.scale;
    const offsets = [-REPEAT, 0, REPEAT];
    return offsets
        .flatMap((across) =>
            offsets.map((down) => ({
                left: tile.left + across,
                top: tile.top + down,
            })),
        )
        .filter((copy) => isInRepeat(copy.left, reach) && isInRepeat(copy.top, reach));
}

function tileShapes(tile: Placement): string[] {
    const { face, rotate, scale } = tile;
    return wrappedCopies(tile).map(({ left, top }) =>
        [
            `<g transform="translate(${left} ${top}) rotate(${rotate}) scale(${scale})">`,
            '<rect x="-50" y="-66" width="100" height="132" rx="14"/>',
            '<rect x="-42" y="-58" width="84" height="116" rx="9" stroke-width="2"/>',
            `<rect x="${-FACE_W / 2}" y="${-FACE_H / 2}" width="${FACE_W}" height="${FACE_H}" fill="#fff" ` +
                `fill-opacity="${INK_OPACITY}" stroke="none" mask="url(#ink-${face})"/>`,
            "</g>",
        ].join(""),
    );
}

async function main(): Promise<void> {
    const sprite = await readFile(SPRITE, "utf8");
    const faces = [...new Set(TILES.map((tile) => tile.face))].toSorted();
    const masks = faces.map(
        (face) =>
            `<mask id="ink-${face}"><use href="#tile-${face}" x="${-FACE_W / 2}" y="${-FACE_H / 2}" ` +
            `width="${FACE_W}" height="${FACE_H}" fill="#fff"/></mask>`,
    );
    const shapes = TILES.flatMap(tileShapes);
    const svg = [
        `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" ` +
            `width="${REPEAT}" height="${REPEAT}" viewBox="0 0 ${REPEAT} ${REPEAT}">`,
        "<defs>",
        ...faces.map((face) => faceSymbolAsMask(sprite, face)),
        ...masks,
        "</defs>",
        `<g fill="none" stroke="#fff" stroke-opacity="${INK_OPACITY}" stroke-width="3.5" ` +
            'stroke-linecap="round" stroke-linejoin="round">',
        ...shapes,
        "</g>",
        "</svg>",
        "",
    ].join("\n");
    await writeFile(OUTPUT, svg);
    console.log(`Surround motif: ${TILES.length} tiles, ${Buffer.byteLength(svg)} bytes`);
}

main().catch((error) => {
    console.error("Surround motif generation failed:", error);
    process.exit(1);
});
