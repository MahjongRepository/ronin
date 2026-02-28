export default {
  multipass: true,
  floatPrecision: 2,
  plugins: [
    {
      name: "preset-default",
      params: {
        overrides: {
          convertPathData: { floatPrecision: 2 },
          // convertStyleToAttrs moves style="" props to presentation attributes.
          // These two plugins then incorrectly strip them:
          // - removeUselessStrokeAndFill: removes visible strokes
          // - removeUnknownsAndDefaults: removes fill="#000" (SVG default),
          //   but the page CSS sets fill:currentColor so black must be explicit.
          removeUselessStrokeAndFill: false,
          removeUnknownsAndDefaults: { defaultAttrs: false },
        },
      },
    },
    // Remove all Inkscape/Sodipodi editor attributes (namespace-prefixed)
    {
      name: "removeAttrs",
      params: {
        attrs: [
          "inkscape:.*",
          "sodipodi:.*",
        ],
      },
    },
    // Inline style="" → SVG presentation attributes (enables further minification)
    { name: "convertStyleToAttrs", params: {} },
    // Sort attributes for deterministic output
    "sortAttrs",
    // Prefix IDs with filename to prevent collisions in the combined sprite
    "prefixIds",
  ],
};
