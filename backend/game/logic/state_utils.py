"""
Immutable state update utilities using Pydantic model_copy.

Provides helper functions for common immutable state updates on frozen
Pydantic models. These functions never mutate the input state - they
always return new state objects with the requested changes applied.
"""

from game.logic.state import (
    CallResponse,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    PendingCallPrompt,
)

_PLAYER_FIELDS = set(MahjongPlayer.model_fields)


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

    Raises:
        ValueError: If seat is out of bounds or update fields are invalid

    """
    if not (0 <= seat < len(round_state.players)):
        raise ValueError(f"Invalid seat {seat}, expected 0-{len(round_state.players) - 1}")
    invalid_fields = set(updates) - _PLAYER_FIELDS
    if invalid_fields:
        raise ValueError(f"Invalid player fields: {invalid_fields}")
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
    new_seat = (round_state.current_player_seat + 1) % len(round_state.players)
    return round_state.model_copy(
        update={
            "current_player_seat": new_seat,
            "turn_count": round_state.turn_count + 1,
        },
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
    pending.remove(response.seat)
    return prompt.model_copy(
        update={
            "responses": (*prompt.responses, response),
            "pending_seats": frozenset(pending),
        },
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
    if not any(p.is_ippatsu for p in round_state.players):
        return round_state
    players = list(round_state.players)
    for i, p in enumerate(players):
        if p.is_ippatsu:
            players[i] = p.model_copy(update={"is_ippatsu": False})
    return round_state.model_copy(update={"players": tuple(players)})
