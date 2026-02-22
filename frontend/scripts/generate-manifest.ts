import { readdirSync, writeFileSync } from "fs";

const files = readdirSync("dist");
const jsFiles = files.filter((f) => f.endsWith(".js"));
const cssFiles = files.filter((f) => f.endsWith(".css"));

if (jsFiles.length !== 1) {
    throw new Error(`Expected exactly 1 .js file in dist/, found ${jsFiles.length}: ${jsFiles.join(", ")}`);
}
if (cssFiles.length !== 1) {
    throw new Error(`Expected exactly 1 .css file in dist/, found ${cssFiles.length}: ${cssFiles.join(", ")}`);
}

const manifest = { js: jsFiles[0], css: cssFiles[0] };
writeFileSync("dist/manifest.json", JSON.stringify(manifest));
