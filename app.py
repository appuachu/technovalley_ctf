from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Team, Task, Category, CTFEvent, UserFlagSubmission, Notification
from datetime import datetime, timedelta
import os
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-to-something-secure'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create admin user and default data
def create_admin():
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@technovally.com',
                password=generate_password_hash('admin1234567890'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created!")
            print("Admin credentials - Username: admin, Password: admin1234567890")
        else:
            print("Admin user already exists")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()

        if user_exists:
            flash('Username already exists!', 'danger')
        elif email_exists:
            flash('Email already registered!', 'danger')
        else:
            hashed_password = generate_password_hash(password)
            new_user = User(username=username, email=email, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))

    active_event = CTFEvent.query.filter_by(is_active=True).first()
    return render_template('dashboard.html',
                         active_event=active_event,
                         Team=Team,
                         datetime=datetime,
                         timedelta=timedelta)

@app.route('/create_individual', methods=['POST'])
@login_required
def create_individual():
    individual_name = request.form.get('individual_name')
    current_user.is_individual = True
    current_user.individual_name = individual_name
    current_user.team_id = None
    db.session.commit()
    flash(f'Welcome {individual_name}! You are now competing as an individual.', 'success')
    return redirect(url_for('individual_dashboard'))

@app.route('/individual_dashboard')
@login_required
def individual_dashboard():
    if not current_user.is_individual:
        return redirect(url_for('dashboard'))

    active_event = CTFEvent.query.filter_by(is_active=True).first()
    if active_event:
        categories = Category.query.filter_by(ctf_event_id=active_event.id).all()
    else:
        categories = []

    return render_template('individual_dashboard.html', categories=categories, active_event=active_event)

@app.route('/create_team', methods=['POST'])
@login_required
def create_team():
    team_name = request.form.get('team_name')

    if Team.query.filter_by(team_name=team_name).first():
        flash('Team name already exists!', 'danger')
        return redirect(url_for('dashboard'))

    new_team = Team(team_name=team_name, created_by=current_user.id)
    db.session.add(new_team)
    db.session.commit()

    current_user.team_id = new_team.id
    current_user.is_individual = False
    db.session.commit()

    flash(f'Team "{team_name}" created! Your team code is: {new_team.team_code}', 'success')
    return redirect(url_for('team_dashboard'))

@app.route('/admin/event/delete/<int:event_id>')
@login_required
def delete_event(event_id):
    """Delete a CTF event and all associated data"""
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    event = CTFEvent.query.get_or_404(event_id)
    event_name = event.name

    # Count items that will be deleted
    categories_count = Category.query.filter_by(ctf_event_id=event_id).count()

    # Get all tasks in this event
    tasks = Task.query.join(Category).filter(Category.ctf_event_id == event_id).all()
    tasks_count = len(tasks)

    # Delete all UserFlagSubmissions for tasks in this event
    for task in tasks:
        UserFlagSubmission.query.filter_by(task_id=task.id).delete()

    # Delete all tasks
    Task.query.filter(Task.category_id.in_(
        db.session.query(Category.id).filter_by(ctf_event_id=event_id)
    )).delete(synchronize_session=False)

    # Delete all categories
    Category.query.filter_by(ctf_event_id=event_id).delete()

    # Delete the event
    db.session.delete(event)
    db.session.commit()

    flash(f'✅ Event "{event_name}" deleted successfully! Removed {categories_count} categories and {tasks_count} tasks.', 'success')
    return redirect(url_for('admin_dashboard'))

# ============= EDIT FUNCTIONS =============

