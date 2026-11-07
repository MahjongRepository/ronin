import { type Page } from "playwright";

import { type PageRun } from "../model.ts";

/* eslint-disable id-length -- Playwright screenshot clips require x and y coordinates. */

interface GapSample {
    readonly x: number;
    readonly y: number;
    readonly width: number;
    readonly height: number;
}

/** A side hand's drawn gap to sample, and the top strip's drawn gap (px) its clear table must match. */
interface DrawnGap {
    readonly clip: GapSample;
    readonly topGap: number;
}

/** What a gap's pixels show against the bare table: channels brighter than it, and the rows holding one. */
interface GapPaint {
    readonly brightChannels: number;
    readonly brightRows: number;
    readonly rows: number;
}

type Side = "left" | "right";

async function drawnGapOf(page: Page, side: Side): Promise<DrawnGap | null> {
    return page.evaluate((strip) => {
        const drawn = document.querySelector(`.board-strip--${strip} .hand-drawn-gap > .tile`);
        if (drawn === null) {
            return null;
        }
        const last = drawn.parentElement?.previousElementSibling?.querySelector(".tile");
        if (!(drawn instanceof HTMLElement) || !(last instanceof HTMLElement)) {
            throw new Error(`Missing ${strip} drawn tile and the tile before it`);
        }
        const a = drawn.getBoundingClientRect();
        const b = last.getBoundingClientRect();
        const top = Math.min(a.bottom, b.bottom);
        const bottom = Math.max(a.top, b.top);
        return {
            clip: {
                height: Math.max(1, Math.floor(bottom - top)),
                width: Math.floor(a.width * 0.6),
                x: Math.floor(a.x + a.width * 0.2),
                y: Math.ceil(top),
            },
            topGap: Number.parseFloat(getComputedStyle(drawn).getPropertyValue("--geo-dg")),
        };
    }, side);
}

/** A right tile carried out of its hand: the band its edge fills under it, and the gap's table past that edge. */
interface SeparatedTile {
    readonly edge: GapSample;
    readonly gap: GapSample;
}

async function separateRightTile(page: Page): Promise<SeparatedTile> {
    return page.evaluate(() => {
        const slot = document.querySelector(".board-strip--right .hand-tile:last-child");
        const tile = slot?.querySelector(".tile");
        if (!(slot instanceof HTMLElement) || !(tile instanceof HTMLElement)) {
            throw new Error("Missing right hand tile");
        }
        slot.classList.remove("hand-drawn-gap");
        const width = slot.offsetWidth;
        const animation = slot.animate([{ left: `${width * 1.2}px` }, { left: "0px" }], {
            duration: 200,
            fill: "both",
        });
        animation.pause();
        animation.currentTime = 0;
        const rect = tile.getBoundingClientRect();
        const column = {
            width: Math.floor(rect.width * 0.6),
            x: Math.floor(rect.x + rect.width * 0.2),
        };
        return {
            edge: {
                ...column,
                height: Math.max(1, Math.floor(width * 0.11)),
                y: Math.ceil(rect.bottom),
            },
            gap: {
                ...column,
                height: Math.max(1, Math.floor(width * 0.08)),
                y: Math.ceil(rect.bottom + width * 0.14),
            },
        };
    });
}

async function readPixels(page: Page, png: Buffer): Promise<readonly number[]> {
    return page.evaluate(
        async (bytes) => {
            const image = await createImageBitmap(new Blob([new Uint8Array(bytes)]));
            const canvas = document.createElement("canvas");
            canvas.width = image.width;
            canvas.height = image.height;
            const context = canvas.getContext("2d");
            if (context === null) {
                throw new Error("Cannot sample tile depth screenshot");
            }
            context.drawImage(image, 0, 0);
            image.close();
            return [...context.getImageData(0, 0, canvas.width, canvas.height).data];
        },
        [...png],
    );
}

async function readBackgroundPixels(
    page: Page,
    side: Side,
    clip: GapSample,
): Promise<readonly number[]> {
    const hand = page.locator(`.board-strip--${side} .hand`);
    await hand.evaluate((element) => {
        element.style.visibility = "hidden";
    });
    try {
        return await readPixels(page, await page.screenshot({ clip }));
    } finally {
        await hand.evaluate((element) => {
            element.style.removeProperty("visibility");
        });
    }
}

async function paintOf(page: Page, side: Side, clip: GapSample): Promise<GapPaint> {
    const visible = await readPixels(page, await page.screenshot({ clip }));
    const background = await readBackgroundPixels(page, side, clip);
    if (visible.length === 0 || visible.length !== background.length) {
        throw new Error(`Missing ${side} gap pixels`);
    }
    const rowLength = visible.length / clip.height;
    const bright = visible.map((value, index) => index % 4 !== 3 && value - background[index] > 20);
    const rows = Array.from({ length: clip.height }, (_row, row) =>
        bright.slice(row * rowLength, (row + 1) * rowLength).includes(true),
    );
    return {
        brightChannels: bright.filter(Boolean).length,
        brightRows: rows.filter(Boolean).length,
        rows: rows.length,
    };
}

/**
 * A side hand's drawn gap shows the edge of the tile the light lays it on (the hand's last tile on the left, the
 * drawn tile on the right), where the hairlines' seam masks must not reach, and keeps the top strip's gap of table
 * clear past that edge; a tile moved out of its hand keeps its whole edge attached and carries none into the gap it
 * leaves.
 */
export async function checkSeparatedHandDepth({ page, report }: PageRun): Promise<string> {
    const shown: string[] = [];
    for (const side of ["left", "right"] as const) {
        const gap = await drawnGapOf(page, side);
        if (gap !== null) {
            const paint = await paintOf(page, side, gap.clip);
            const clear = paint.rows - paint.brightRows;
            report.expect(paint.brightRows > 0, `no tile edge in the ${side} hand's drawn gap`);
            report.expect(
                clear >= gap.topGap - 1,
                `the ${side} hand's drawn gap keeps ${clear}px clear past the edge, under the top strip's ${gap.topGap}px gap`,
            );
            shown.push(`${side} drawn gap ${paint.brightRows}px edge, ${clear}px clear`);
        }
    }
    const separated = await separateRightTile(page);
    const edge = await paintOf(page, "right", separated.edge);
    report.expect(
        edge.brightRows === edge.rows,
        `the separated right tile's edge is cut: ${edge.brightRows} of ${edge.rows} rows under it painted`,
    );
    const { brightChannels } = await paintOf(page, "right", separated.gap);
    report.expect(
        brightChannels === 0,
        `detached tile depth in the hand gap: ${brightChannels} bright channels`,
    );
    return [
        ...shown,
        `separated tile edge ${edge.brightRows}px, gap ${brightChannels} bright channels`,
    ].join(", ");
}
