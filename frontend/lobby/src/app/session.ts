import { apiGet } from "@/api";

export interface SessionUser {
    readonly isAdmin: boolean;
    readonly isGuest: boolean;
    readonly username: string;
}

export interface Session {
    readonly user: SessionUser | null;
}

function parseUser(value: unknown): SessionUser | undefined {
    if (typeof value !== "object" || value === null) {
        return undefined;
    }
    const { is_admin: isAdmin, is_guest: isGuest, username } = value as Record<string, unknown>;
    if (
        typeof username !== "string" ||
        typeof isAdmin !== "boolean" ||
        typeof isGuest !== "boolean"
    ) {
        return undefined;
    }
    return { isAdmin, isGuest, username };
}

export function parseSession(data: unknown): Session | null {
    if (typeof data !== "object" || data === null || !("user" in data)) {
        return null;
    }
    if (data.user === null) {
        return { user: null };
    }
    const user = parseUser(data.user);
    return user === undefined ? null : { user };
}

export async function fetchSession(): Promise<Session | null> {
    const result = await apiGet("/api/lobby/session");
    const session = result.ok ? parseSession(result.data) : null;
    if (session === null) {
        console.error("lobby session not loaded", result.ok ? "invalid answer" : result.error);
    }
    return session;
}
