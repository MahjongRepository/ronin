import { type Params } from "@ronin/shared/i18n";

import { API_ERROR, type ApiResult, isRecord } from "@/api";
import { type MessageKey, reportI18nError } from "@/i18n";

export type AuthPage = "login" | "register";

export const AUTH_FIELD = {
    CONFIRM_PASSWORD: "confirm_password",
    PASSWORD: "password",
    USERNAME: "username",
} as const;

export type AuthField = (typeof AUTH_FIELD)[keyof typeof AUTH_FIELD];

export interface AccountLimits {
    readonly passwordMaxLength: number;
    readonly passwordMinLength: number;
    readonly usernameMaxLength: number;
    readonly usernameMinLength: number;
}

export interface AuthFormError {
    readonly field: AuthField | null;
    readonly key: MessageKey;
    readonly params: Params;
}

export interface AuthState {
    error: AuthFormError | null;
    limits: AccountLimits | null;
    readonly next: string | null;
    readonly page: AuthPage;
    submitting: boolean;
    username: string;
}

export interface AuthFields {
    readonly confirmPassword: string | null;
    readonly password: string;
    readonly username: string;
}

const AUTH_ERROR_TEXT: ReadonlyMap<string, MessageKey> = new Map([
    ["account_not_saved", "auth.error.account_not_saved"],
    ["bot_name_pattern", "auth.error.bot_name_pattern"],
    ["human_account", "auth.error.human_account"],
    ["password_bytes", "auth.error.password_bytes"],
    ["password_length", "auth.error.password_length"],
    ["username_length", "auth.error.username_length"],
    ["username_pattern", "auth.error.username_pattern"],
    ["username_reserved_prefix", "auth.error.username_reserved_prefix"],
    ["username_taken", "auth.error.username_taken"],
    ["wrong_credentials", "auth.error.wrong_credentials"],
]);

const FAILED: AuthFormError = { field: null, key: "auth.form.failed", params: {} };

const DEFAULT_ERROR_FIELD: Readonly<Record<AuthPage, AuthField>> = {
    login: AUTH_FIELD.PASSWORD,
    register: AUTH_FIELD.USERNAME,
};

export function createAuthState(page: AuthPage, url: URL): AuthState {
    return {
        error: null,
        limits: null,
        next: url.searchParams.get("next"),
        page,
        submitting: false,
        username: "",
    };
}

export function nextQuery(state: AuthState): string {
    return state.next ? `?${new URLSearchParams({ next: state.next }).toString()}` : "";
}

export function errorField(state: AuthState): AuthField | null {
    if (state.error === null) {
        return null;
    }
    return state.error.field ?? DEFAULT_ERROR_FIELD[state.page];
}

function isLength(value: unknown): value is number {
    return Number.isInteger(value) && Number(value) > 0;
}

export function parseAccountLimits(data: unknown): AccountLimits | null {
    if (!isRecord(data) || !isRecord(data.limits)) {
        return null;
    }
    const {
        password_max_length: passwordMaxLength,
        password_min_length: passwordMinLength,
        username_max_length: usernameMaxLength,
        username_min_length: usernameMinLength,
    } = data.limits;
    if (
        !isLength(usernameMinLength) ||
        !isLength(usernameMaxLength) ||
        !isLength(passwordMinLength) ||
        !isLength(passwordMaxLength)
    ) {
        return null;
    }
    return { passwordMaxLength, passwordMinLength, usernameMaxLength, usernameMinLength };
}

export function parseSignedInNext(data: unknown): string | null {
    return isRecord(data) && typeof data.next === "string" && data.next.startsWith("/")
        ? data.next
        : null;
}

function parseParams(value: unknown): Params | null {
    if (!isRecord(value)) {
        return null;
    }
    const params: Record<string, string | number> = {};
    for (const [name, param] of Object.entries(value)) {
        if (typeof param !== "string" && typeof param !== "number") {
            return null;
        }
        params[name] = param;
    }
    return params;
}

function parseField(value: unknown): AuthField | null {
    return Object.values(AUTH_FIELD).find((field) => field === value) ?? null;
}

function authErrorOf(data: unknown): AuthFormError {
    const code = isRecord(data) ? data.code : undefined;
    const key = typeof code === "string" ? AUTH_ERROR_TEXT.get(code) : undefined;
    const params = isRecord(data) ? parseParams(data.params) : null;
    if (key === undefined || params === null) {
        reportI18nError(`auth.error.${String(code)}`, "unknown auth error code");
        return FAILED;
    }
    return { field: isRecord(data) ? parseField(data.field) : null, key, params };
}

export function describeAuthFailure(result: ApiResult): AuthFormError {
    if (result.ok) {
        console.error("sign-in answer invalid");
        return FAILED;
    }
    switch (result.error) {
        case "auth_error": {
            return authErrorOf(result.data);
        }
        case "passwords_mismatch": {
            return {
                field: AUTH_FIELD.CONFIRM_PASSWORD,
                key: "auth.form.passwords_mismatch",
                params: {},
            };
        }
        case "guest_rate_limited": {
            return { field: null, key: "auth.form.guest_rate_limited", params: {} };
        }
        case API_ERROR.CSRF_INVALID: {
            return { field: null, key: "auth.form.session_expired", params: {} };
        }
        default: {
            console.error("sign-in failed", result.error);
            return FAILED;
        }
    }
}
