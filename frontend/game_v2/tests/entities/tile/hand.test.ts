import { type TemplateResult, render } from "lit-html";
import { describe, expect, test, vi } from "vitest";

import { Hand, type HandTile } from "@/entities/tile";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

describe("Hand", () => {
    test("draws known faces from the sprite, backs and concealed tiles as backs, the drawn tile apart", () => {
        const tiles: HandTile[] = [
            { face: "1m", show: "face" },
            { face: "2m", show: "back" },
            { show: "concealed" },
        ];
        const el = renderTo(Hand({ drawnTile: { face: "9m", show: "face" }, tiles }));

        const slots = [...el.querySelectorAll(".hand > .hand-tile")];
        expect(slots.map((slot) => slot.querySelector("use") !== null)).toEqual([
            true,
            false,
            false,
            true,
        ]);
        expect(el.querySelectorAll(".hand-tile .tile-back")).toHaveLength(2);
        expect(slots.at(-1)?.classList.contains("hand-drawn-gap")).toBe(true);
    });

    test("makes a selectable tile a named button that reports its tile id when pressed", () => {
        const onTile = vi.fn();
        const el = renderTo(
            Hand({
                onTile,
                tileAction: "Discard",
                tiles: [{ face: "5p", show: "face", state: "selectable", tileId: 53 }],
            }),
        );
        const button = el.querySelector("button.hand-tile");

        expect(button?.getAttribute("aria-label")).toBe("Discard 5p");
        expect(button?.getAttribute("type")).toBe("button");
        button?.dispatchEvent(new MouseEvent("click"));
        expect(onTile).toHaveBeenCalledExactlyOnceWith(53);
    });

    test("keeps a disabled, selected or waiting tile a focusable button that says so and reports nothing", () => {
        const onTile = vi.fn();
        const tiles: HandTile[] = [
            { face: "2m", show: "face", state: "disabled", tileId: 4 },
            { face: "3m", show: "face", state: "selected", tileId: 8 },
            { face: "4m", show: "face", state: "waiting", tileId: 12 },
        ];
        const el = renderTo(Hand({ onTile, tiles }));

        const buttons = [...el.querySelectorAll("button")];
        for (const button of buttons) {
            button.dispatchEvent(new MouseEvent("click"));
        }
        expect(
            buttons.map((button) => [button.disabled, button.getAttribute("aria-disabled")]),
        ).toEqual([
            [false, "true"],
            [false, "true"],
            [false, "true"],
        ]);
        expect(buttons.map((button) => button.getAttribute("aria-pressed"))).toEqual([
            null,
            "true",
            null,
        ]);
        expect(onTile).not.toHaveBeenCalled();
    });
});
