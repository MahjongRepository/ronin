import { type CssSupport, supportsBoardCss } from "@ronin/shared/browser-support";

export function showUnsupportedBrowserNotice(css: CssSupport | undefined = globalThis.CSS): void {
    const notice = document.querySelector<HTMLElement>("[data-browser-notice]");
    if (notice && !supportsBoardCss(css)) {
        notice.hidden = false;
    }
}
