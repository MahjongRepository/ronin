import { type NavigateOptions, type Route } from "@ronin/shared/router";

import { mountLobbyView } from "@/lobby";

export interface RouteDeps {
    readonly navigate: (url: string, options?: NavigateOptions) => void;
}

export function lobbyRoutes(deps: RouteDeps): Route[] {
    return [
        {
            mount: (host, _params, url) => mountLobbyView(host, url, { navigate: deps.navigate }),
            pattern: /^\/$/,
        },
    ];
}
