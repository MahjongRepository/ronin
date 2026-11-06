const BOARD_CSS_CONDITIONS = ["selector(:has(*))", "(container-type: size)", "(height: 100dvh)"];

interface CssSupport {
    supports: (conditionText: string) => boolean;
    registerProperty?: unknown;
}

export function supportsBoardCss(css: CssSupport | undefined = globalThis.CSS): boolean {
    return (
        css !== undefined &&
        typeof css.registerProperty === "function" &&
        BOARD_CSS_CONDITIONS.every((condition) => css.supports(condition))
    );
}
