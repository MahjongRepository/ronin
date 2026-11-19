import { type Locale } from "@ronin/shared/locale";
import {
    AnimationsRow,
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
import { type TemplateResult, html, render } from "lit-html";

import { t } from "@/i18n";

export interface SettingsProps {
    readonly animations: SwitchRowProps;
    readonly input: InputRowsProps;
    readonly keepAutoWin: SwitchRowProps;
    readonly onLanguage: (locale: Locale) => void;
    readonly onTileLabels: (on: boolean) => void;
    readonly onWinds: (script: WindScript) => void;
    readonly sound: SwitchRowProps;
}

const BLOCK = "settings-page";

function settingsTemplate(props: SettingsProps): TemplateResult {
    return html`<section class="lobby-section ${BLOCK}">
        <div class="lobby-section-header">
            <h2>${t("nav.settings")}</h2>
        </div>
        <div class="${BLOCK}__list">
            ${SoundRow(BLOCK, props.sound)} ${AnimationsRow(BLOCK, props.animations)}
            ${TileLabelsRow(BLOCK, props.onTileLabels)} ${KeepAutoWinRow(BLOCK, props.keepAutoWin)}
            ${InputRows(BLOCK, props.input)} ${LanguageRow(BLOCK, props.onLanguage)}
            ${WindsRow(BLOCK, props.onWinds)}
        </div>
    </section>`;
}

export function renderSettings(host: HTMLElement, props: SettingsProps): void {
    document.title = t("page.title.with_page", { page: t("nav.settings") });
    render(settingsTemplate(props), host);
}
