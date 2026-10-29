import { type Locale, applyStaticText, isLocale } from "@/i18n";

const LANGUAGE_FORM_SELECTOR = "form.footer-lang";

function readCsrfToken(form: HTMLFormElement): string {
    const input = form.elements.namedItem("csrf_token");
    return input instanceof HTMLInputElement ? input.value : "";
}

async function saveLanguage(form: HTMLFormElement, locale: Locale): Promise<void> {
    const response = await fetch(form.action, {
        body: new URLSearchParams({ csrf_token: readCsrfToken(form), lang: locale }),
        method: "POST",
        redirect: "manual",
    });
    if (response.type !== "opaqueredirect" && !response.ok) {
        throw new Error(`POST ${form.action} answered ${response.status}`);
    }
}

function markActiveLanguage(form: HTMLFormElement, locale: Locale): void {
    for (const button of form.querySelectorAll<HTMLButtonElement>("button[name=lang]")) {
        if (button.value === locale) {
            button.setAttribute("aria-current", "true");
        } else {
            button.removeAttribute("aria-current");
        }
    }
}

function readChosenLocale(event: SubmitEvent): Locale | null {
    const { submitter } = event;
    if (!(submitter instanceof HTMLButtonElement) || !isLocale(submitter.value)) {
        return null;
    }
    return submitter.value;
}

export function bindLanguageSwitchInPlace(rerender: () => void): void {
    const form = document.querySelector<HTMLFormElement>(LANGUAGE_FORM_SELECTOR);
    if (!form) {
        return;
    }
    let saving = Promise.resolve();
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const locale = readChosenLocale(event);
        if (locale === null) {
            return;
        }
        saving = saving
            .then(() => saveLanguage(form, locale))
            .catch((error: unknown) => console.error("language choice not saved", error));
        document.documentElement.lang = locale;
        markActiveLanguage(form, locale);
        applyStaticText(document.body);
        rerender();
    });
}
