"""Login / logout routes."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for
from sqlalchemy import select

from .. import auth
from ..db import SessionLocal
from ..models import User

bp = Blueprint("auth", __name__)


@bp.get("/login")
def login():
    if auth.is_authenticated():
        return redirect(url_for("views.dashboard"))
    return render_template("login.html", next=request.args.get("next", ""))


@bp.post("/login")
def login_submit():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    nxt = auth.safe_next(request.form.get("next")) or url_for("views.dashboard")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.username == username))
        # verify_password runs a constant-time-ish dummy compare when user is
        # None, so a missing username is indistinguishable from a wrong password.
        if auth.verify_password(user, password):
            auth.log_in(user)
            return redirect(nxt)
    return (
        render_template(
            "login.html", error="Invalid username or password.", next=request.form.get("next", "")
        ),
        401,
    )


@bp.post("/logout")
def logout():
    auth.log_out()
    return redirect(url_for("views.dashboard"))
