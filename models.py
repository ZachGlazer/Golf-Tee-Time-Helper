"""
models.py — SQLAlchemy database models
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Member(db.Model):
    __tablename__ = "members"

    id            = db.Column(db.Integer, primary_key=True)
    ibis_email    = db.Column(db.String(200), unique=True, nullable=False)
    ibis_password = db.Column(db.String(200), nullable=False)
    phone         = db.Column(db.String(20), nullable=False)

    # Preferences
    dates         = db.Column(db.String(500), default="")   # comma-separated YYYY-MM-DD, empty = any
    earliest_time = db.Column(db.String(10), default="06:00")
    latest_time   = db.Column(db.String(10), default="14:00")
    min_players   = db.Column(db.Integer, default=1)

    # State
    active        = db.Column(db.Boolean, default=True)
    alerted_times = db.Column(db.Text, default="")          # pipe-separated seen tee time keys
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def get_alerted_set(self):
        if not self.alerted_times:
            return set()
        return set(self.alerted_times.split("|"))

    def add_alerted(self, key: str):
        existing = self.get_alerted_set()
        existing.add(key)
        self.alerted_times = "|".join(existing)

    def get_dates_list(self):
        if not self.dates:
            return []
        return [d.strip() for d in self.dates.split(",") if d.strip()]

    def __repr__(self):
        return f"<Member {self.ibis_email}>"
