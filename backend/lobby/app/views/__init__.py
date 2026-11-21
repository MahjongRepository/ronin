from app.views.assets import (
    create_templates as create_templates,
)
from app.views.assets import (
    load_vite_manifest as load_vite_manifest,
)
from app.views.assets import (
    resolve_vite_asset_urls as resolve_vite_asset_urls,
)
from app.views.game_client import (
    GAME_V2_ASSETS_PATH as GAME_V2_ASSETS_PATH,
)
from app.views.game_client import (
    BuiltGameClient as BuiltGameClient,
)
from app.views.game_client import (
    DevGameClient as DevGameClient,
)
from app.views.game_handlers import (
    game_session as game_session,
)
from app.views.game_handlers import (
    play_page as play_page,
)
from app.views.game_handlers import (
    replay_page as replay_page,
)
from app.views.replay_handlers import observe_stream as observe_stream
from app.views.replay_handlers import replay_content as replay_content
from app.views.replay_handlers import tenhou_replay as tenhou_replay
