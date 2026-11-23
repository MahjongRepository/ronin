import { type Locale } from "@ronin/shared/locale";
import {
    AnimationsRow,
    DiscardSlideRow,
    InputRows,
    type InputRowsProps,
    KeepAutoWinRow,
    LanguageRow,
    SoundRow,
    type SwitchRowProps,
    TileLabelsRow,
    WindsRow,
} from "@ronin/shared/settings-rows";
import { type WindScript } from "@ronin/shared/winds";
import { type TemplateResult, html, type nothing, render } from "lit-html";

import { type MessageKey, t } from "@/i18n";

export const SETTINGS_TABS = ["game", "api"] as const;

export type SettingsTab = (typeof SETTINGS_TABS)[number];

export interface SettingsTabs {
    readonly api: TemplateResult | typeof nothing;
    readonly current: SettingsTab;
    readonly onSelect: (tab: SettingsTab) => void;
}

export interface SettingsProps {
    readonly tabs: SettingsTabs | null;
    readonly animations: SwitchRowProps;
    readonly discardSlide: SwitchRowProps;
    readonly input: InputRowsProps;
    readonly keepAutoWin: SwitchRowProps;
    readonly onLanguage: (locale: Locale) => void;
    readonly onTileLabels: (on: boolean) => void;
    readonly onWinds: (script: WindScript) => void;
    readonly sound: SwitchRowProps;
}

const BLOCK = "settings-page";

const TAB_LABELS: Record<SettingsTab, MessageKey> = {
    api: "settings.tab.api",
    game: "settings.tab.game",
};

function gameSettingsTemplate(props: SettingsProps): TemplateResult {
    return html`<div class="${BLOCK}__list">
        ${SoundRow(BLOCK, props.sound)} ${AnimationsRow(BLOCK, props.animations)}
        ${DiscardSlideRow(BLOCK, props.discardSlide)}
        ${TileLabelsRow(BLOCK, props.onTileLabels)} ${KeepAutoWinRow(BLOCK, props.keepAutoWin)}
        ${InputRows(BLOCK, props.input)} ${LanguageRow(BLOCK, props.onLanguage)}
        ${WindsRow(BLOCK, props.onWinds)}
    </div>`;
}

function tabsTemplate(tabs: SettingsTabs): TemplateResult {
    return html`<div class="lobby-tabs ${BLOCK}__tabs" role="tablist">
        ${SETTINGS_TABS.map(
            (tab) =>
                html`<button
                    type="button"
                    role="tab"
                    id="settings-tab-${tab}"
                    aria-controls="settings-panel"
                    aria-selected=${tab === tabs.current ? "true" : "false"}
                    @click=${() => tabs.onSelect(tab)}
                >
                    ${t(TAB_LABELS[tab])}
                </button>`,
        )}
    </div>`;
}

function panelTemplate(props: SettingsProps, tabs: SettingsTabs): TemplateResult {
    return html`<div
        class="${BLOCK}__panel"
        id="settings-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-${tabs.current}"
    >
        ${tabs.current === "api" ? tabs.api : gameSettingsTemplate(props)}
    </div>`;
}

function settingsTemplate(props: SettingsProps): TemplateResult {
    const { tabs } = props;
    return html`<section class="lobby-section ${BLOCK}">
        <div class="lobby-section-header">
            <h2>${t(tabs === null ? "nav.settings" : "settings.title")}</h2>
        </div>
        ${
            tabs === null
                ? gameSettingsTemplate(props)
                : html`${tabsTemplate(tabs)} ${panelTemplate(props, tabs)}`
        }
    </section>`;
}

export function renderSettings(host: HTMLElement, props: SettingsProps): void {
    document.title = t("page.title.with_page", { page: t("nav.settings") });
    render(settingsTemplate(props), host);
}
