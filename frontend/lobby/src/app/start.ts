import { restoreBoardAppearance } from "@ronin/shared/board-appearance";
import { type Route, interceptLinks, startRouter } from "@ronin/shared/router";
import { restoreWindScript } from "@ronin/shared/winds";
import { render } from "lit-html";

import { type Chrome, type ChromeMounts, startChrome } from "@/app/chrome";
import { pageFailedView } from "@/app/page-failed";
import { type PageMeta, readPageMeta } from "@/app/page-meta";
import { lobbyRoutes } from "@/app/routes";
import { fetchSession } from "@/app/session";
import { readErrorPage, renderErrorView } from "@/retained/error-view";
import { startLegalSwap } from "@/retained/legal-swap";

function findChromeMounts(host: HTMLElement): ChromeMounts | null {
    const nav = document.querySelector<HTMLElement>("[data-lobby-nav]");
    const footer = document.querySelector<HTMLElement>("[data-lobby-footer]");
    if (nav === null || footer === null) {
        return null;
    }
    return { footer, nav, notice: host.querySelector<HTMLElement>("[data-browser-notice]") };
}

function withChromeRender(routes: readonly Route[], chrome: Chrome): Route[] {
    return routes.map((route) => ({
        mount(host, params, url) {
            const mounted = route.mount(host, params, url);
            chrome.render();
            return mounted;
        },
        pattern: route.pattern,
    }));
}

async function showSession(chrome: Chrome): Promise<void> {
    const session = await fetchSession();
    if (session !== null) {
        chrome.showSession(session);
    }
}

function startShell(host: HTMLElement, mounts: ChromeMounts, meta: PageMeta): void {
    restoreWindScript();
    restoreBoardAppearance();
    const chrome = startChrome(mounts, meta, () => router.rerender());
    const routes = withChromeRender(
        lobbyRoutes({
            navigate: (url, options) => router.navigate(url, options),
            setLanguage: chrome.switchLanguage,
        }),
        chrome,
    );
    let started = false;
    function showUnmatched(): void {
        if (started) {
            window.location.reload();
            return;
        }
        render(pageFailedView(), host);
        chrome.render();
    }
    const router = startRouter(host, routes, showUnmatched);
    started = true;
    interceptLinks(router, routes);
    void showSession(chrome);
}

export function startLobbyApp(host: HTMLElement): void {
    const meta = readPageMeta();
    const mounts = findChromeMounts(host);
    if (meta === null || mounts === null) {
        console.error("lobby shell is missing its page meta or chrome mounts");
        render(pageFailedView(), host);
        return;
    }
    startShell(host, mounts, meta);
}

function startErrorView(host: HTMLElement): () => void {
    const page = readErrorPage();
    function draw(): void {
        renderErrorView(host, page);
    }
    draw();
    return draw;
}

function startRetainedContent(main: HTMLElement): () => void {
    const errorHost = main.querySelector<HTMLElement>("[data-error-view]");
    return errorHost === null ? startLegalSwap(main) : startErrorView(errorHost);
}

export function startRetainedPage(): void {
    const meta = readPageMeta();
    const main = document.querySelector<HTMLElement>("main");
    const mounts = main === null ? null : findChromeMounts(main);
    if (meta === null || main === null || mounts === null) {
        console.error("lobby page is missing its page meta or chrome mounts");
        return;
    }
    const chrome = startChrome(mounts, meta, startRetainedContent(main));
    chrome.render();
    void showSession(chrome);
}
