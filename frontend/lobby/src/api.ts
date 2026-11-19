import { readCsrfToken, storeCsrfToken } from "@/app/page-meta";

export type ApiResult =
    | { readonly ok: true; readonly data: unknown }
    | { readonly ok: false; readonly error: string; readonly data?: unknown };

export const API_ERROR = {
    CSRF_INVALID: "csrf_invalid",
    NETWORK: "network_error",
    UNAUTHORIZED: "unauthorized",
} as const;

const HTTP_UNAUTHORIZED = 401;
const NETWORK_FAILURE: ApiResult = { error: API_ERROR.NETWORK, ok: false };

export function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

async function readText(response: Response, path: string): Promise<string | null> {
    try {
        return await response.text();
    } catch (error: unknown) {
        console.error(`${path} answer not read`, error);
        return null;
    }
}

function parseBody(text: string): unknown {
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
    window.location.replace(`/login?next=${encodeURIComponent(next)}`);
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

function unauthorizedResult(): ApiResult {
    sendToLogin();
    return { error: API_ERROR.UNAUTHORIZED, ok: false };
}

function failedResult(response: Response, body: unknown): ApiResult {
    const error = errorCode(body, response.status);
    if (error === API_ERROR.CSRF_INVALID) {
        keepFreshCsrfToken(body);
    }
    return { data: body, error, ok: false };
}

async function send(path: string, init: RequestInit): Promise<ApiResult> {
    const response = await fetchResponse(path, init);
    if (response === null) {
        return NETWORK_FAILURE;
    }
    if (response.status === HTTP_UNAUTHORIZED) {
        return unauthorizedResult();
    }
    const text = await readText(response, path);
    if (text === null) {
        return NETWORK_FAILURE;
    }
    const body = parseBody(text);
    return response.ok ? { data: body, ok: true } : failedResult(response, body);
}

function postOnce(path: string, body: unknown): Promise<ApiResult> {
    return send(path, {
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json", "X-CSRF-Token": readCsrfToken() },
        method: "POST",
    });
}

export async function fetchPageHtml(path: string): Promise<string | null> {
    const response = await fetchResponse(path, { headers: { Accept: "text/html" }, method: "GET" });
    if (response === null) {
        return null;
    }
    if (!response.ok) {
        console.error(`GET ${path} answered ${String(response.status)}`);
        return null;
    }
    return readText(response, path);
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
