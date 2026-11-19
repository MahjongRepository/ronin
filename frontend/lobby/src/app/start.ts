import { type Route, interceptLinks, startRouter } from "@ronin/shared/router";
import { render } from "lit-html";

import { type Chrome, type ChromeMounts, startChrome } from "@/app/chrome";
import { pageFailedView } from "@/app/page-failed";
import { type PageMeta, readPageMeta } from "@/app/page-meta";
import { lobbyRoutes } from "@/app/routes";
import { fetchSession } from "@/app/session";

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
    const chrome = startChrome(mounts, meta, () => router.rerender());
    const routes = withChromeRender(
        lobbyRoutes({ navigate: (url, options) => router.navigate(url, options) }),
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
