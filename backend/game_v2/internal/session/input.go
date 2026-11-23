package session

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
)

func (g *game) gameAction(conn Connection, message messaging.GameActionMessage) error {
	p := g.participantOf(conn)
	if p == nil {
		return nil
	}
	if g.lifecycle == lifecyclePending {
		sendSessionError(g.log, conn, messaging.SessionGameNotStarted, "Game has not started yet")
		return nil
	}
	if message.Action == messaging.GameActionConfirmRound {
		return g.confirmRound(p, message.WaitID)
	}
	if !message.Play.OK {
		return errNoEngineAction
	}

	action := message.Play.Value
	if g.hold.held() || !g.wait.awaits(p.seat) || message.WaitID != p.decisionID {
		return g.staleAction(p, actionName(action), message.WaitID)
	}
	if message.Called.OK && g.mismatchesOpenCall(p.seat, message.Called.Value) {
		p.log.Warn(logCalledTileMismatch, "action", actionName(action))
		return send(conn, messaging.CalledTileMismatch(action, message.WaitID).Payload())
	}

	if pick := g.m.cfg.Pick; pick != nil {
		action = g.engine.Disguised(p.seat, action, pick)
	}
	next, events, refusal := g.engine.Act(p.seat, action)
	if !refusal.OK {
		g.engine = next
		if action.AnswersCall() {
			g.hold.until = g.hold.floor
		}
		return g.followEngine(events, play.Some(p.seat))
	}
	refused, answerable := messaging.RefusalError(action, refusal.Value, message.WaitID)
	if !answerable {
		return g.kick(p, conn, action, refusal.Value)
	}
	return send(conn, refused.Payload())
}

func (g *game) mismatchesOpenCall(seat tile.Seat, called tile.TileID) bool {
	decision, ok := g.engine.Decision(seat)
	if !ok {
		return false
	}
	call, isCall := decision.Context.(play.Call)
	return isCall && call.Tile != called
}

func (g *game) confirmRound(p *participant, waitID int) error {
	if g.pause == nil || !g.pause.owes(p.seat) || waitID != p.decisionID {
		return g.staleAction(p, "confirm_round", waitID)
	}
	return g.confirmPause(p.seat)
}

func (g *game) staleAction(p *participant, action string, waitID int) error {
	p.log.Info(logStaleAction, "action", action, "wait_id", waitID)
	return send(p.conn, messaging.StaleAction(waitID).Payload())
}

func (g *game) kick(p *participant, conn Connection, action play.Action, refusal play.Refusal) error {
	p.log.Warn(logInvalidAction, "action", actionName(action), "reason", refusal.Code.String())
	g.m.evict(conn)
	err := g.disconnected(p, conn)
	if err != nil {
		return err
	}
	conn.Close(CloseInvalidAction, "invalid_game_action")
	return nil
}

func actionName(action play.Action) string {
	name := "none"
	switch action.Kind() {
	case play.ActionDiscard:
		name = "discard"
	case play.ActionRiichi:
		name = "riichi"
	case play.ActionTsumo:
		name = "tsumo"
	case play.ActionRon:
		name = "ron"
	case play.ActionKyuushu:
		name = "kyuushu"
	case play.ActionPass:
		name = "pass"
	case play.ActionPon:
		name = "pon"
	case play.ActionChi:
		name = "chi"
	case play.ActionKan:
		name = "kan"
	}
	if id, ok := action.Tile(); ok {
		return name + " " + strconv.Itoa(id.Index())
	}
	return name
}
