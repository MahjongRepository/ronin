# Ronin

It is an open Riichi Mahjong game server and client that you can run on your infrastructure.

Ronin is in an early stage of development, the first version of the server is ready and tested well, while client is in early prototyping stage.

## Backend

The game server is a WebSocket app written in Go; the lobby is Python + Starlette.

## Frontend

The client is planned to be a TypeScript app (not React).

# Third-party libraries credits

## Mahjong libraries

Below is a third-party library related to mahjong that Ronin draws on:

- [xiangting](https://github.com/Apricot-S/xiangting) as the inspiration for fast shanten calculations

## Assets

Tiles sets:

- https://github.com/FluffyStuff/riichi-mahjong-tiles
