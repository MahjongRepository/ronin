export function isAbortError(error: unknown): boolean {
    return error instanceof DOMException && error.name === "AbortError";
}

/** Whether a request ended because its own time limit ran out, as `AbortSignal.timeout` ends it. */
export function isTimeoutError(error: unknown): boolean {
    return error instanceof DOMException && error.name === "TimeoutError";
}
