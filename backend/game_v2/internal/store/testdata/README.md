# `internal/store` test data

- `python_rows.json`: the `played_games` rows the Python game server's repository wrote for four
  games (a start, a completed game, an abandoned one at whole seconds, a failed one), read back from
  its SQLite file. `played_games_test.go` plays the same games through `store` and must read back
  the same rows, column for column and `data` byte for byte. `final_score` is in tenths; the
  Python side wrote the same integers.
