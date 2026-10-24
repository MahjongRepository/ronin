import { type TemplateResult, render } from "lit-html";
import { describe, expect, test, vi } from "vitest";

import { type DropdownItem, DropdownSelect } from "@/entities/table/ui/dropdown-select";

function renderTo(template: TemplateResult): HTMLElement {
    const el = document.createElement("div");
    render(template, el);
    return el;
}

function makeItems(count: number, currentIndex = -1): DropdownItem[] {
    const items: DropdownItem[] = [];
    for (let idx = 0; idx < count; idx++) {
        items.push({
            isCurrent: idx === currentIndex,
            label: `Item ${idx + 1}`,
            stepIndex: idx * 10,
        });
    }
    return items;
}

function renderDropdown(
    overrides: {
        isOpen?: boolean;
        items?: DropdownItem[];
        onSelect?: (stepIndex: number) => void;
        onToggle?: () => void;
        triggerLabel?: string;
    } = {},
): HTMLElement {
    return renderTo(
        DropdownSelect({
            isOpen: overrides.isOpen ?? false,
            items: overrides.items ?? makeItems(3),
            onSelect: overrides.onSelect ?? vi.fn(),
            onToggle: overrides.onToggle ?? vi.fn(),
            triggerLabel: overrides.triggerLabel ?? "Rounds",
        }),
    );
}

describe("DropdownSelect", () => {
    describe("trigger button", () => {
        test("renders trigger with correct label", () => {
            const el = renderDropdown({ triggerLabel: "East 2" });
            const trigger = el.querySelector(".dropdown-select__trigger");
            expect(trigger?.textContent).toBe("East 2");
        });

        test("calls onToggle when trigger is clicked", () => {
            const onToggle = vi.fn();
            const el = renderDropdown({ onToggle });
            const trigger = el.querySelector<HTMLButtonElement>(".dropdown-select__trigger");
            trigger?.click();
            expect(onToggle).toHaveBeenCalledOnce();
        });
    });

    describe("panel visibility", () => {
        test("does not render panel when closed", () => {
            const el = renderDropdown({ isOpen: false });
            expect(el.querySelector(".dropdown-select__panel")).toBeNull();
        });

        test("renders panel with items when open", () => {
            const el = renderDropdown({ isOpen: true });
            const panel = el.querySelector(".dropdown-select__panel");
            expect(panel).not.toBeNull();
            const items = panel?.querySelectorAll(".dropdown-select__item");
            expect(items).toHaveLength(3);
        });
    });

    describe("item rendering", () => {
        test("renders item labels", () => {
            const el = renderDropdown({ isOpen: true, items: makeItems(2) });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items[0]?.textContent?.trim()).toBe("Item 1");
            expect(items[1]?.textContent?.trim()).toBe("Item 2");
        });

        test("highlights current item", () => {
            const el = renderDropdown({ isOpen: true, items: makeItems(3, 1) });
            const items = el.querySelectorAll(".dropdown-select__item");
            expect(items[0]?.classList.contains("dropdown-select__item--current")).toBe(false);
            expect(items[1]?.classList.contains("dropdown-select__item--current")).toBe(true);
            expect(items[2]?.classList.contains("dropdown-select__item--current")).toBe(false);
        });

        test("calls onSelect with correct stepIndex when item is clicked", () => {
            const onSelect = vi.fn();
            const el = renderDropdown({ isOpen: true, onSelect });
            const items = el.querySelectorAll<HTMLButtonElement>(".dropdown-select__item");
            items[1]?.click();
            expect(onSelect).toHaveBeenCalledWith(10);
        });

        test("calls onSelect with first item stepIndex", () => {
            const onSelect = vi.fn();
            const el = renderDropdown({ isOpen: true, onSelect });
            const items = el.querySelectorAll<HTMLButtonElement>(".dropdown-select__item");
            items[0]?.click();
            expect(onSelect).toHaveBeenCalledWith(0);
        });
    });

    describe("empty items", () => {
        test("renders empty panel when open with no items", () => {
            const el = renderDropdown({ isOpen: true, items: [] });
            const panel = el.querySelector(".dropdown-select__panel");
            expect(panel).not.toBeNull();
            expect(panel?.querySelectorAll(".dropdown-select__item")).toHaveLength(0);
        });
    });
});
