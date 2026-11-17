from game.engine import Discard, MahjongGameService, Pass, Ron
from game.session.ai_player import choose_ai_action
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.start_wall import make_start_wall

SEED = "5" * 192
DEALER = 0
READY_HAND = tile_copies(0, man="123456789", pin="11", sou="45")


def test_choose_ai_action__when_a_discard_offers_it_ron__should_pass():
    discarded_six_sou = tile_copies(1, sou="6")[0]
    hands = (
        tile_copies(0, pin="2345678", sou="12378", honors="1"),
        READY_HAND,
        tile_copies(2, pin="123456789", sou="1234"),
        tile_copies(3, pin="123456789", sou="5789"),
    )
    service = MahjongGameService()
    runtime, _ = service.new_game(SEED, walls=[make_start_wall(hands, draws=[discarded_six_sou])])
    service.begin_round(runtime)
    service.act(runtime, DEALER, Discard(tile=discarded_six_sou))
    decision = service.decision(runtime, 1)
    assert decision is not None
    assert Ron() in decision.legal

    assert choose_ai_action(decision) == Pass()
