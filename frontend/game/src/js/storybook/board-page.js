import $ from "jquery";

const VARIANT_PARAM = "state";

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

function fitBoardBelowHeader() {
    const board = $("#board");
    const height = board.outerHeight();
    const available = window.innerHeight - board.offset().top;
    const scale = Math.min(1, available / height);
    board.css({
        transform: `scale(${scale})`,
        transformOrigin: "top center",
        marginBottom: height * (scale - 1),
    });
}

export function showBoardPage(header, pai, model, { viewpoint = 0 } = {}) {
    $("#space").remove();
    $("body").prepend(header);
    const audio = Majiang.UI.audio($("#loaddata"));
    const board = new Majiang.UI.Board($("#board .board"), pai, audio, model);
    board.viewpoint = viewpoint;
    board.redraw();
    fitBoardBelowHeader();
    document.fonts.ready.then(fitBoardBelowHeader);
    $(window).on("resize", fitBoardBelowHeader);
    return board;
}