# Edit Event
@app.route('/admin/edit_event/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    event = CTFEvent.query.get_or_404(event_id)

    if request.method == 'POST':
        name = request.form.get('name')
        duration = request.form.get('duration')

        duration_map = {
            '30sec': 30,
            '1min': 60,
            '1hour': 3600,
            '24hours': 86400,
            '48hours': 172800
        }

        event.name = name
        event.duration_seconds = duration_map.get(duration, 3600)
        db.session.commit()
        flash(f'✅ Event "{event.name}" updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('edit_event.html', event=event)

# Edit Category
@app.route('/admin/edit_category/<int:category_id>', methods=['GET', 'POST'])
@login_required
def edit_category(category_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    category = Category.query.get_or_404(category_id)

    if request.method == 'POST':
        name = request.form.get('name')
        event_id = request.form.get('event_id')

        # Check if another category with same name exists for this event
        existing = Category.query.filter(
            Category.name == name,
            Category.ctf_event_id == event_id,
            Category.id != category_id
        ).first()

        if existing:
            flash(f'⚠️ Category "{name}" already exists for this CTF event!', 'danger')
        else:
            category.name = name
            category.ctf_event_id = event_id
            db.session.commit()
            flash(f'✅ Category "{category.name}" updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

    events = CTFEvent.query.all()
    return render_template('edit_category.html', category=category, events=events)

# Edit Task
@app.route('/admin/edit_task/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    task = Task.query.get_or_404(task_id)

    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        description = request.form.get('description')
        endpoint = request.form.get('endpoint')
        flag = request.form.get('flag')
        points = request.form.get('points')
        category_id = request.form.get('category_id')

        # Update task
        task.name = name
        task.description = description
        task.endpoint = endpoint
        task.flag = flag
        task.points = int(points)
        task.category_id = category_id

        db.session.commit()
        flash(f'✅ Task "{task.name}" updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    # GET request - show edit form
    categories = Category.query.all()
    return render_template('edit_task.html', task=task, categories=categories)

# Get Task Data for AJAX
@app.route('/admin/task/data/<int:task_id>')
@login_required
def get_task_data(task_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    task = Task.query.get_or_404(task_id)
    return jsonify({
        'id': task.id,
        'name': task.name,
        'description': task.description,
        'endpoint': task.endpoint,
        'flag': task.flag,
        'points': task.points,
        'category_id': task.category_id
    })

# ============= END EDIT FUNCTIONS =============

# ============= NOTIFICATION / HINT FUNCTIONS =============

@app.route('/admin/send_hint', methods=['GET', 'POST'])
@login_required
def send_hint():
    """Admin page to send hints/notifications to users"""
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title = request.form.get('title')
        message = request.form.get('message')
        task_id = request.form.get('task_id')

        if not title or not message:
            flash('Title and message are required!', 'danger')
            return redirect(url_for('send_hint'))

        # Create notification
        notification = Notification(
            title=title,
            message=message,
            hint_for_task_id=int(task_id) if task_id and task_id != '' else None,
            created_by=current_user.id
        )
        db.session.add(notification)
        db.session.commit()

        flash(f'✅ Hint/Notification sent successfully!', 'success')
        return redirect(url_for('send_hint'))

    # GET request - show form
    tasks = Task.query.all()
    return render_template('send_hint.html', tasks=tasks)

@app.route('/admin/get_hint_data/<int:task_id>')
@login_required
def get_hint_data(task_id):
    """Get hint data for a specific task"""
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    task = Task.query.get_or_404(task_id)

    # Get existing hints for this task
    hints = Notification.query.filter_by(
        hint_for_task_id=task_id
    ).order_by(Notification.created_at.desc()).all()

    hint_data = [{
        'id': h.id,
        'title': h.title,
        'message': h.message,
        'created_at': h.created_at.strftime('%Y-%m-%d %H:%M')
    } for h in hints]

    return jsonify({
        'task_name': task.name,
        'hints': hint_data
    })

@app.route('/notifications')
@login_required
def notifications():
    """View all notifications for current user"""
    notifications = Notification.query.order_by(Notification.created_at.desc()).all()
    return render_template('notifications.html', notifications=notifications)

@app.route('/api/notifications')
@login_required
def get_notifications():
    """Get all notifications as JSON"""
    notifications = Notification.query.order_by(Notification.created_at.desc()).all()
    return jsonify([{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'task_name': n.task.name if n.task else None,
        'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
        'is_read': n.is_read
    } for n in notifications])

@app.route('/notification/mark_read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    notification = Notification.query.get_or_404(notification_id)
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/notification/mark_all_read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    Notification.query.update({Notification.is_read: True, Notification.read_at: datetime.utcnow()})
    db.session.commit()
    return jsonify({'success': True})

# ============= END NOTIFICATION FUNCTIONS =============

# Optional: Add a route to delete all events (for cleanup)
@app.route('/admin/event/delete_all', methods=['POST'])
@login_required
def delete_all_events():
    """Delete all CTF events (use with caution)"""
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    if request.form.get('confirm') != 'DELETE_ALL':
        flash('Confirmation required. Type "DELETE_ALL" to confirm.', 'danger')
        return redirect(url_for('admin_dashboard'))

    events = CTFEvent.query.all()
    events_count = len(events)

    # Delete all UserFlagSubmissions first
    UserFlagSubmission.query.delete()

    # Delete all tasks
    Task.query.delete()

    # Delete all categories
    Category.query.delete()

    # Delete all events
    CTFEvent.query.delete()

    db.session.commit()

    flash(f'⚠️ All {events_count} CTF events and associated data have been deleted!', 'warning')
    return redirect(url_for('admin_dashboard'))


@app.route('/join_team', methods=['POST'])
@login_required
def join_team():
    team_code = request.form.get('team_code').upper()
    team = Team.query.filter_by(team_code=team_code).first()

    if not team:
        flash('Invalid team code!', 'danger')
    elif len(team.members) >= 3:
        flash('Team is already full! Maximum 3 members.', 'danger')
    elif current_user.team_id:
        flash('You are already in a team!', 'danger')
    else:
        current_user.team_id = team.id
        current_user.is_individual = False
        db.session.commit()
        flash(f'Successfully joined team "{team.team_name}"!', 'success')

    return redirect(url_for('team_dashboard'))

@app.route('/team_dashboard')
@login_required
def team_dashboard():
    if not current_user.team_id or current_user.is_individual:
        return redirect(url_for('dashboard'))

    team = Team.query.get(current_user.team_id)
    active_event = CTFEvent.query.filter_by(is_active=True).first()

    if active_event:
        categories = Category.query.filter_by(ctf_event_id=active_event.id).all()
    else:
        categories = []

    return render_template('team_dashboard.html', team=team, categories=categories, active_event=active_event)

@app.route('/submit_flag', methods=['POST'])
@login_required
def submit_flag():
    try:
        # Get task_id and flag from request
        task_id = request.form.get('task_id')
        if task_id is None:
            return jsonify({'success': False, 'message': 'Task ID is required!'})

        task_id = int(task_id)
        flag = request.form.get('flag')

        if not flag:
            return jsonify({'success': False, 'message': 'Flag is required!'})

        # Get the task
        task = Task.query.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': 'Task not found!'})

        # Check if already solved correctly - IMPORTANT: Check FIRST
        existing_correct = UserFlagSubmission.query.filter_by(
            user_id=current_user.id,
            task_id=task_id,
            is_correct=True
        ).first()

        if existing_correct:
            return jsonify({
                'success': False,
                'message': 'You already solved this challenge!'
            })

        # Check active CTF
        active_event = CTFEvent.query.filter_by(is_active=True).first()
        if not active_event:
            return jsonify({
                'success': False,
                'message': 'No active CTF event!'
            })

        # Check if CTF has started
        if active_event.start_time and datetime.utcnow() < active_event.start_time:
            return jsonify({
                'success': False,
                'message': '⏰ CTF has not started yet!'
            })

        # Check if CTF has ended
        if active_event.start_time:
            end_time = active_event.start_time + timedelta(seconds=active_event.duration_seconds)
            if datetime.utcnow() > end_time:
                return jsonify({
                    'success': False,
                    'message': '⏰ CTF has ended!'
                })

        # Compare flags
        submitted_flag = flag.strip()
        correct_flag = task.flag.strip()

        if submitted_flag == correct_flag:
            # Check AGAIN before inserting to prevent race conditions
            existing_correct_check = UserFlagSubmission.query.filter_by(
                user_id=current_user.id,
                task_id=task_id,
                is_correct=True
            ).first()

            if existing_correct_check:
                return jsonify({
                    'success': False,
                    'message': 'You already solved this challenge!'
                })

            # Save correct submission
            submission = UserFlagSubmission(
                user_id=current_user.id,
                task_id=task_id,
                is_correct=True
            )
            db.session.add(submission)

            # Add score to team or individual
            if current_user.team_id:
                team = Team.query.get(current_user.team_id)
                if team:
                    team.total_score += task.points
                    message = f'🎉 Correct! +{task.points} points to team {team.team_name}!'
                else:
                    message = f'🎉 Correct! +{task.points} points!'
            else:
                message = f'🎉 Correct! +{task.points} points!'

            db.session.commit()

            # Return success with points for UI update
            return jsonify({
                'success': True,
                'message': message,
                'points': task.points,
                'task_id': task_id
            })
        else:
            # Check if user already submitted a wrong attempt for this task
            existing_wrong = UserFlagSubmission.query.filter_by(
                user_id=current_user.id,
                task_id=task_id,
                is_correct=False
            ).first()

            # Only insert if no wrong submission exists (optional - allows multiple wrong attempts)
            if not existing_wrong:
                submission = UserFlagSubmission(
                    user_id=current_user.id,
                    task_id=task_id,
                    is_correct=False
                )
                db.session.add(submission)
                db.session.commit()

            return jsonify({
                'success': False,
                'message': '❌ Wrong flag! Try again.'
            })

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Invalid task ID format: {str(e)}'
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error in submit_flag: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })


@app.route('/debug/flags')
@login_required
def debug_flags():
    if not current_user.is_admin:
        return "Access denied", 403

    tasks = Task.query.all()
    result = "<h1>Task Flags in Database</h1>"
    result += "<table border='1' cellpadding='5'>"
    result += "<tr><th>ID</th><th>Name</th><th>Flag</th><th>Points</th></tr>"
    for task in tasks:
        result += f"<tr><td>{task.id}</td><td>{task.name}</td><td><code>{task.flag}</code></td><td>{task.points}</td></tr>"
    result += "</table>"

    # Also show submissions
    result += "<h2>Recent Submissions</h2>"
    submissions = UserFlagSubmission.query.order_by(UserFlagSubmission.submitted_at.desc()).limit(20).all()
    result += "<table border='1' cellpadding='5'>"
    result += "<tr><th>User</th><th>Task</th><th>Flag</th><th>Correct</th><th>Time</th></tr>"
    for sub in submissions:
        user = User.query.get(sub.user_id)
        task = Task.query.get(sub.task_id)
        result += f"<tr><td>{user.username}</td><td>{task.name if task else 'Unknown'}</td><td>{'Submitted'}</td><td>{'✅' if sub.is_correct else '❌'}</td><td>{sub.submitted_at}</td></tr>"
    result += "</table>"

    return result



@app.route('/scoreboard')
def scoreboard():
    teams = Team.query.order_by(Team.total_score.desc()).all()

    # Get individual participants (users who chose individual mode and not in a team)
    individuals = User.query.filter_by(is_individual=True, team_id=None, is_admin=False).all()

    # Calculate individual scores and create list of tuples (user, score)
    individuals_with_scores = []
    for user in individuals:
        # Calculate total points from correct submissions
        correct_submissions = UserFlagSubmission.query.filter_by(user_id=user.id, is_correct=True).all()
        total_score = sum(submission.task.points for submission in correct_submissions if submission.task)
        individuals_with_scores.append((user, total_score))

    # Sort individuals by score (highest first)
    individuals_with_scores.sort(key=lambda x: x[1], reverse=True)

    return render_template('scoreboard.html', teams=teams, individuals=individuals_with_scores)

@app.route('/scoreboard_data')
def scoreboard_data():
    # Get teams data
    teams = Team.query.order_by(Team.total_score.desc()).all()
    chart_data = []

    # Add teams to chart data
    for team in teams:
        chart_data.append({
            'name': f"🏆 {team.team_name} (Team)",
            'score': team.total_score,
            'type': 'team'
        })

    # Get individual participants
    individuals = User.query.filter_by(is_individual=True, team_id=None, is_admin=False).all()

    # Calculate individual scores
    for user in individuals:
        correct_submissions = UserFlagSubmission.query.filter_by(user_id=user.id, is_correct=True).all()
        total_score = sum(submission.task.points for submission in correct_submissions if submission.task)
        if total_score > 0:  # Only show individuals with points (optional: remove this line to show all)
            chart_data.append({
                'name': f"👤 {user.individual_name or user.username} (Individual)",
                'score': total_score,
                'type': 'individual'
            })

    # Sort by score (highest first)
    chart_data.sort(key=lambda x: x['score'], reverse=True)

    return jsonify(chart_data)

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, is_admin=True).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials!', 'danger')

    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    events = CTFEvent.query.all()
    active_event = CTFEvent.query.filter_by(is_active=True).first()
    teams = Team.query.all()
    users = User.query.filter_by(is_admin=False).all()
    tasks = Task.query.all()

    return render_template('admin_dashboard.html',
                         events=events,
                         active_event=active_event,
                         teams=teams,
                         users=users,
                         tasks=tasks)

@app.route('/admin/create_ctf', methods=['POST'])
@login_required
def create_ctf():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    name = request.form.get('name')
    duration = request.form.get('duration')

    duration_map = {
        '30sec': 30,
        '1min': 60,
        '1hour': 3600,
        '24hours': 86400,
        '48hours': 172800
    }

    duration_seconds = duration_map.get(duration, 3600)

    new_event = CTFEvent(name=name, duration_seconds=duration_seconds)
    db.session.add(new_event)
    db.session.commit()

    flash(f'CTF Event "{name}" created!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/start_ctf/<int:event_id>')
@login_required
def start_ctf(event_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    # Deactivate all events
    CTFEvent.query.update({CTFEvent.is_active: False})

    event = CTFEvent.query.get(event_id)
    event.is_active = True
    event.start_time = datetime.utcnow()
    db.session.commit()

    flash(f'CTF Event "{event.name}" has started!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/stop_ctf/<int:event_id>')
@login_required
def stop_ctf(event_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    event = CTFEvent.query.get(event_id)
    event.is_active = False
    db.session.commit()

    flash(f'CTF Event "{event.name}" has been stopped!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/create_category', methods=['POST'])
@login_required
def create_category():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    name = request.form.get('name')
    event_id = request.form.get('event_id')

    # Check if category already exists for this event
    existing_category = Category.query.filter_by(name=name, ctf_event_id=event_id).first()
    if existing_category:
        flash(f'Category "{name}" already exists for this CTF event!', 'danger')
        return redirect(url_for('admin_dashboard'))

    try:
        category = Category(name=name, ctf_event_id=event_id)
        db.session.add(category)
        db.session.commit()
        flash(f'Category "{name}" created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating category: {str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_category/<int:category_id>')
@login_required
def delete_category(category_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    category = Category.query.get_or_404(category_id)
    category_name = category.name

    # Delete all tasks in this category
    tasks = Task.query.filter_by(category_id=category_id).all()
    for task in tasks:
        # Delete submissions for each task
        UserFlagSubmission.query.filter_by(task_id=task.id).delete()
        db.session.delete(task)

    # Delete the category
    db.session.delete(category)
    db.session.commit()

    flash(f'✅ Category "{category_name}" and all its tasks deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/create_task', methods=['POST'])
@login_required
def create_task():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    name = request.form.get('name')
    description = request.form.get('description')
    endpoint = request.form.get('endpoint')
    flag = request.form.get('flag')
    points = request.form.get('points')
    category_id = request.form.get('category_id')

    task = Task(
        name=name,
        description=description,
        endpoint=endpoint,
        flag=flag,
        points=int(points),
        category_id=category_id
    )
    db.session.add(task)
    db.session.commit()

    flash(f'Task "{name}" created!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_task/<int:task_id>')
@login_required
def delete_task(task_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    task = Task.query.get(task_id)
    # Delete all submissions for this task first
    UserFlagSubmission.query.filter_by(task_id=task_id).delete()
    db.session.delete(task)
    db.session.commit()

    flash('Task deleted!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/get_ctf_status')
def get_ctf_status():
    active_event = CTFEvent.query.filter_by(is_active=True).first()
    if active_event and active_event.start_time:
        end_time = active_event.start_time + timedelta(seconds=active_event.duration_seconds)
        time_left = end_time - datetime.utcnow()
        if time_left.total_seconds() > 0:
            return jsonify({
                'active': True,
                'time_left': time_left.total_seconds(),
                'event_name': active_event.name
            })
        else:
            # CTF has ended
            return jsonify({
                'active': False,
                'time_left': 0,
                'event_name': active_event.name,
                'ended': True
            })
    return jsonify({'active': False})

@app.route('/terms')
@login_required
def terms():
    """Show terms and conditions page"""
    return render_template('terms.html', username=current_user.username)

@app.route('/agree_terms', methods=['POST'])
@login_required
def agree_terms():
    """Mark that user has agreed to terms"""
    current_user.agreed_to_terms = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/check_terms')
@login_required
def check_terms():
    """Check if user has agreed to terms"""
    return jsonify({'agreed': current_user.agreed_to_terms})

@app.route('/challenges')
@login_required
def challenges():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))

    # Check if user has agreed to terms
    if not current_user.agreed_to_terms:
        return redirect(url_for('terms'))

    active_event = CTFEvent.query.filter_by(is_active=True).first()

    if not active_event:
        flash('No active CTF!', 'warning')
        return redirect(url_for('dashboard'))

    # Check time
    if active_event.start_time:
        end_time = active_event.start_time + timedelta(seconds=active_event.duration_seconds)
        if datetime.utcnow() > end_time:
            flash('CTF ended!', 'danger')
            return redirect(url_for('dashboard'))

    categories = Category.query.filter_by(ctf_event_id=active_event.id).all()

    # Get all solved tasks once
    solved = UserFlagSubmission.query.filter_by(
        user_id=current_user.id,
        is_correct=True
    ).all()

    solved_task_ids = {s.task_id for s in solved}

    categories_with_tasks = []

    for category in categories:
        tasks = Task.query.filter_by(category_id=category.id).all()

        for task in tasks:
            task.submitted = task.id in solved_task_ids

        categories_with_tasks.append({
            'category': category,
            'tasks': tasks
        })

    return render_template('challenges.html', categories=categories_with_tasks)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()
    app.run(debug=True, host='0.0.0.0', port=5009)
