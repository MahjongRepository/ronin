import { build } from "vite";

await build({
    build: { write: false },
    logLevel: "warn",
    plugins: [
        {
            generateBundle(_options, bundle) {
                for (const output of Object.values(bundle)) {
                    if (output.type === "chunk") {
                        const developmentModules = Object.keys(output.modules).filter((id) =>
                            /\/src\/(?:views\/storybook[^/]*|fixtures\/)/.test(id),
                        );
                        if (developmentModules.length > 0) {
                            throw new Error(
                                `Development modules in ${output.fileName}: ${developmentModules.join(", ")}`,
                            );
                        }
                    } else if (
                        output.fileName.endsWith(".css") &&
                        /storybook/.test(String(output.source))
                    ) {
                        throw new Error(`Storybook CSS in ${output.fileName}`);
                    }
                }
            },
            name: "check-production-assets",
        },
    ],
});
