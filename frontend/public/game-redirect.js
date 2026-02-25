// Redirect users to the lobby if they navigate to /game without a hash fragment.
// The game client expects a hash route (e.g. #/game-id); without one there is
// nothing to render, so we send them back to the lobby landing page.
if (!location.hash || location.hash === "#" || location.hash === "#/") {
    location.replace("/");
}
