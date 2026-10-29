import { readFile, readdir, writeFile } from "node:fs/promises";

import { loadConfig, optimize } from "svgo";

import { TILE_FACES_SET } from "../src/entities/tile/lib/tile-config.ts";

const name = process.argv[2] ?? TILE_FACES_SET;
const TILES_DIR = new URL(`../src/assets/tiles/faces/${name}/`, import.meta.url);
const OUTPUT = new URL(`../src/assets/tiles/sprites/${name}.svg`, import.meta.url);
const VIEWBOX = "0 0 300 400";

/**
 * Extract the inner content from an SVG string (everything between the root
 * <svg> opening tag and the closing </svg> tag). Operates on clean SVGO output
 * where the root element is always a single top-level <svg>.
 *
 * Self-closing SVGs (e.g. `<svg ... />`) are valid — they indicate an empty
 * tile face (like Haku/white dragon). Returns an empty string in that case.
 */
function extractSvgInner(svgString: string): string {
    // Self-closing root element: <svg ... />
    if (svgString.trimEnd().endsWith("/>")) {
        return "";
    }
    const openTagEnd = svgString.indexOf(">") + 1;
    const closeTagStart = svgString.lastIndexOf("</svg>");
    if (openTagEnd <= 0 || closeTagStart === -1) {
        throw new Error("Malformed SVG: missing root <svg> element");
    }
    return svgString.slice(openTagEnd, closeTagStart);
}

async function main(): Promise<void> {
    const config = await loadConfig();
    const entries = await readdir(TILES_DIR);
    const files = entries.filter((f) => f.endsWith(".svg")).toSorted();

    let totalRawBytes = 0;
    const symbols: string[] = [];

    for (const file of files) {
        const raw = await readFile(new URL(file, TILES_DIR), "utf8");
        totalRawBytes += Buffer.byteLength(raw);

        const result = optimize(raw, { ...config, path: file });
        const inner = extractSvgInner(result.data);
        const id = `tile-${file.replace(".svg", "")}`;
        symbols.push(`<symbol id="${id}" viewBox="${VIEWBOX}">${inner}</symbol>`);
    }

    const sprite = [
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">',
        ...symbols,
        "</svg>",
        "",
    ].join("\n");

    await writeFile(OUTPUT, sprite);

    const spriteBytes = Buffer.byteLength(sprite);
    const pct = ((1 - spriteBytes / totalRawBytes) * 100).toFixed(1);
    console.log(
        `Sprite: ${files.length} tiles, ${totalRawBytes} -> ${spriteBytes} bytes (${pct}% reduction)`,
    );
}

main().catch((error) => {
    console.error("Sprite generation failed:", error);
    process.exit(1);
});
