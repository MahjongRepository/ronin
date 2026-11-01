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
    host = document.createElement("div");
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
        expect(element.style.getPropertyValue("--geo-rw")).toBe("");
        expect(observer.disconnected).toBe(false);

        observer.resize(1420, 880);

        expect(element.dataset.boardFamily).toBe("desktop");
        expect(element.style.getPropertyValue("--geo-rw")).toBe("42px");
    });

    it("rewrites the family and drops sizes it no longer has when the box crosses families", async () => {
        box = { height: 880, width: 1420 };
        const { element } = await renderBoard();

        latestObserver().resize(667, 375);

        expect(element.dataset).toMatchObject({ boardChrome: "small", boardFamily: "phone" });
        expect(element.style.getPropertyValue("--geo-rw")).toBe("");
    });

    it("keeps the written sizes through a re-render that adds the overlay", async () => {
        box = { height: 880, width: 1420 };
        const { element } = await renderBoard();

        await renderBoard(html`<p>Panel</p>`);

        expect(host.querySelector(".board-overlay")).not.toBeNull();
        expect(element.dataset.boardFamily).toBe("desktop");
        expect(element.style.getPropertyValue("--geo-rw")).toBe("42px");
    });

    it("stops observing a removed board and measures it again once it is back", async () => {
        box = { height: 880, width: 1420 };
        const { element, part } = await renderBoard();
        const first = latestObserver();

        part.setConnected(false);
        box = { height: 780, width: 1420 };
        part.setConnected(true);

        expect(first.disconnected).toBe(true);
        expect(latestObserver()).not.toBe(first);
        expect(latestObserver().observed).toEqual([element]);
        expect(element.style.getPropertyValue("--geo-rw")).toBe("36px");
    });
});
