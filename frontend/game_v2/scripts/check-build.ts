import { build } from "vite";

await build({
    build: { write: false },
    logLevel: "warn",
});
