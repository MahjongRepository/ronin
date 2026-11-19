import { readCsrfToken, storeCsrfToken } from "@/app/page-meta";

export type ApiResult =
    | { readonly ok: true; readonly data: unknown }
    | { readonly ok: false; readonly error: string };

export const API_ERROR = {
    CSRF_INVALID: "csrf_invalid",
    NETWORK: "network_error",
    UNAUTHORIZED: "unauthorized",
} as const;

const HTTP_UNAUTHORIZED = 401;

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

async function readBody(response: Response): Promise<unknown> {
    const text = await response.text();
    try {
        return JSON.parse(text) as unknown;
    } catch (error: unknown) {
        if (error instanceof SyntaxError) {
            return null;
        }
        throw error;
    }
}

function errorCode(body: unknown, status: number): string {
    return isRecord(body) && typeof body.error === "string" ? body.error : `http_${String(status)}`;
}

function sendToLogin(): void {
    const next = window.location.pathname + window.location.search;
    window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

function keepFreshCsrfToken(body: unknown): void {
    if (isRecord(body) && typeof body.csrf_token === "string") {
        storeCsrfToken(body.csrf_token);
    }
}

async function fetchResponse(path: string, init: RequestInit): Promise<Response | null> {
    try {
        return await fetch(path, { ...init, credentials: "same-origin" });
    } catch (error: unknown) {
        console.error(`${init.method ?? "GET"} ${path} failed`, error);
        return null;
    }
}

function failedResult(response: Response, body: unknown): ApiResult {
    if (response.status === HTTP_UNAUTHORIZED) {
        sendToLogin();
        return { error: API_ERROR.UNAUTHORIZED, ok: false };
    }
    const error = errorCode(body, response.status);
    if (error === API_ERROR.CSRF_INVALID) {
        keepFreshCsrfToken(body);
    }
    return { error, ok: false };
}

async function send(path: string, init: RequestInit): Promise<ApiResult> {
    const response = await fetchResponse(path, init);
    if (response === null) {
        return { error: API_ERROR.NETWORK, ok: false };
    }
    const body = await readBody(response);
    return response.ok ? { data: body, ok: true } : failedResult(response, body);
}

function postOnce(path: string, body: unknown): Promise<ApiResult> {
    return send(path, {
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json", "X-CSRF-Token": readCsrfToken() },
        method: "POST",
    });
}

export function apiGet(path: string): Promise<ApiResult> {
    return send(path, { method: "GET" });
}

export async function apiPost(path: string, body: unknown): Promise<ApiResult> {
    const result = await postOnce(path, body);
    if (!result.ok && result.error === API_ERROR.CSRF_INVALID) {
        return postOnce(path, body);
    }
    return result;
}
