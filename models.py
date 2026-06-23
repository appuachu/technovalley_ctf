from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import secrets

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    agreed_to_terms = db.Column(db.Boolean, default=False)
    is_individual = db.Column(db.Boolean, default=False)
    individual_name = db.Column(db.String(100), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', use_alter=True), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Track submitted flags
    submitted_flags = db.relationship('UserFlagSubmission', backref='user', lazy=True, foreign_keys='UserFlagSubmission.user_id')

    def get_score(self):
        """Calculate user's total score"""
        if self.team_id:
            team = Team.query.get(self.team_id)
            return team.total_score if team else 0
        else:
            # For individuals, sum points from correct submissions
            correct_submissions = UserFlagSubmission.query.filter_by(user_id=self.id, is_correct=True).all()
            return sum(submission.task.points for submission in correct_submissions if submission.task)

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_code = db.Column(db.String(10), unique=True, nullable=False)
    team_name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_score = db.Column(db.Integer, default=0)

    # Explicitly define the relationship with foreign key
    members = db.relationship('User', backref='team', lazy=True, foreign_keys=[User.team_id])

    creator = db.relationship('User', foreign_keys=[created_by], backref='created_teams')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.team_code:
            self.team_code = secrets.token_hex(4).upper()

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=False, nullable=False)  # Changed unique=False
    ctf_event_id = db.Column(db.Integer, db.ForeignKey('ctf_event.id'), nullable=False)
    tasks = db.relationship('Task', backref='category', lazy=True, foreign_keys='Task.category_id')

    # Add a unique constraint for name + ctf_event_id combination
    __table_args__ = (db.UniqueConstraint('name', 'ctf_event_id', name='unique_category_per_event'),)

class CTFEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    start_time = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Integer, default=3600)  # 1 hour default
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    categories = db.relationship('Category', backref='ctf_event', lazy=True, foreign_keys='Category.ctf_event_id')

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    endpoint = db.Column(db.String(200), nullable=True)
    flag = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    submissions = db.relationship('UserFlagSubmission', backref='task', lazy=True, foreign_keys='UserFlagSubmission.task_id')

class UserFlagSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_correct = db.Column(db.Boolean, default=False)

# ============= NEW NOTIFICATION MODEL =============
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    hint_for_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    task = db.relationship('Task', backref='notifications', foreign_keys=[hint_for_task_id])
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_notifications')

    def __repr__(self):
        return f'<Notification {self.title}>'
