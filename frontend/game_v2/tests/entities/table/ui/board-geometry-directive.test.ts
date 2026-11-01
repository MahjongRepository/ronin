import { type RootPart, type TemplateResult, html, render } from "lit-html";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GameBoard } from "@/entities/table/ui/game-board";

class FakeObserver implements ResizeObserver {
    static readonly all: FakeObserver[] = [];
    readonly observed: Element[] = [];
    disconnected = false;

    constructor(private readonly callback: ResizeObserverCallback) {
        FakeObserver.all.push(this);
    }

    observe(target: Element): void {
        this.observed.push(target);
    }

    unobserve(): void {
        throw new Error("the board is never unobserved");
    }

    disconnect(): void {
        this.disconnected = true;
    }

    resize(width: number, height: number): void {
        const [target] = this.observed;
        if (target === undefined) {
            throw new Error("nothing is observed");
        }
        const entry: ResizeObserverEntry = {
            borderBoxSize: [],
            contentBoxSize: [],
            contentRect: DOMRect.fromRect({ height, width }),
            devicePixelContentBoxSize: [],
            target,
        };
        this.callback([entry], this);
    }
}

let box = { height: 0, width: 0 };
const frames = new Map<number, FrameRequestCallback>();
let lastFrame = 0;
let host = document.createElement("div");

function board(overlay?: TemplateResult): TemplateResult {
    return GameBoard({
        debug: false,
        overlay,
        platePress: { kind: "pin", onPin: vi.fn(), pinned: null },
        state: null,
    });
}

async function renderBoard(
    overlay?: TemplateResult,
): Promise<{ element: HTMLElement; part: RootPart }> {
    const part = render(board(overlay), host);
    const element = host.querySelector<HTMLElement>(".game-board");
    if (element === null) {
        throw new Error("no board rendered");
    }
    element.getBoundingClientRect = () => DOMRect.fromRect(box);
    await Promise.resolve();
    return { element, part };
}

function written(element: HTMLElement): Record<string, string | undefined> {
    return {
        chrome: element.dataset.boardChrome,
        family: element.dataset.boardFamily,
        rw: element.style.getPropertyValue("--geo-rw"),
    };
}

function nextFrame(): void {
    const due = [...frames.values()];
    frames.clear();
    for (const frame of due) {
        frame(0);
    }
}

function latestObserver(): FakeObserver {
    const observer = FakeObserver.all.at(-1);
    if (observer === undefined) {
        throw new Error("nothing observes the board");
    }
    return observer;
}

beforeEach(() => {
    FakeObserver.all.length = 0;
    vi.stubGlobal("ResizeObserver", FakeObserver);
    frames.clear();
    vi.stubGlobal("requestAnimationFrame", (frame: FrameRequestCallback) => {
        lastFrame += 1;
        frames.set(lastFrame, frame);
        return lastFrame;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
    host = document.createElement("div");
    host.className = "board-page";
    host.style.setProperty("--page-gutter", "10px");
    document.body.append(host);
});

afterEach(() => {
    render(html``, host);
    host.remove();
    vi.unstubAllGlobals();
});

describe("sizeBoard", () => {
    it("writes the board's family, chrome and sizes once its first render is in the document", async () => {
        box = { height: 880, width: 1420 };

        const { element } = await renderBoard();

        expect(element.dataset).toMatchObject({ boardChrome: "regular", boardFamily: "desktop" });
        expect(element.style.getPropertyValue("--geo-rw")).toBe("42px");
    });

    it("writes nothing for an empty box and sizes the board once it shows", async () => {
        box = { height: 0, width: 0 };
        const { element } = await renderBoard();
        const observer = latestObserver();

        observer.resize(0, 0);

        expect(element.dataset.boardFamily).toBeUndefined();
        expect([element.style.getPropertyValue("--geo-rw"), observer.disconnected]).toEqual([
            "",
            false,
        ]);

        observer.resize(1420, 880);

        expect(element.dataset.boardFamily).toBe("desktop");
        expect(element.style.getPropertyValue("--geo-rw")).toBe("42px");
    });

    it("writes a change keeping the gutter at once and one moving it in the next frame, dropping sizes it lost", async () => {
        box = { height: 880, width: 1420 };
        const { element } = await renderBoard();

        latestObserver().resize(647, 355);

        expect(written(element)).toEqual({ chrome: "regular", family: "desktop", rw: "42px" });

        nextFrame();

        expect(written(element)).toEqual({ chrome: "small", family: "phone", rw: "17px" });
        expect(element.style.getPropertyValue("--geo-band-shift")).toBe("0px");

        latestObserver().resize(1420, 700);

        expect(written(element)).toEqual({
            chrome: "regular",
            family: "short-desktop",
            rw: "34px",
        });
        expect(element.style.getPropertyValue("--geo-band-shift")).toBe("");
    });

    it("keeps the written sizes through a re-render that adds the overlay", async () => {
        box = { height: 880, width: 1420 };
        const { element } = await renderBoard();

        await renderBoard(html`<p>Panel</p>`);

        expect(host.querySelector(".board-overlay")).not.toBeNull();
        expect(host.querySelector(".game-board")).toBe(element);
        expect(element.dataset.boardFamily).toBe("desktop");
        expect(element.style.getPropertyValue("--geo-rw")).toBe("42px");
    });

    it("stops observing a removed board, even through a re-render, and measures it again once it is back", async () => {
        box = { height: 880, width: 1420 };
        const { element, part } = await renderBoard();
        const first = latestObserver();

        part.setConnected(false);
        box = { height: 780, width: 1420 };
        await renderBoard();

        expect(FakeObserver.all).toEqual([first]);

        part.setConnected(true);

        expect(
            FakeObserver.all.map(({ disconnected, observed }) => ({ disconnected, observed })),
        ).toEqual([
            { disconnected: true, observed: [element] },
            { disconnected: false, observed: [element] },
        ]);
        expect(element.style.getPropertyValue("--geo-rw")).toBe("36px");
    });
});
