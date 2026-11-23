import { type TemplateResult, html, nothing, svg } from "lit-html";

import { LANGUAGE_NAMES, LOCALES, type Locale, pageLocale } from "./locale";
import { t } from "./shared-i18n";
import { pageTileLabels } from "./tile-labels";
import {
    WIND_LETTERS,
    WIND_SCRIPT_LANGS,
    type WindScript,
    pageWindScript,
    windScriptsOf,
} from "./winds";

export interface SwitchRowProps {
    readonly on: boolean;
    readonly onToggle: () => void;
}

export interface InputRowsProps {
    readonly rightClick: boolean;
    readonly onToggle: () => void;
    readonly keyHints: boolean;
    readonly onToggleKeyHints: () => void;
}

const WIND_SCRIPT_NAMES = {
    cyrillic: "settings.winds.cyrillic",
    kanji: "settings.winds.kanji",
    latin: "settings.winds.latin",
} as const satisfies Readonly<Record<WindScript, string>>;

function onOff(on: boolean): string {
    return t(on ? "settings.on" : "settings.off");
}

function SwitchValue(block: string, on: boolean): TemplateResult {
    return html`<span class="${block}__item-value ${block}__switch-value" data-reserve=${onOff(!on)}
        ><span>${onOff(on)}</span></span
    >`;
}

function SoundIcon(block: string, on: boolean): TemplateResult {
    return html`<svg
        class="${block}__icon"
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <path d="M2.5 6h2.5l3.5-3v10l-3.5-3h-2.5z" />
        ${
            on
                ? svg`<path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.5a6 6 0 0 1 0 9" />`
                : svg`<path d="M11 6l3.5 4M14.5 6l-3.5 4" />`
        }
    </svg>`;
}

export function SoundRow(block: string, sound: SwitchRowProps): TemplateResult {
    return html`<button
                type="button"
                class="secondary ${block}__item ${block}__sound"
                role="switch"
                aria-checked=${sound.on ? "true" : "false"}
                @click=${sound.onToggle}
            >
                ${SoundIcon(block, sound.on)}<span class="${block}__item-name">${t("settings.sound")}</span
                >${SwitchValue(block, sound.on)}
            </button>`;
}

export function AnimationsRow(block: string, animations: SwitchRowProps): TemplateResult {
    return html`<button
                type="button"
                class="secondary ${block}__item ${block}__animations"
                role="switch"
                aria-checked=${animations.on ? "true" : "false"}
                @click=${animations.onToggle}
            >
                <span class="${block}__item-name">${t("settings.animations")}</span
                >${SwitchValue(block, animations.on)}
            </button>`;
}

export function DiscardSlideRow(block: string, slide: SwitchRowProps): TemplateResult {
    return html`<button
        type="button"
        class="secondary ${block}__item ${block}__discard-slide"
        role="switch"
        aria-checked=${String(slide.on)}
        @click=${slide.onToggle}
    ><span class="${block}__item-name">${t("settings.discard_slide")}</span
        >${SwitchValue(block, slide.on)}</button>`;
}

export function TileLabelsRow(block: string, onTileLabels: (on: boolean) => void): TemplateResult {
    const on = pageTileLabels() !== null;
    return html`<button
        type="button"
        class="secondary ${block}__item ${block}__tile-labels"
        role="switch"
        aria-checked=${String(on)}
        @click=${() => onTileLabels(!on)}
    ><span class="${block}__item-name">${t("settings.tile_labels")}</span
        >${SwitchValue(block, on)}</button>`;
}

export function KeepAutoWinRow(block: string, keep: SwitchRowProps): TemplateResult {
    return html`<button
        type="button"
        class="secondary ${block}__item ${block}__keep-auto-win"
        role="switch"
        aria-checked=${String(keep.on)}
        @click=${keep.onToggle}
    ><span class="${block}__item-name">${t("settings.keep_auto_win")}</span
        >${SwitchValue(block, keep.on)}</button>`;
}

export function InputRows(block: string, input: InputRowsProps): TemplateResult {
    return html`<button
        type="button"
            class="secondary ${block}__item ${block}__right-click"
        role="switch"
        aria-checked=${String(input.rightClick)}
        @click=${input.onToggle}
    ><span class="${block}__item-name">${t("settings.right_click")}</span
        >${SwitchValue(block, input.rightClick)}</button>
        <button
            type="button"
            class="secondary ${block}__item ${block}__key-hints"
            role="switch"
            aria-checked=${String(input.keyHints)}
            @click=${input.onToggleKeyHints}
        ><span class="${block}__item-name">${t("settings.key_hints")}</span
            >${SwitchValue(block, input.keyHints)}</button>`;
}

export function LanguageRow(block: string, onLanguage: (locale: Locale) => void): TemplateResult {
    const current = pageLocale();
    return html`<div class="${block}__item ${block}__language" role="group" aria-label=${t("settings.language")}>
        <span class="${block}__item-name" aria-hidden="true">${t("settings.language")}</span>
        <span class="${block}__languages">${LOCALES.map(
            (locale) => html`<button
                type="button"
                class="secondary ${block}__language-option"
                lang=${locale}
                aria-current=${locale === current ? "true" : nothing}
                @click=${() => onLanguage(locale)}
            >${LANGUAGE_NAMES[locale]}</button>`,
        )}</span>
    </div>`;
}

export function WindsRow(block: string, onWinds: (script: WindScript) => void): TemplateResult {
    const current = pageWindScript();
    return html`<div class="${block}__item ${block}__language ${block}__winds" role="group" aria-label=${t("settings.winds")}>
        <span class="${block}__item-name" aria-hidden="true">${t("settings.winds")}</span>
        <span class="${block}__languages">${windScriptsOf(pageLocale()).map(
            (script) => html`<button
                type="button"
                class="secondary ${block}__language-option ${block}__winds-option"
                lang=${WIND_SCRIPT_LANGS[script]}
                data-script=${script}
                aria-label=${t(WIND_SCRIPT_NAMES[script])}
                aria-current=${script === current ? "true" : nothing}
                @click=${() => onWinds(script)}
            >${WIND_LETTERS[script].join("")}</button>`,
        )}</span>
    </div>`;
}
