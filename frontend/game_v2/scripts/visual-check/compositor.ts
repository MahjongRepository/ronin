import { type Page } from "playwright";

const FRAME_WAIT_MS = 50;
const FRAME_TRIES = 50;
const SETTLE_MS = 300;

/**
 * The viewport as WebKit's compositor shows it, a screencast frame (JPEG): Playwright's `page.screenshot()` in WebKit on
 * Linux paints in software and flattens a CSS perspective (no divide, Playwright #21620, WebKit bug 68276), so a shot of
 * the tilted table must come from the compositor. A frame arrives only when something paints, so a 1px element
 * nudges one.
 */
export async function compositorShot(page: Page): Promise<Buffer> {
    const viewport = page.viewportSize();
    if (viewport === null) {
        throw new Error("a compositor shot needs a viewport");
    }
    const scale = await page.evaluate(() => window.devicePixelRatio);
    let latest: Buffer | null = null;
    let started = false;
    await page.screencast.start({
        onFrame: (frame) => {
            if (started) {
                latest = frame.data;
            }
        },
        quality: 100,
        size: {
            height: Math.round(viewport.height * scale),
            width: Math.round(viewport.width * scale),
        },
    });
    started = true;
    await page.evaluate(() => {
        const nudge = document.createElement("div");
        nudge.style.cssText =
            "position:fixed;left:0;top:0;width:1px;height:1px;opacity:0.01;pointer-events:none";
        document.documentElement.append(nudge);
        requestAnimationFrame(() => requestAnimationFrame(() => nudge.remove()));
    });
    function arrived(): boolean {
        return latest !== null;
    }
    for (let tries = 0; tries < FRAME_TRIES && !arrived(); tries += 1) {
        await page.waitForTimeout(FRAME_WAIT_MS);
    }
    await page.waitForTimeout(SETTLE_MS);
    await page.screencast.stop();
    if (latest === null) {
        throw new Error("no screencast frame arrived");
    }
    return latest;
}
