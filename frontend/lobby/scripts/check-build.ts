import { build } from "vite";

await build({
    build: { write: false },
    logLevel: "warn",
    plugins: [
        {
            generateBundle(_options, bundle) {
                for (const output of Object.values(bundle)) {
                    if (
                        output.type === "asset" &&
                        output.fileName.endsWith(".css") &&
                        /storybook|footer-dev-links|data-theme=["']?light|prefers-color-scheme|\.(?:contrast|grid|overflow-auto)\b/.test(
                            String(output.source),
                        )
                    ) {
                        throw new Error(`Development or unused theme CSS in ${output.fileName}`);
                    }
                }
            },
            name: "check-production-assets",
        },
    ],
});
