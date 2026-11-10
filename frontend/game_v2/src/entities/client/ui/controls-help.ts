import { type TemplateResult, html } from "lit-html";

import { type PlayCommand } from "@/entities/client/model/play-ui";
import { PANEL_CONTROL_FOCUS_KEY } from "@/entities/table";
import { type MessageKey, t } from "@/shared/i18n";
import { focusOnFirstRender, keepTabInside } from "@/shared/ui";

const CLOSE: PlayCommand = { kind: "close_controls" };

interface KeyRow {
    readonly key: MessageKey;
    readonly action: MessageKey;
}

const KEY_ROWS: readonly KeyRow[] = [
    { action: "game.help.tile_action", key: "game.help.tile_key" },
    { action: "game.help.arrows_action", key: "game.help.arrows_key" },
    { action: "game.help.activate_action", key: "game.help.activate_key" },
    { action: "game.help.digits_action", key: "game.help.digits_key" },
    { action: "game.help.escape_action", key: "game.help.escape_key" },
];

const RIGHT_CLICK_ROW: KeyRow = {
    action: "game.help.right_click_action",
    key: "game.help.right_click_key",
};

/**
 * The keyboard and mouse controls over the board, opened from the settings menu: each key beside what it does
 * (right-click only while its shortcuts are on), then how offers are declined. Modal while the
 * page makes the rest inert: Close takes the focus, Tab stays on it, and Escape closes.
 */
export function ControlsHelp(
    rightClick: boolean,
    onCommand: (command: PlayCommand) => void,
): TemplateResult {
    function onKeydown(event: KeyboardEvent): void {
        if (event.key === "Tab") {
            keepTabInside(event);
            return;
        }
        if (event.key === "Escape") {
            event.preventDefault();
            onCommand(CLOSE);
        }
    }
    const rows = rightClick ? [...KEY_ROWS, RIGHT_CLICK_ROW] : KEY_ROWS;
    return html`<div
        class="controls-help"
        role="dialog"
        aria-modal="true"
        aria-label=${t("game.help.title")}
        @keydown=${onKeydown}
    >
        <p class="controls-help__title">${t("game.help.title")}</p>
        <dl class="controls-help__keys">
            ${rows.map(
                (row) => html`<div class="controls-help__row">
                    <dt><span class="controls-help__key">${t(row.key)}</span></dt>
                    <dd>${t(row.action)}</dd>
                </div>`,
            )}
        </dl>
        <p class="controls-help__note">${t("game.help.decline", {
            pass: t("game.button.pass"),
            ron: t("game.call.ron"),
            tsumo: t("game.call.tsumo"),
        })}</p>
        <button type="button" data-focus-key=${PANEL_CONTROL_FOCUS_KEY} class="secondary controls-help__close" ${focusOnFirstRender()} @click=${() => onCommand(CLOSE)}>
            ${t("common.close")}
        </button>
    </div>`;
}
