import { type Page } from "playwright";

import { type PageRun } from "../model.ts";

/* eslint-disable id-length -- Playwright screenshot clips require x and y coordinates. */

interface GapSample {
    readonly x: number;
    readonly y: number;
    readonly width: number;
    readonly height: number;
}

async function separateRightTile(page: Page): Promise<GapSample> {
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
        return {
            height: Math.max(1, Math.floor(width * 0.08)),
            width: Math.floor(rect.width * 0.6),
            x: Math.floor(rect.x + rect.width * 0.2),
            y: Math.ceil(rect.bottom + width * 0.14),
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

async function readBackgroundPixels(page: Page, clip: GapSample): Promise<readonly number[]> {
    const hand = page.locator(".board-strip--right .hand");
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

export async function checkSeparatedHandDepth({ page, report }: PageRun): Promise<string> {
    const clip = await separateRightTile(page);
    const visible = await readPixels(page, await page.screenshot({ clip }));
    const background = await readBackgroundPixels(page, clip);
    report.expect(visible.length > 0 && visible.length === background.length, "missing gap pixels");
    const painted = visible.filter(
        (value, index) => index % 4 !== 3 && value - background[index] > 20,
    ).length;
    report.expect(painted === 0, `detached tile depth in the hand gap: ${painted} bright channels`);
    return `sampled ${visible.length / 4} gap pixels, ${painted} bright channels`;
}
