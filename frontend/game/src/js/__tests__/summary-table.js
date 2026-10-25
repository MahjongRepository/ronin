import $ from "jquery";

/** The final standings table markup majiang-ui's summary fills in, as `index.html` holds it. */
export function renderSummary() {
    const cells = (tag, cls) => `<${tag} class="${cls}"></${tag}>`.repeat(4);
    return $(`<div class="summary"><table>
        <thead>
            <tr class="r_rank"><th colspan="3"></th>${cells("td", "rank")}</tr>
            <tr class="r_player">${cells("th", "player")}</tr>
        </thead>
        <tbody class="body"><tr class="r_diff">
            <th class="jushu"></th><th class="changbang"></th><th class="last"></th>
            ${'<td class="back"><span class="diff"></span><span class="lizhi"></span></td>'.repeat(4)}
        </tr></tbody>
        <tfoot>
            <tr class="r_defen"><th colspan="3"></th>${cells("td", "defen")}</tr>
            <tr class="r_point"><th colspan="3"></th>${cells("td", "point")}</tr>
        </tfoot>
    </table></div>`);
}

/** The text of each row matching selector, its cells joined by "|". */
export function rowTexts(root, selector) {
    return root
        .find(selector)
        .map((i, row) =>
            $(row)
                .children()
                .map((j, cell) => $(cell).text())
                .get()
                .join("|"),
        )
        .get();
}
