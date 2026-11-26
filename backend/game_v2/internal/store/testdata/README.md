# `internal/store` test data

- `python_rows.json`: the `played_games` rows the Python game server's repository wrote for four
  games (a start, a completed game, an abandoned one at whole seconds, a failed one), read back from
  its SQLite file. `played_games_test.go` plays the same games through `store` and must read back
  the same rows, column for column and `data` byte for byte, but for the `final_score_unit` key Go
  ends every row with and the `place` Go adds after a scored standing's `final_score`. `final_score` is in tenths; the Python side wrote the same integers.
  `final_scores_test.go` stores the same rows as the Python server left them, in whole points, for the
  migration to tenths.
