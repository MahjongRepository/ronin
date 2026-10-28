import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PAGE from "../../../index.html?raw";
import { hasKey, setLocale, t, tileSpoken, tileVisible } from "../../i18n/index.js";
import { gameErrorText, sessionErrorText } from "../ronin/error-text.js";
import { DRAW_CODE } from "../ronin/draws.js";
import { ROUNDS_PER_WIND, WIND_CODES, drawName, roundName, windName } from "../ronin/terms.js";
import wire from "../ronin/wire.js";
import { YAKU_IDS, yakuName } from "../ronin/yaku.js";

const LOCALES = ["en", "ja", "ru"];

/** Every tile code the page's #loaddata draws, the face-down tile aside. */
function tileCodes() {
    const page = new DOMParser().parseFromString(PAGE, "text/html");
    return [...page.querySelectorAll("#loaddata img.pai")]
        .map((image) => image.dataset.pai)
        .filter((code) => code !== "_");
}

describe.each(LOCALES)("dynamic key families in %s", (locale) => {
    beforeEach(() => {
        setLocale(locale);
        vi.spyOn(console, "error").mockImplementation(() => {});
    });

    afterEach(() => vi.restoreAllMocks());

    it("name every yaku id the server sends, and a numbered yaku for an unknown one", () => {
        for (const id of YAKU_IDS) {
            expect(hasKey(`yaku.${id}`), `yaku.${id}`).toBe(true);
            expect(yakuName(id)).toBe(t(`yaku.${id}`));
        }
        expect(yakuName(999)).toBe(t("yaku.unknown", { id: "999" }));
    });

    it("word every game and session error code wire.js mirrors", () => {
        for (const code of Object.values(wire.GAME_ERROR)) {
            expect(gameErrorText(code)).toBe(t(`game.error.${code}`));
        }
        for (const code of Object.values(wire.SESSION_ERROR)) {
            expect(sessionErrorText(code)).toBe(t(`game.session_error.${code}`));
        }
    });

    it("name every draw code", () => {
        for (const code of Object.values(DRAW_CODE)) {
            expect(drawName(code)).toBe(t(`draw.${code}`));
        }
    });

    it("name every tile of #loaddata in both its visible and spoken form", () => {
        const codes = tileCodes();
        expect(codes).toHaveLength(37);
        for (const code of codes) {
            expect(tileVisible(code)).not.toBe("");
            expect(tileSpoken(code)).not.toBe("");
        }
    });

    it("name every place, yakuman multiple and meld the board labels by number or kind", () => {
        for (let place = 1; place <= 4; place++) {
            expect(hasKey(`game.summary.rank_${place}`)).toBe(true);
        }
        for (let multiple = 1; multiple <= 6; multiple++) {
            expect(hasKey(`game.score.yakuman_${multiple}`)).toBe(true);
        }
        for (const kind of ["pon", "kan", "added_kan"]) {
            for (const side of ["right", "across", "left"]) {
                expect(hasKey(`game.meld.${kind}_from_${side}`)).toBe(true);
            }
        }
    });

    it("name every round of every wind", () => {
        WIND_CODES.forEach((_, wind) => {
            expect(windName(wind)).not.toBe("");
            for (let jushu = 0; jushu < ROUNDS_PER_WIND; jushu++) {
                expect(roundName(wind, jushu)).not.toBe("");
            }
        });
    });
});
