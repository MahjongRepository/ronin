import $ from "jquery";

/** A side panel's head (the round list, the help): its title and a button that closes it. */
export function panelHead(titleId, title, closeLabel) {
    return $('<div class="replay-panel-head">').append(
        $(`<h2 id="${titleId}">`).text(title),
        $('<button type="button" class="replay-panel-close">')
            .attr({ "aria-label": closeLabel, title: "Close" })
            .append($('<span aria-hidden="true">').text("✕")),
    );
}
