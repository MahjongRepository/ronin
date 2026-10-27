import $ from "jquery";
import { afterEach, describe, expect, it, vi } from "vitest";

import Util from "../../vendor/majiang-ui/scale.js";

const TABLE_WIDTH = 800;
const TABLE_HEIGHT = 680;

const INSET = 8;
const GEAR = 40;
const CLEARANCE = INSET + GEAR + INSET;
const SWITCHES_HEIGHT = 32;
const SWITCHES_CLEARANCE = INSET + SWITCHES_HEIGHT + INSET;

function renderStage(
    top,
    viewportWidth,
    { switches = false, switchesWidth = GEAR, height = 0 } = {},
) {
    const stage = $(
        '<div id="board"><div class="board"></div><div class="controller"></div></div>',
    ).appendTo(document.body);
    stage[0].getBoundingClientRect = () => ({
        top,
        left: 0,
        right: viewportWidth,
        bottom: top + height,
    });
    stage.find(".controller")[0].getBoundingClientRect = () => ({
        left: viewportWidth - INSET - GEAR,
        right: viewportWidth - INSET,
        bottom: top + INSET + GEAR,
    });
    if (switches) {
        $('<div class="autoplay">').appendTo(stage)[0].getBoundingClientRect = () => ({
            left: INSET,
            right: INSET + switchesWidth,
            top: top + height - INSET - SWITCHES_HEIGHT,
        });
    }
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
    return { top: y, right: x + TABLE_WIDTH * scale, bottom: y + TABLE_HEIGHT * scale, scale };
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

    it("fits the table to the stage's own box, not the window, and leaves a stage not laid out yet alone", () => {
        const stage = renderStage(0, 1000, { height: 340 });
        setViewport(1920, 1120);
        vi.spyOn(stage[0], "clientWidth", "get").mockReturnValue(1000);
        const stageHeight = vi.spyOn(stage[0], "clientHeight", "get").mockReturnValue(340);

        Util.fitToStage(stage);
        expect(stage[0].style.height).toBe("");
        expect(stage.find(".board")[0].style.transform).toBe("translate(300px, 0px) scale(0.5)");

        stageHeight.mockReturnValue(0);
        Util.fitToStage(stage);
        expect(stage.find(".board")[0].style.transform).toBe("translate(300px, 0px) scale(0.5)");
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

    it("keeps a strip below the table for the corner switches beside the gear's above it, resting it on them on an upright touch screen", () => {
        const stage = renderStage(0, 800, { switches: true, height: 760 });
        setViewport(800, 760);
        const touchPortrait = vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false });

        Util.scale(stage);
        const centred = placedTable(stage);
        expect(centred.top).toBeGreaterThanOrEqual(CLEARANCE);
        expect(centred.bottom).toBeLessThanOrEqual(760 - SWITCHES_CLEARANCE + 1e-9);
        expect(centred.scale).toBeCloseTo((760 - CLEARANCE - SWITCHES_CLEARANCE) / 680);

        touchPortrait.mockReturnValue({ matches: true });
        stage[0].getBoundingClientRect = () => ({ top: 0, left: 0, right: 800, bottom: 2000 });
        stage.find(".autoplay")[0].getBoundingClientRect = () => ({
            left: INSET,
            right: INSET + GEAR,
            top: 2000 - INSET - SWITCHES_HEIGHT,
        });
        setViewport(800, 2000);
        Util.scale(stage);
        expect(placedTable(stage).bottom).toBeCloseTo(2000 - SWITCHES_CLEARANCE);
    });

    it("lets the corner switches cover the table's felt left of the left player's hand, narrowing it only past that", () => {
        const handMargin = 40;
        const renderLandscape = (switchesWidth) => {
            const stage = renderStage(0, 1000, { switches: true, switchesWidth, height: 680 });
            const table = stage.find(".board");
            table[0].getBoundingClientRect = () => ({ left: 0, width: TABLE_WIDTH });
            $('<div class="shoupai shangjia">').appendTo(table)[0].getBoundingClientRect = () => ({
                left: handMargin,
            });
            return stage;
        };
        setViewport(1000, 680);

        const fitting = renderLandscape(110);
        Util.scale(fitting);
        expect(placedTable(fitting).scale).toBe(1);

        document.body.innerHTML = "";
        const wider = renderLandscape(140);
        Util.scale(wider);
        const table = placedTable(wider);
        const handLeft = table.right - (TABLE_WIDTH - handMargin) * table.scale;
        expect(handLeft).toBeCloseTo(INSET + 140 + INSET);
    });
});
