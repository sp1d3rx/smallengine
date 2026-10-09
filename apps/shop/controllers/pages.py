"""Page routes — serve the SPA shell, enforcing setup and login guards."""
from py4web import action, redirect, URL
from ..common import auth, session, db, is_admin, get_user_role
from ..constants import RAW as _CONSTANTS_RAW


def _shell_context():
    """Return template vars for index.html, or redirect if not ready."""
    if db(db.auth_user).count() == 0:
        redirect(URL("setup"))
    user = auth.get_user()
    if not user:
        redirect(URL("auth", "login"))
    uid = user["id"]
    return dict(user=user, is_admin=is_admin(uid), role=get_user_role(uid))


@action("index")
@action.uses("index.html", db, session, auth)
def index():
    """Redirect to setup if no users exist; require login otherwise."""
    return _shell_context()


# Catch-all so Brython hash-routes survive a hard refresh.
_PAGES = [
    "customers", "equipment", "workorders",
    "warranty", "parts", "sales", "invoices",
    "reports", "settings", "reception",
]

@action("api/constants", method=["GET"])
def constants():
    """Serve coded-list constants to Brython. No auth required — not sensitive."""
    return _CONSTANTS_RAW


for _page in _PAGES:
    def _make_view(p):
        @action(p)
        @action.uses("index.html", db, session, auth)
        def _view():
            return _shell_context()
        _view.__name__ = f"page_{p}"
        return _view
    _make_view(_page)
