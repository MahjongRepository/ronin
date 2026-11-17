import { type TemplateResult, html, nothing } from "lit-html";

import { t } from "@/shared/i18n";
import { type ShortcutKeys } from "@/shared/lib";

import { REPLAY_TOOLS_ID } from "./replay-controls";

export interface ReplayToolsProps {
    /** Whether a hand shows to copy or analyse: none under the seating. */
    readonly showsHand: boolean;
    readonly hideHands: boolean;
    /** Whose shortcut names the menu shows: Apple's ⌘ or the others' Ctrl. */
    readonly shortcuts: ShortcutKeys;
    readonly showTsumogiri: boolean;
    readonly onCopyHand: () => void;
    readonly onAnalyzeHand: () => void;
    readonly onToggleHands: () => void;
    readonly onToggleTsumogiri: () => void;
    readonly onClose: () => void;
}

/** The focus key the menu's first item that can act renders, so the page focuses it as the menu opens. */
export const TOOLS_FIRST_FOCUS_KEY = "replay-tools-first";

/** What the tools' menu renders, so a click inside it is told from one outside that closes it. */
export const TOOLS_SELECTOR = "[data-replay-tools]";

/** Escape closes the menu and goes no further; every other key stays the page's. */
function onToolsKeydown(event: KeyboardEvent, onClose: () => void): void {
    if (event.key !== "Escape") {
        return;
    }
    event.preventDefault();
    event.stopPropagation();
    onClose();
}

/** A tool's keys: shown at its row's end on a screen with a keyboard, named for assistive technology. */
interface ToolKeys {
    readonly shown: string;
    readonly aria: string;
}

/** The copy's keys in each convention. */
const COPY_KEYS: Readonly<Record<ShortcutKeys, ToolKeys>> = {
    apple: { aria: "Meta+C", shown: "⌘C" },
    other: { aria: "Control+C", shown: "Ctrl+C" },
};
const ANALYZE_KEYS: ToolKeys = { aria: "A", shown: "A" };
const HANDS_KEYS: ToolKeys = { aria: "H", shown: "H" };

function KeyHint(keys: ToolKeys | null): TemplateResult | typeof nothing {
    return keys === null
        ? nothing
        : html`<span class="replay-tools__key" aria-hidden="true">${keys.shown}</span>`;
}

function onOff(on: boolean): string {
    return t(on ? "game.settings.on" : "game.settings.off");
}

interface ToolSwitchProps {
    readonly kind: string;
    readonly label: string;
    readonly on: boolean;
    readonly onToggle: () => void;
    readonly focusKey: string | null;
    readonly keys: ToolKeys | null;
}

/** A switch of the menu, its key and state at its row's end. */
function ToolSwitch({
    focusKey,
    keys,
    kind,
    label,
    on,
    onToggle,
}: ToolSwitchProps): TemplateResult {
    return html`<button
        type="button"
        class="secondary replay-tools__item replay-tools__${kind}"
        role="switch"
        aria-checked=${String(on)}
        aria-keyshortcuts=${keys?.aria ?? nothing}
        data-focus-key=${focusKey ?? nothing}
        @click=${onToggle}
    >
        <span>${label}</span
        ><span class="replay-tools__end">${KeyHint(keys)}<span class="replay-tools__value">${onOff(on)}</span></span>
    </button>`;
}

/**
 * The replay's tools by the options, a menu that stays open while its switches turn: the bottom seat's closed hand
 * copied (Ctrl+C or Cmd+C on a keyboard) or opened in Tenhou's analysis (A), the other hands hidden (H) and
 * the rivers' tsumogiri marked.
 */
export function ReplayTools(props: ReplayToolsProps): TemplateResult {
    const copyKeys = COPY_KEYS[props.shortcuts];
    return html`<section
        class="replay-tools"
        data-replay-tools
        id=${REPLAY_TOOLS_ID}
        aria-label=${t("replay.tools.title")}
        @keydown=${(event: KeyboardEvent) => onToolsKeydown(event, props.onClose)}
    >
        <button
            type="button"
            class="secondary replay-tools__item replay-tools__copy"
            aria-keyshortcuts=${copyKeys.aria}
            data-focus-key=${props.showsHand ? TOOLS_FIRST_FOCUS_KEY : nothing}
            ?disabled=${!props.showsHand}
            @click=${props.onCopyHand}
        >
            <span>${t("replay.tools.copy_hand")}</span>${KeyHint(copyKeys)}
        </button>
        <button
            type="button"
            class="secondary replay-tools__item replay-tools__analyze"
            aria-keyshortcuts=${ANALYZE_KEYS.aria}
            ?disabled=${!props.showsHand}
            @click=${props.onAnalyzeHand}
        >
            <span>${t("replay.tools.analyze_hand")}</span>${KeyHint(ANALYZE_KEYS)}
        </button>
        ${ToolSwitch({
            focusKey: props.showsHand ? null : TOOLS_FIRST_FOCUS_KEY,
            keys: HANDS_KEYS,
            kind: "hands",
            label: t("replay.options.hide_hands"),
            on: props.hideHands,
            onToggle: props.onToggleHands,
        })}
        ${ToolSwitch({
            focusKey: null,
            keys: null,
            kind: "tsumogiri",
            label: t("replay.tools.show_tsumogiri"),
            on: props.showTsumogiri,
            onToggle: props.onToggleTsumogiri,
        })}
    </section>`;
}
