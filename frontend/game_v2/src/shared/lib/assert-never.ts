/** Fail the build when a `switch` over a union misses a member, and throw if one slips through at runtime. */
export function assertNever(value: never): never {
    throw new Error(`Unhandled value: ${JSON.stringify(value)}`);
}
