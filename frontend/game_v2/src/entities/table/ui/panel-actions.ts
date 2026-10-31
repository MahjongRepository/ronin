import { type TemplateResult, html, nothing } from "lit-html";

/** A way on from a panel: a link to another page, or a control of the view's own. */
export type PanelAction =
    | {
          readonly kind: "link";
          readonly label: string;
          readonly href: string;
          readonly primary?: boolean;
      }
    | {
          readonly kind: "button";
          readonly label: string;
          readonly onClick: () => void;
          readonly primary?: boolean;
      };

function PanelActionView(action: PanelAction): TemplateResult {
    const classes = `seating__action${action.primary === true ? "" : " secondary"}`;
    if (action.kind === "link") {
        return html`<a class=${classes} role="button" href=${action.href}>${action.label}</a>`;
    }
    return html`<button type="button" class=${classes} @click=${action.onClick}>${action.label}</button>`;
}

/** A panel's ways on, in order; the one marked primary is its primary action. */
export function PanelActions(actions: readonly PanelAction[]): TemplateResult | typeof nothing {
    if (actions.length === 0) {
        return nothing;
    }
    return html`<div class="seating__actions">${actions.map(PanelActionView)}</div>`;
}
