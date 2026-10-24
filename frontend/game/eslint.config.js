import js from "@eslint/js";
import globals from "globals";

const UPSTREAM_SOURCES = [
    "src/js/majiang.js",
    "src/js/ronin.js",
    "src/js/ronin/**",
    "src/vendor/**",
];

export default [
    { ignores: ["dist/", "public/"] },
    js.configs.recommended,
    {
        languageOptions: {
            ecmaVersion: "latest",
            sourceType: "module",
            globals: {
                ...globals.browser,
                ...globals.node,
                Majiang: "readonly",
                $: "readonly",
                jQuery: "readonly",
            },
        },
    },
    {
        files: UPSTREAM_SOURCES,
        rules: {
            "no-empty": "off",
            "no-unused-vars": "off",
            "no-useless-escape": "off",
        },
    },
];
