import { LANGUAGE_NAMES, LOCALES, locale, writeLangCookie } from "../i18n/index.js";

function markChosen(options) {
    for (const option of options) {
        option.setAttribute("aria-checked", String(option.lang === locale()));
    }
}

/**
 * Fill the settings menu's language group under `root` with a choice per locale, each by its native name and in its
 * own language, the page's checked. Choosing another one remembers it in the lang cookie (as the lobby's menu does),
 * then hands it to `apply`, which shows the page in it: in place on the live game, by a reload elsewhere.
 */
export function bindLanguageMenu(root, apply) {
    const group = root.querySelector(".settings-menu .language");
    if (group === null) {
        return;
    }
    group.querySelectorAll(".language-option").forEach((option) => option.remove());
    const options = LOCALES.map((code) => {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "language-option";
        option.setAttribute("role", "radio");
        option.lang = code;
        option.textContent = LANGUAGE_NAMES[code];
        option.addEventListener("click", () => {
            if (code === locale()) {
                return;
            }
            writeLangCookie(code);
            apply(code);
            markChosen(options);
        });
        return option;
    });
    group.append(...options);
    markChosen(options);
}

/** Show the page in the chosen language by loading it again: the replay's and the storybook's, whose address holds the position. */
export function reloadInLanguage() {
    window.location.reload();
}
