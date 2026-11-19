import { type MountedView } from "@ronin/shared/router";

import { loadLimits, startGuestSession, submitCredentials } from "@/auth/handlers";
import { type AuthFields, type AuthPage, createAuthState } from "@/auth/state";
import { clearPasswordsAndFocusErrorField, renderAuth } from "@/auth/ui";

function mountAuthView(host: HTMLElement, page: AuthPage, url: URL): MountedView {
    const state = createAuthState(page, url);
    let disposed = false;
    const context = {
        isDisposed: () => disposed,
        render,
        showError: () => {
            render();
            clearPasswordsAndFocusErrorField(host, state);
        },
    };
    const actions = {
        startGuest: () => void startGuestSession(state, context),
        submit: (fields: AuthFields) => void submitCredentials(state, context, fields),
    };

    function render(): void {
        renderAuth(host, state, actions);
    }

    render();
    void loadLimits(state, context);
    return {
        rerender: render,
        unmount: () => {
            disposed = true;
        },
    };
}

export function mountLoginView(host: HTMLElement, url: URL): MountedView {
    return mountAuthView(host, "login", url);
}

export function mountRegisterView(host: HTMLElement, url: URL): MountedView {
    return mountAuthView(host, "register", url);
}
