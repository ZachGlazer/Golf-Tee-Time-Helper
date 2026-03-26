"""
Ibis Tee Time Alert — app.py
Flask web server: signup flow, member dashboard, admin panel
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, Member
from scheduler import start_scheduler
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ibis.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ibisadmin123")

# ── Create tables on first run ──────────────────────────────────────────────

with app.app_context():
    db.create_all()
    start_scheduler(app)

# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        ibis_email    = request.form.get("ibis_email", "").strip()
        ibis_password = request.form.get("ibis_password", "").strip()
        phone         = request.form.get("phone", "").strip()
        dates         = request.form.get("dates", "").strip()
        earliest_time = request.form.get("earliest_time", "06:00")
        latest_time   = request.form.get("latest_time", "12:00")
        min_players   = int(request.form.get("min_players", 1))

        if not ibis_email or not ibis_password or not phone:
            flash("Please fill in all required fields.")
            return render_template("signup.html")

        existing = Member.query.filter_by(ibis_email=ibis_email).first()
        if existing:
            existing.ibis_password = ibis_password
            existing.phone         = phone
            existing.dates         = dates
            existing.earliest_time = earliest_time
            existing.latest_time   = latest_time
            existing.min_players   = min_players
            existing.active        = True
            db.session.commit()
            flash("Your preferences have been updated!")
        else:
            member = Member(
                ibis_email=ibis_email,
                ibis_password=ibis_password,
                phone=phone,
                dates=dates,
                earliest_time=earliest_time,
                latest_time=latest_time,
                min_players=min_players,
                active=True,
            )
            db.session.add(member)
            db.session.commit()

        return redirect(url_for("confirmed"))

    return render_template("signup.html")


@app.route("/confirmed")
def confirmed():
    return render_template("confirmed.html")


@app.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        member = Member.query.filter_by(ibis_email=email).first()
        if member:
            member.active = False
            db.session.commit()
            flash("You have been unsubscribed. No more alerts will be sent.")
        else:
            flash("We couldn't find an account with that email.")
        return render_template("unsubscribe.html")
    return render_template("unsubscribe.html")


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Wrong password.")
    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    members = Member.query.order_by(Member.created_at.desc()).all()
    return render_template("admin_dashboard.html", members=members)


@app.route("/admin/toggle/<int:member_id>")
def admin_toggle(member_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    member = Member.query.get_or_404(member_id)
    member.active = not member.active
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete/<int:member_id>")
def admin_delete(member_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    member = Member.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
