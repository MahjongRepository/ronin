import $ from "jquery";

const VARIANT_PARAM = "state";
const STORYBOOK_PREF_KEY = "Majiang.pref.storybook";

export const SAMPLE_PLAYERS = Object.freeze(["Ronin", "Bot 1", "Bot 2", "Bot 3"]);

export function currentVariant(variants) {
    const key = new URLSearchParams(window.location.search).get(VARIANT_PARAM);
    return variants.find((variant) => variant.key === key) ?? variants[0];
}

export function renderVariantNav(variants, current) {
    const links = variants.map((variant) =>
        $("<a>")
            .attr("href", `?${VARIANT_PARAM}=${variant.key}`)
            .toggleClass("active", variant === current)
            .text(variant.title),
    );
    return $('<nav class="storybook-nav storybook-variants">').append(links);
}

/** On a short screen the header is one scrolling row; scroll it so the shown variant is in view. */
function revealActiveVariant(header) {
    header
        .find(".storybook-variants .active")
        .get(0)
        ?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

export function showBoardPage(header, pai, model, { viewpoint = 0, dealt = true } = {}) {
    $("#space").remove();
    $("body").prepend(header);
    const audio = Majiang.UI.audio($("#loaddata"));
    const board = new Majiang.UI.Board($("#board .board"), pai, audio, model);
    board.viewpoint = viewpoint;
    if (dealt) {
        board.redraw();
    }
    new Majiang.UI.GameCtl($("#board"), STORYBOOK_PREF_KEY);
    const layOutPage = () => {
        Majiang.UI.Util.scale($("#board"));
        revealActiveVariant(header);
    };
    Majiang.UI.Util.scale($("#board"));
    document.fonts.ready.then(layOutPage);
    $(window).on("resize", layOutPage);
    return board;
}
