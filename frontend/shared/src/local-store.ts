/** A value this browser keeps in `localStorage` under one key, read and written as JSON. */
export interface LocalStore<Value> {
    readonly load: () => Value;
    readonly save: (value: Value) => void;
}

/**
 * A value kept in `localStorage` under `key`, a convenience of this browser: `read` turns whatever JSON is stored into
 * a value, and storage that is blocked, full or holds no JSON gives the fallback and keeps nothing, so a page works the
 * same without it.
 */
export function localStore<Value>(
    key: string,
    read: (stored: unknown) => Value,
    fallback: Value,
): LocalStore<Value> {
    return {
        load: () => {
            try {
                const raw = localStorage.getItem(key);
                return raw === null ? fallback : read(JSON.parse(raw));
            } catch {
                return fallback;
            }
        },
        save: (value) => {
            try {
                localStorage.setItem(key, JSON.stringify(value));
            } catch {
                return;
            }
        },
    };
}
