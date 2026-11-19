import { type Locale } from "@ronin/shared/locale";
import {
    type MountedView,
    type NavigateOptions,
    type Route,
    lazyRoute,
} from "@ronin/shared/router";

import { pageFailedView } from "@/app/page-failed";
import { fetchSession } from "@/app/session";
import { mountLoginView, mountRegisterView } from "@/auth";
import { mountHistoryView } from "@/history";
import { mountLobbyView } from "@/lobby";
import { mountMatchmakingView } from "@/matchmaking";
import { mountRoomView } from "@/room";
import { mountSettingsView } from "@/settings";
import { mountTournamentView } from "@/tournament";
import { mountTournamentsView } from "@/tournaments";

export interface RouteDeps {
    readonly navigate: (url: string, options?: NavigateOptions) => void;
    readonly setLanguage: (locale: Locale) => void;
}

function mountSignedInOnly(url: URL, deps: RouteDeps, mountView: () => MountedView): MountedView {
    let disposed = false;
    async function sendSignedOutToLogin(): Promise<void> {
        const session = await fetchSession();
        if (disposed || session === null || session.user !== null) {
            return;
        }
        const next = encodeURIComponent(url.pathname + url.search);
        deps.navigate(`/login?next=${next}`, { replace: true });
    }

    const mounted = mountView();
    void sendSignedOutToLogin();
    return {
        rerender: mounted.rerender,
        unmount: () => {
            disposed = true;
            mounted.unmount();
        },
    };
}

function developmentRoutes(): Route[] {
    if (!import.meta.env.DEV) {
        return [];
    }
    return [
        lazyRoute(
            /^\/storybook\/?$/,
            async () => {
                const { mountStorybookView } = await import("@/storybook");
                return mountStorybookView;
            },
            pageFailedView,
        ),
    ];
}

export function lobbyRoutes(deps: RouteDeps): Route[] {
    return [
        {
            mount: (host, _params, url) => mountLobbyView(host, url, { navigate: deps.navigate }),
            pattern: /^\/$/,
        },
        {
            mount: (host, params) =>
                mountRoomView(host, params.id ?? "", { navigate: deps.navigate }),
            pattern: /^\/rooms\/(?<id>[^/]+)\/?$/,
        },
        {
            mount: (host) => mountTournamentsView(host, { navigate: deps.navigate }),
            pattern: /^\/tournaments\/?$/,
        },
        {
            mount: (host, params) =>
                mountTournamentView(host, params.id ?? "", { navigate: deps.navigate }),
            pattern: /^\/tournaments\/(?<id>[^/]+)\/?$/,
        },
        {
            mount: (host) => mountMatchmakingView(host),
            pattern: /^\/matchmaking\/?$/,
        },
        {
            mount: (host) => mountHistoryView(host),
            pattern: /^\/history\/?$/,
        },
        {
            mount: (host, _params, url) => mountLoginView(host, url),
            pattern: /^\/login\/?$/,
        },
        {
            mount: (host, _params, url) => mountRegisterView(host, url),
            pattern: /^\/register\/?$/,
        },
        {
            mount: (host, _params, url) =>
                mountSignedInOnly(url, deps, () =>
                    mountSettingsView(host, { setLanguage: deps.setLanguage }),
                ),
            pattern: /^\/settings\/?$/,
        },
        lazyRoute(
            /^\/admin\/monitoring\/?$/,
            async () => {
                const { mountMonitoringView } = await import("@/monitoring");
                return mountMonitoringView;
            },
            pageFailedView,
        ),
        ...developmentRoutes(),
    ];
}
