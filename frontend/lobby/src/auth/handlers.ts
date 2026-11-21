import { clearAllGameSessions } from "@ronin/shared/session-storage";

import { type ApiResult, apiGet, apiPost } from "@/api";
import {
    type AuthFields,
    type AuthState,
    describeAuthFailure,
    parseAccountLimits,
    parseSignedInNext,
} from "@/auth/state";

export interface AuthViewContext {
    readonly isDisposed: () => boolean;
    readonly render: () => void;
    readonly showError: () => void;
}

const AUTH_API = {
    guest: "/api/lobby/auth/guest",
    login: "/api/lobby/auth/login",
    register: "/api/lobby/auth/register",
} as const;

export async function loadLimits(state: AuthState, context: AuthViewContext): Promise<void> {
    const result = await apiGet("/api/lobby/session");
    if (context.isDisposed()) {
        return;
    }
    const limits = result.ok ? parseAccountLimits(result.data) : null;
    if (limits === null) {
        console.error("account limits not loaded", result.ok ? "invalid answer" : result.error);
        return;
    }
    state.limits = limits;
    context.render();
}

interface SignInRequest {
    readonly body: Readonly<Record<string, string | null>>;
    readonly path: string;
}

function finishSignIn(state: AuthState, context: AuthViewContext, result: ApiResult): void {
    const next = result.ok ? parseSignedInNext(result.data) : null;
    if (next !== null) {
        window.location.replace(next);
        return;
    }
    if (context.isDisposed()) {
        return;
    }
    state.submitting = false;
    state.error = describeAuthFailure(result);
    context.showError();
}

async function signIn(
    state: AuthState,
    context: AuthViewContext,
    request: SignInRequest,
): Promise<void> {
    if (state.submitting) {
        return;
    }
    state.submitting = true;
    clearAllGameSessions();
    const result = await apiPost(request.path, { ...request.body, next: state.next });
    finishSignIn(state, context, result);
}

export function submitCredentials(
    state: AuthState,
    context: AuthViewContext,
    fields: AuthFields,
): Promise<void> {
    state.username = fields.username;
    const credentials = { password: fields.password, username: fields.username };
    if (state.page === "login") {
        return signIn(state, context, { body: credentials, path: AUTH_API.login });
    }
    return signIn(state, context, {
        body: { ...credentials, confirm_password: fields.confirmPassword },
        path: AUTH_API.register,
    });
}

export function startGuestSession(state: AuthState, context: AuthViewContext): Promise<void> {
    return signIn(state, context, { body: {}, path: AUTH_API.guest });
}
