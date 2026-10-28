/**
 * The page's language, set on <html lang> before anything renders (docs/i18n.md): the lang cookie when it names a
 * supported locale, else the first supported browser language by its primary subtag, else English. The bundle reads it
 * from there; this classic script runs before it so the loading screen already shows the right language.
 */
(function () {
    "use strict";

    var SUPPORTED = ["en", "ja", "ru"];

    function cookieLocale() {
        var entries = document.cookie ? document.cookie.split(";") : [];
        for (var i = 0; i < entries.length; i++) {
            var entry = entries[i].trim();
            if (entry.indexOf("lang=") === 0) {
                var value = entry.slice("lang=".length);
                return SUPPORTED.indexOf(value) >= 0 ? value : null;
            }
        }
        return null;
    }

    function browserLocale() {
        var languages = navigator.languages && navigator.languages.length
            ? navigator.languages
            : [navigator.language || ""];
        for (var i = 0; i < languages.length; i++) {
            var primary = String(languages[i]).split("-")[0].toLowerCase();
            if (SUPPORTED.indexOf(primary) >= 0) {
                return primary;
            }
        }
        return null;
    }

    document.documentElement.lang = cookieLocale() || browserLocale() || "en";
})();
