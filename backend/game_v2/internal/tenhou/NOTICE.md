# Tenhou notice

**Applies to**: this folder: `tenhou` (the export of a replay as a Tenhou log) and `tenhoulog` (the
check of the engine's scoring against wins from Tenhou logs)

Tenhou (天鳳), tenhou.net and the Tenhou log format are the property of C-EGG Inc., the operator of the
Tenhou online mahjong service. All rights in them belong to their owner. Ronin is not affiliated with,
endorsed by or sponsored by C-EGG Inc. or tenhou.net, and names Tenhou only to identify the service and
its replay format.

The game server writes its own replays in the Tenhou log format so that players can open their games in
tools that read that format, and the tests read wins from Tenhou logs to check the engine's scoring. The
format is used as a reference for compatibility only: the converter and the checks were written
independently, and no Tenhou source code, client, server or other software is copied, decompiled or
included.

No Tenhou log, or data taken from one, is included in this repository. The scoring check reads Tenhou
logs only from a developer's own copy, outside the repository; its committed tests use hands made up for
them.
