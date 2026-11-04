export function isAbortError(error: unknown): boolean {
    return error instanceof DOMException && error.name === "AbortError";
}
