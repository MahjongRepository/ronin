"""
Immutable state update utilities using Pydantic model_copy.

Provides helper functions for common immutable state updates on frozen
Pydantic models. These functions never mutate the input state - they
always return new state objects with the requested changes applied.
"""

from game.logic.state import (
    CallResponse,
    Discard,
    MahjongGameState,
    MahjongRoundState,
    PendingCallPrompt,
)


def update_player(
    round_state: MahjongRoundState,
    seat: int,
    **updates: object,
) -> MahjongRoundState:
    """
    Return new round state with updated player at seat.

    Args:
        round_state: Current round state
        seat: Player seat to update (0-3)
        **updates: Fields to update on the player

    Returns:
        New MahjongRoundState with updated player

    """
    players = list(round_state.players)
    players[seat] = round_state.players[seat].model_copy(update=updates)
    return round_state.model_copy(update={"players": tuple(players)})


def add_tile_to_player(
    round_state: MahjongRoundState,
    seat: int,
    tile_id: int,
) -> MahjongRoundState:
    """
    Return new state with tile added to player's hand.

    Args:
        round_state: Current round state
        seat: Player seat
        tile_id: Tile ID to add

    Returns:
        New MahjongRoundState with tile added to player's hand

    """
    player = round_state.players[seat]
    new_tiles = (*player.tiles, tile_id)
    return update_player(round_state, seat, tiles=new_tiles)


def remove_tile_from_player(
    round_state: MahjongRoundState,
    seat: int,
    tile_id: int,
) -> MahjongRoundState:
    """
    Return new state with tile removed from player's hand.

    Args:
        round_state: Current round state
        seat: Player seat
        tile_id: Tile ID to remove

    Returns:
        New MahjongRoundState with tile removed from player's hand

    Raises:
        ValueError: If tile is not in player's hand

    """
    player = round_state.players[seat]
    tiles = list(player.tiles)
    tiles.remove(tile_id)
    return update_player(round_state, seat, tiles=tuple(tiles))


def add_discard_to_player(
    round_state: MahjongRoundState,
    seat: int,
    discard: Discard,
) -> MahjongRoundState:
    """
    Return new state with discard added to player's history.

    Args:
        round_state: Current round state
        seat: Player seat
        discard: Discard record to add

    Returns:
        New MahjongRoundState with discard added

    """
    player = round_state.players[seat]
    new_discards = (*player.discards, discard)
    return update_player(round_state, seat, discards=new_discards)


def advance_turn(
    round_state: MahjongRoundState,
) -> MahjongRoundState:
    """
    Return new state with turn advanced to next player.

    Args:
        round_state: Current round state

    Returns:
        New MahjongRoundState with turn advanced

    """
    new_seat = (round_state.current_player_seat + 1) % 4
    return round_state.model_copy(
        update={
            "current_player_seat": new_seat,
            "turn_count": round_state.turn_count + 1,
        }
    )


def clear_pending_prompt(
    round_state: MahjongRoundState,
) -> MahjongRoundState:
    """
    Return new state with pending call prompt cleared.

    Args:
        round_state: Current round state

    Returns:
        New MahjongRoundState with pending_call_prompt set to None

    """
    return round_state.model_copy(update={"pending_call_prompt": None})


def add_prompt_response(
    prompt: PendingCallPrompt,
    response: CallResponse,
) -> PendingCallPrompt:
    """
    Return new prompt with response appended and seat removed from pending set.

    Args:
        prompt: Current pending call prompt
        response: Call response to add

    Returns:
        New PendingCallPrompt with response added and seat removed from pending

    """
    pending = set(prompt.pending_seats)
    pending.discard(response.seat)
    return prompt.model_copy(
        update={
            "responses": (*prompt.responses, response),
            "pending_seats": frozenset(pending),
        }
    )


def update_game_with_round(
    game_state: MahjongGameState,
    round_state: MahjongRoundState,
) -> MahjongGameState:
    """
    Return new game state with updated round state.

    Args:
        game_state: Current game state
        round_state: New round state to set

    Returns:
        New MahjongGameState with updated round_state

    """
    return game_state.model_copy(update={"round_state": round_state})


def update_all_discards(
    round_state: MahjongRoundState,
    tile_id: int,
) -> MahjongRoundState:
    """
    Return new round state with tile added to all_discards tracking.

    Args:
        round_state: Current round state
        tile_id: Tile ID to add to all_discards

    Returns:
        New MahjongRoundState with tile added to all_discards

    """
    new_all_discards = (*round_state.all_discards, tile_id)
    return round_state.model_copy(update={"all_discards": new_all_discards})


def clear_all_players_ippatsu(
    round_state: MahjongRoundState,
) -> MahjongRoundState:
    """
    Return new round state with all players' ippatsu flags cleared.

    Used when a meld is called, which breaks ippatsu for everyone.

    Args:
        round_state: Current round state

    Returns:
        New MahjongRoundState with all ippatsu flags cleared

    """
    players = list(round_state.players)
    for i, p in enumerate(players):
        if p.is_ippatsu:
            players[i] = p.model_copy(update={"is_ippatsu": False})
    return round_state.model_copy(update={"players": tuple(players)})
