import $ from "jquery";
import { afterEach, describe, expect, it, vi } from "vitest";

import Util from "../../vendor/majiang-ui/scale.js";

const TABLE_WIDTH = 800;
const TABLE_HEIGHT = 680;

const INSET = 8;
const GEAR = 40;
const CLEARANCE = INSET + GEAR + INSET;

function renderStage(top, viewportWidth) {
    const stage = $(
        '<div id="board"><div class="board"></div><div class="controller"></div></div>',
    ).appendTo(document.body);
    stage[0].getBoundingClientRect = () => ({ top, right: viewportWidth });
    stage.find(".controller")[0].getBoundingClientRect = () => ({
        left: viewportWidth - INSET - GEAR,
        right: viewportWidth - INSET,
        bottom: top + INSET + GEAR,
    });
    const table = stage.find(".board")[0];
    vi.spyOn(table, "offsetWidth", "get").mockReturnValue(TABLE_WIDTH);
    vi.spyOn(table, "offsetHeight", "get").mockReturnValue(TABLE_HEIGHT);
    return stage;
}

function placedTable(stage) {
    const [, x, y, scale] = stage
        .find(".board")[0]
        .style.transform.match(/translate\(([\d.]+)px, ([\d.]+)px\) scale\(([\d.]+)\)/)
        .map(Number);
    return { top: y, right: x + TABLE_WIDTH * scale, scale };
}

function setViewport(width, height) {
    vi.spyOn(document.documentElement, "clientWidth", "get").mockReturnValue(width);
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(height);
}

afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
});

describe("Majiang.UI.Util.scale", () => {
    it("stretches the stage below what sits above it and enlarges the table to its height, centred across", () => {
        const stage = renderStage(100, 1920);
        setViewport(1920, 1120);

        Util.scale(stage);
        Util.scale(stage);

        expect(stage[0].style.height).toBe("1020px");
        expect(stage.find(".board")[0].style.transform).toBe("translate(360px, 0px) scale(1.5)");
    });

    it("centres a width-limited table on a desktop, and rests it on the bottom edge on an upright touch screen", () => {
        const stage = renderStage(0, 1000);
        setViewport(1000, 2000);
        const touchPortrait = vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false });

        Util.scale(stage);
        expect(stage.find(".board")[0].style.transform).toBe("translate(0px, 575px) scale(1.25)");

        touchPortrait.mockReturnValue({ matches: true });
        Util.scale(stage);
        expect(stage.find(".board")[0].style.transform).toBe("translate(0px, 1150px) scale(1.25)");
    });

    it("drops the table below the corner gear when that keeps it larger than narrowing it beside the gear", () => {
        const stage = renderStage(0, 800);
        setViewport(800, 704);

        Util.scale(stage);

        const table = placedTable(stage);
        expect(table.top).toBeGreaterThanOrEqual(CLEARANCE);
        expect(table.scale).toBeCloseTo((704 - CLEARANCE) / 680);
    });

    it("narrows the table to leave side felt for the gear when that keeps it larger than a strip above", () => {
        const stage = renderStage(0, 800);
        setViewport(800, 620);

        Util.scale(stage);

        const table = placedTable(stage);
        expect(table.right).toBeLessThanOrEqual(800 - CLEARANCE + 1e-9);
        expect(table.scale).toBeCloseTo((800 - 2 * CLEARANCE) / 800);
    });
});
