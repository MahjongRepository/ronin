import { chromium } from "playwright";

const FACE_WIDTH = 300;
const FACE_HEIGHT = 400;
const RASTER_SCALE = 2;

/**
 * The symbol viewport of a face whose ink is centred across at `inkCentreX`, shifted so that centre lands on the
 * viewport's middle. A blank face (null) keeps the unshifted viewport.
 */
function faceViewBox(inkCentreX: number | null): string {
    const shift = inkCentreX === null ? 0 : Math.round((inkCentreX - FACE_WIDTH / 2) * 100) / 100;
    return `${shift} 0 ${FACE_WIDTH} ${FACE_HEIGHT}`;
}

/**
 * Measure where each face's ink weighs across, rasterised over white in a headless browser: the centre of its
 * darkness, null for a face that draws nothing. A glyph's heavy strokes, not its outermost tips, set where it reads
 * as centred.
 */
async function measureInkCentresX(faces: readonly string[]): Promise<readonly (number | null)[]> {
    const browser = await chromium.launch();
    try {
        const page = await browser.newPage();
        return await page.evaluate(
            async ({ inners, height, scale, width }) => {
                const canvas = document.createElement("canvas");
                canvas.width = width * scale;
                canvas.height = height * scale;
                const context = canvas.getContext("2d", { willReadFrequently: true });
                if (context === null) {
                    throw new Error("no 2d canvas context to weigh the faces' ink");
                }
                const centres: (number | null)[] = [];
                for (const inner of inners) {
                    const markup = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${inner}</svg>`;
                    const image = new Image();
                    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
                    await image.decode();
                    context.fillStyle = "#fff";
                    context.fillRect(0, 0, canvas.width, canvas.height);
                    context.drawImage(image, 0, 0, canvas.width, canvas.height);
                    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
                    let total = 0;
                    let moment = 0;
                    for (let index = 0; index < data.length; index += 4) {
                        const darkness = 765 - data[index] - data[index + 1] - data[index + 2];
                        total += darkness;
                        moment += darkness * (((index / 4) % canvas.width) + 0.5);
                    }
                    centres.push(total === 0 ? null : moment / total / scale);
                }
                return centres;
            },
            { height: FACE_HEIGHT, inners: faces, scale: RASTER_SCALE, width: FACE_WIDTH },
        );
    } finally {
        await browser.close();
    }
}

export { faceViewBox, measureInkCentresX };
