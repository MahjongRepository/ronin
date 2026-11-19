import { SOUND_SETTING_KEY, readSoundSetting } from "@ronin/shared/sound-setting";
import { WIND_SCRIPT_KEY, pageWindScript } from "@ronin/shared/winds";
import { afterEach, describe, expect, it } from "vitest";

import { startChrome } from "@/app/chrome";
import { mountSettingsView } from "@/settings";

function settingsPage(): HTMLElement {
    const nav = document.createElement("nav");
    const host = document.createElement("main");
    const footer = document.createElement("footer");
    document.body.append(nav, host, footer);
    const meta = { appVersion: "dev", currentYear: 2026, devMode: false, releaseUrl: "" };
    const chrome = startChrome({ footer, nav, notice: null }, meta, () => view.rerender());
    const view = mountSettingsView(host, { setLanguage: chrome.switchLanguage });
    return host;
}

function click(host: HTMLElement, selector: string): void {
    host.querySelector<HTMLButtonElement>(selector)?.click();
}

afterEach(() => {
    document.body.replaceChildren();
    document.documentElement.lang = "en";
    delete document.documentElement.dataset.winds;
    document.cookie = "lang=; Path=/; Max-Age=0";
    localStorage.clear();
});

describe("mountSettingsView", () => {
    it("turns sound off in the setting the game reads", () => {
        const host = settingsPage();

        click(host, ".settings-page__sound");

        const stored: unknown = JSON.parse(localStorage.getItem(SOUND_SETTING_KEY) ?? "null");
        expect(readSoundSetting(stored)).toEqual({ sound_on: false });
        expect(host.querySelector(".settings-page__sound")?.getAttribute("aria-checked")).toBe(
            "false",
        );
    });

    it("switches the page language and resets the wind letters to the new language's default", () => {
        document.documentElement.lang = "en";
        const host = settingsPage();
        click(host, '.settings-page__winds-option[data-script="kanji"]');
        const chosenInEnglish = pageWindScript();

        click(host, '.settings-page__language-option[lang="ru"]');

        expect(chosenInEnglish).toBe("kanji");
        expect(document.documentElement.lang).toBe("ru");
        expect(localStorage.getItem(WIND_SCRIPT_KEY)).toBeNull();
        expect(pageWindScript()).toBe("latin");
        expect(
            host.querySelector(".settings-page__sound .settings-page__item-name")?.textContent,
        ).toBe("Звук");
    });
});
