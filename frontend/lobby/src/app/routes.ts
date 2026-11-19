import { type NavigateOptions, type Route } from "@ronin/shared/router";

import { mountHistoryView } from "@/history";
import { mountLobbyView } from "@/lobby";
import { mountMatchmakingView } from "@/matchmaking";
import { mountRoomView } from "@/room";

export interface RouteDeps {
    readonly navigate: (url: string, options?: NavigateOptions) => void;
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
            mount: (host) => mountMatchmakingView(host),
            pattern: /^\/matchmaking\/?$/,
        },
        {
            mount: (host) => mountHistoryView(host),
            pattern: /^\/history\/?$/,
        },
    ];
}
