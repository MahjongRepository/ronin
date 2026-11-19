package seam_test

import (
	"strconv"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type jsonObject struct {
	b     strings.Builder
	empty bool
}

func newObject() *jsonObject {
	o := &jsonObject{empty: true}
	o.b.WriteByte('{')
	return o
}

func (o *jsonObject) field(key, value string) *jsonObject {
	if !o.empty {
		o.b.WriteByte(',')
	}
	o.empty = false
	o.b.WriteByte('"')
	o.b.WriteString(key)
	o.b.WriteString(`":`)
	o.b.WriteString(value)
	return o
}

func (o *jsonObject) String() string {
	return o.b.String() + "}"
}

func jsonList[T any](items []T, show func(T) string) string {
	parts := make([]string, len(items))
	for i, item := range items {
		parts[i] = show(item)
	}
	return "[" + strings.Join(parts, ",") + "]"
}

func jsonName(name string) string {
	return `"` + name + `"`
}

func jsonInt(n int) string {
	return strconv.Itoa(n)
}

func jsonBool(b bool) string {
	return strconv.FormatBool(b)
}

func jsonInts(ns []int) string {
	return jsonList(ns, jsonInt)
}

func jsonOption[T any](o play.Option[T], show func(T) string) string {
	if !o.OK {
		return "null"
	}
	return show(o.Value)
}

func jsonTile(id tile.TileID) string {
	return jsonInt(id.Index())
}

func jsonTiles(ids []tile.TileID) string {
	return jsonList(ids, jsonTile)
}

func jsonSeat(s tile.Seat) string {
	return jsonInt(s.Index())
}

func jsonDice(d tile.Dice) string {
	return "[" + jsonInt(d.First) + "," + jsonInt(d.Second) + "]"
}

func windName(w tile.Wind) string {
	switch w {
	case tile.East:
		return "east"
	case tile.South:
		return "south"
	case tile.West:
		return "west"
	case tile.North:
		return "north"
	}
	return "wind " + jsonInt(int(w))
}

func kanName(k play.KanKind) string {
	switch k {
	case play.KanClosed:
		return "closed"
	case play.KanAdded:
		return "added"
	case play.KanOpen:
		return "open"
	}
	return "kan " + jsonInt(int(k))
}

func meldName(k play.MeldKind) string {
	switch k {
	case play.MeldChi:
		return "chi"
	case play.MeldPon:
		return "pon"
	case play.MeldOpenKan:
		return "open_kan"
	case play.MeldAddedKan:
		return "added_kan"
	case play.MeldClosedKan:
		return "closed_kan"
	}
	return "meld " + jsonInt(int(k))
}

func sourceName(s play.CallSource) string {
	switch s {
	case play.SourceDiscard:
		return "discard"
	case play.SourceAddedKan:
		return "added_kan"
	case play.SourceClosedKan:
		return "closed_kan"
	}
	return "source " + jsonInt(int(s))
}

func causeName(c play.GameEndCause) string {
	switch c {
	case play.EndTobi:
		return "tobi"
	case play.EndLength:
		return "length"
	case play.EndTargetReached:
		return "target_reached"
	case play.EndExtensionLimit:
		return "extension_limit"
	case play.EndFixedWallsDealt:
		return "fixed_walls_dealt"
	}
	return "cause " + jsonInt(int(c))
}

func actionJSON(a play.Action) string {
	held, _ := a.Held()
	at, _ := a.Tile()
	kan, _ := a.Kan()
	switch a.Kind() {
	case play.ActionDiscard:
		return newObject().field("discard", jsonTile(at)).String()
	case play.ActionRiichi:
		return newObject().field("riichi", jsonTile(at)).String()
	case play.ActionTsumo:
		return jsonName("tsumo")
	case play.ActionRon:
		return jsonName("ron")
	case play.ActionKyuushu:
		return jsonName("kyuushu")
	case play.ActionPass:
		return jsonName("pass")
	case play.ActionPon:
		return newObject().field("pon", jsonTiles(held[:])).String()
	case play.ActionChi:
		return newObject().field("chi", jsonTiles(held[:])).String()
	case play.ActionKan:
		return newObject().field("kan", jsonName(kanName(kan))).field("tile", jsonTile(at)).String()
	}
	return jsonName("action " + jsonInt(int(a.Kind())))
}

func contextJSON(context play.DecisionContext) string {
	switch c := context.(type) {
	case play.TurnAfterDraw:
		return newObject().field("kind", jsonName("turn_after_draw")).field("drawn", jsonTile(c.Drawn)).
			field("rinshan", jsonBool(c.Rinshan)).field("haitei", jsonBool(c.Haitei)).String()
	case play.TurnAfterCall:
		return newObject().field("kind", jsonName("turn_after_call")).
			field("kuikae", jsonList(c.Kuikae, func(k tile.Kind) string { return jsonInt(int(k)) })).String()
	case play.Call:
		return newObject().field("kind", jsonName("call")).field("tile", jsonTile(c.Tile)).field("from", jsonSeat(c.From)).
			field("source", jsonName(sourceName(c.Source))).field("houtei", jsonBool(c.Houtei)).String()
	}
	return "null"
}

func decisionLine(decision play.Decision, action play.Action) string {
	return newObject().field("decide", jsonSeat(decision.Seat)).field("context", contextJSON(decision.Context)).
		field("legal", jsonList(decision.Legal, actionJSON)).field("default", actionJSON(decision.Default)).
		field("action", actionJSON(action)).String()
}

func meldJSON(m play.MeldView) string {
	return newObject().field("kind", jsonName(meldName(m.Kind))).field("tiles", jsonTiles(m.Tiles)).
		field("called", jsonOption(m.Called, jsonTile)).field("from", jsonOption(m.From, jsonSeat)).String()
}

func shownJSON(shown play.ShownHand) string {
	return newObject().field("seat", jsonSeat(shown.Seat)).field("hand", jsonTiles(shown.Hand)).
		field("melds", jsonList(shown.Melds, meldJSON)).String()
}

func nagashiJSON(nagashi play.NagashiRiver) string {
	river := jsonList(nagashi.River, func(r play.RiverTile) string {
		return newObject().field("tile", jsonTile(r.Tile)).field("tsumogiri", jsonBool(r.Tsumogiri)).
			field("riichi", jsonBool(r.Riichi)).String()
	})
	return newObject().field("seat", jsonSeat(nagashi.Seat)).field("river", river).String()
}

func valueJSON(value play.Value) string {
	switch v := value.(type) {
	case play.Han:
		return newObject().field("han", jsonInt(v.Han)).field("fu", jsonInt(v.Fu)).String()
	case play.Yakuman:
		return newObject().field("yakuman", jsonInt(v.Count)).field("fu", jsonOption(v.Fu, jsonInt)).String()
	}
	return "null"
}

func winJSON(win play.WinResult) string {
	dora := newObject().field("dora", jsonInt(win.Dora.Dora)).field("aka_dora", jsonInt(win.Dora.AkaDora)).
		field("ura_dora", jsonInt(win.Dora.UraDora)).String()
	return newObject().field("winner", jsonSeat(win.Winner)).field("loser", jsonOption(win.Loser, jsonSeat)).
		field("hand", jsonTiles(win.Hand)).field("melds", jsonList(win.Melds, meldJSON)).
		field("win_tile", jsonTile(win.WinTile)).field("value", valueJSON(win.Value)).
		field("limit", jsonOption(win.Limit, func(l play.Limit) string { return jsonName(l.String()) })).
		field("yaku", jsonList(win.Yaku, func(y play.YakuID) string { return jsonInt(int(y)) })).
		field("dora", dora).field("ura_indicators", jsonTiles(win.UraIndicators)).
		field("pao", jsonOption(win.Pao, jsonSeat)).field("score_changes", jsonInts(win.ScoreChanges[:])).String()
}

func abortJSON(kind play.AbortKind) string {
	switch k := kind.(type) {
	case play.KyuushuKyuuhai:
		return newObject().field("kind", jsonName("kyuushu_kyuuhai")).field("seat", jsonSeat(k.Seat)).
			field("hand", jsonTiles(k.Hand)).String()
	case play.FourWinds:
		return newObject().field("kind", jsonName("four_winds")).String()
	case play.FourRiichi:
		return newObject().field("kind", jsonName("four_riichi")).field("hands", jsonList(k.Hands, shownJSON)).String()
	case play.FourKans:
		return newObject().field("kind", jsonName("four_kans")).String()
	case play.TripleRon:
		return newObject().field("kind", jsonName("triple_ron")).field("discarder", jsonSeat(k.Discarder)).
			field("tile", jsonTile(k.Tile)).field("hands", jsonList(k.Hands, shownJSON)).
			field("robbed_kan", jsonOption(k.RobbedKan, func(kan play.KanKind) string { return jsonName(kanName(kan)) })).String()
	}
	return "null"
}

func resultJSON(result play.RoundResult) string {
	switch r := result.(type) {
	case play.ExhaustiveDraw:
		return newObject().field("kind", jsonName("exhaustive_draw")).field("tenpai", jsonList(r.Tenpai, shownJSON)).
			field("nagashi", jsonList(r.Nagashi, nagashiJSON)).field("score_changes", jsonInts(r.ScoreChanges[:])).String()
	case play.Tsumo:
		return newObject().field("kind", jsonName("tsumo")).field("win", winJSON(r.Win)).String()
	case play.Ron:
		return newObject().field("kind", jsonName("ron")).field("discarder", jsonSeat(r.Discarder)).
			field("wins", jsonList(r.Wins, winJSON)).field("head_bumped", jsonList(r.HeadBumped, jsonSeat)).String()
	case play.Abortive:
		return newObject().field("kind", jsonName("abortive")).field("abort", abortJSON(r.Kind)).String()
	}
	return "null"
}

func headerJSON(h play.RoundHeader) string {
	return newObject().field("round_number", jsonInt(int(h.RoundNumber))).field("wind", jsonName(windName(h.Wind))).
		field("round_in_wind", jsonInt(h.RoundInWind)).field("dealer", jsonSeat(h.Dealer)).
		field("honba", jsonInt(h.Honba)).field("riichi_sticks", jsonInt(h.RiichiSticks)).
		field("dice", jsonDice(h.Dice)).String()
}

func standingsJSON(s play.Standings) string {
	return newObject().field("cause", jsonName(causeName(s.Cause))).field("scores", jsonInts(s.Scores[:])).
		field("placements", jsonInts(s.Placements[:])).field("points", jsonInts(s.Points[:])).String()
}

func visibilityJSON(v play.Visibility) string {
	if only, ok := v.Seat(); ok {
		return jsonSeat(only)
	}
	for _, s := range tile.Seats() {
		if !v.Includes(s) {
			return jsonName("none")
		}
	}
	return jsonName("all")
}

func eventLine(emitted play.Emitted) string {
	o := newObject().field("to", visibilityJSON(emitted.To))
	switch e := emitted.Event.(type) {
	case play.GameStarted:
		o.field("event", jsonName("game_started")).field("first_dealer", jsonSeat(e.FirstDealer)).
			field("dice", "["+jsonDice(e.Dice[0])+","+jsonDice(e.Dice[1])+"]")
	case play.RoundStarted:
		o.field("event", jsonName("round_started")).field("seat", jsonSeat(e.Seat)).field("header", headerJSON(e.Header)).
			field("scores", jsonInts(e.Scores[:])).field("hand", jsonTiles(e.Hand)).
			field("dora_indicators", jsonTiles(e.DoraIndicators)).field("live_tiles", jsonInt(e.LiveTiles))
	case play.Drew:
		o.field("event", jsonName("drew")).field("seat", jsonSeat(e.Seat)).field("tile", jsonTile(e.Tile)).
			field("rinshan", jsonBool(e.Rinshan))
	case play.DrewNotice:
		o.field("event", jsonName("drew_notice")).field("seat", jsonSeat(e.Seat)).field("rinshan", jsonBool(e.Rinshan))
	case play.Discarded:
		o.field("event", jsonName("discarded")).field("seat", jsonSeat(e.Seat)).field("tile", jsonTile(e.Tile)).
			field("tsumogiri", jsonBool(e.Tsumogiri)).field("riichi", jsonBool(e.Riichi))
	case play.RiichiDeposited:
		o.field("event", jsonName("riichi_deposited")).field("seat", jsonSeat(e.Seat)).field("score", jsonInt(e.Score)).
			field("riichi_sticks", jsonInt(e.RiichiSticks))
	case play.FuritenChanged:
		o.field("event", jsonName("furiten_changed")).field("seat", jsonSeat(e.Seat)).field("furiten", jsonBool(e.Furiten))
	case play.Called:
		o.field("event", jsonName("called")).field("seat", jsonSeat(e.Seat)).field("meld", meldJSON(e.Meld))
	case play.PaoAssigned:
		o.field("event", jsonName("pao_assigned")).field("seat", jsonSeat(e.Seat)).field("liable", jsonSeat(e.Liable))
	case play.DoraRevealed:
		o.field("event", jsonName("dora_revealed")).field("indicator", jsonTile(e.Indicator))
	case play.RoundEnded:
		o.field("event", jsonName("round_ended")).field("result", resultJSON(e.Result)).
			field("scores", jsonInts(e.Scores[:])).field("riichi_sticks", jsonInt(e.RiichiSticks))
	case play.GameEnded:
		o.field("event", jsonName("game_ended")).field("standings", standingsJSON(e.Standings))
	}
	return o.String()
}
