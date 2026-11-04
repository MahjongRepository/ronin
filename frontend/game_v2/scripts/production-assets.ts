import { type Plugin } from "vite";

const DEVELOPMENT_TEXT = /storybook|game-board--debug|footer-dev-links/;
const DEVELOPMENT_MODULE = /\/src\/(?:views\/storybook[^/]*|fixtures\/)/;
const REPLAY_MODULE =
    /\/src\/(?:replay-entry\.ts|views\/replay(?:-input)?\.ts|entities\/replay\/|entities\/client\/model\/replay(?:-dispatch)?\.ts|entities\/table\/model\/replay-file\.ts|shared\/(?:api\/replays|protocol\/schemas\/replay)\.ts)/;

interface BuiltChunk {
    readonly fileName: string;
    readonly isEntry: boolean;
    readonly imports: readonly string[];
    readonly modules: Readonly<Record<string, { readonly renderedLength: number }>>;
}

function renderedModules(chunk: BuiltChunk): string[] {
    return Object.entries(chunk.modules)
        .filter(([, module]) => module.renderedLength > 0)
        .map(([id]) => id);
}

function checkReplayBoundary(chunks: readonly BuiltChunk[]): void {
    const byName = new Map(chunks.map((chunk) => [chunk.fileName, chunk]));
    const pending = new Set(chunks.filter((chunk) => chunk.isEntry));
    for (const chunk of pending) {
        const replayModules = renderedModules(chunk).filter((id) => REPLAY_MODULE.test(id));
        if (replayModules.length > 0) {
            throw new Error(
                `Eager replay modules in ${chunk.fileName}: ${replayModules.join(", ")}`,
            );
        }
        for (const name of chunk.imports) {
            const dependency = byName.get(name);
            if (dependency !== undefined) {
                pending.add(dependency);
            }
        }
    }
}

export function createProductionAssetCheck(): Plugin {
    return {
        apply: (_config, environment) =>
            environment.command === "build" && environment.mode !== "development",
        generateBundle: {
            handler(_options, bundle) {
                const outputs = Object.values(bundle);
                const chunks = outputs.filter((output) => output.type === "chunk");
                for (const chunk of chunks) {
                    const developmentModules = renderedModules(chunk).filter((id) =>
                        DEVELOPMENT_MODULE.test(id),
                    );
                    if (developmentModules.length > 0) {
                        throw new Error(
                            `Development modules in ${chunk.fileName}: ${developmentModules.join(", ")}`,
                        );
                    }
                }
                const textOutputs = outputs.filter((output) =>
                    /\.(?:js|css|html)$/.test(output.fileName),
                );
                for (const output of textOutputs) {
                    const source = output.type === "chunk" ? output.code : String(output.source);
                    if (DEVELOPMENT_TEXT.test(`${output.fileName}\n${source}`)) {
                        throw new Error(`Development content in ${output.fileName}`);
                    }
                }
                checkReplayBoundary(chunks);
            },
            order: "post",
        },
        name: "check-production-assets",
    };
}
