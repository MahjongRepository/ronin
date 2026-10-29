import { type TemplateResult, html, nothing } from "lit-html";

interface DropdownItem {
    /** Whether this item is highlighted as current */
    isCurrent: boolean;
    /** Text shown in the dropdown entry */
    label: string;
    /** Action step index to jump to */
    stepIndex: number;
}

interface DropdownSelectProps {
    isOpen: boolean;
    items: DropdownItem[];
    onSelect: (stepIndex: number) => void;
    onToggle: () => void;
    triggerLabel: string;
}

/**
 * Stateless dropdown select component. Renders a trigger button that toggles
 * the panel, and a list of selectable items when open. The caller owns all
 * state (open/closed, current item) and provides callbacks for interaction.
 */
function DropdownSelect(props: DropdownSelectProps): TemplateResult {
    const { isOpen, items, onSelect, onToggle, triggerLabel } = props;

    return html`<div class="dropdown-select">
        <button class="dropdown-select__trigger" @click=${onToggle}>${triggerLabel}</button>
        ${
            isOpen
                ? html`<div class="dropdown-select__panel">
                  ${items.map(
                      (item) => html`<button
                          class="dropdown-select__item${item.isCurrent ? " dropdown-select__item--current" : ""}"
                          @click=${() => onSelect(item.stepIndex)}
                      >
                          ${item.label}
                      </button>`,
                  )}
              </div>`
                : nothing
        }
    </div>`;
}

export { DropdownSelect };
export type { DropdownItem, DropdownSelectProps };
