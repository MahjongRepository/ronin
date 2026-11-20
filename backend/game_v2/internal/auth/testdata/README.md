# `internal/auth` test data

- `lobby_tickets.json`: tickets signed by the lobby's `sign_game_ticket` under `secret`, each with
  whether the Python `verify_game_ticket` accepted it and, if so, the ticket it read. The expiries
  sit in 2100 or 2001, so the verdicts hold for years; an integer and a NaN expiry are signed
  as the lobby's code writes them and refused. `ticket_test.go` checks that Go reaches each verdict
  and signs each accepted ticket to the same token.
