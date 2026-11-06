import { type Locale, t } from "@/shared/i18n";

export interface FakeLanguageSwitch {
    readonly chosen: Locale[];
    readonly setLanguage: (locale: Locale) => void;
}

export function fakeLanguageSwitch(): FakeLanguageSwitch {
    const chosen: Locale[] = [];
    return {
        chosen,
        setLanguage: (locale) => {
            chosen.push(locale);
            document.documentElement.lang = locale;
            document.title = t("game.page.title");
        },
    };
}

export function resetPageLanguage(): void {
    document.documentElement.lang = "";
    document.title = "";
}
