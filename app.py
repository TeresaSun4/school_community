from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import foreign
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
import os
import re
from datetime import datetime
from markupsafe import escape
from flask import jsonify

# Start the Flask app
app = Flask(__name__)

# App settings
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'campus-community-app-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'community.db')
app.config['SQLALCHEMY_BINDS'] = {
    'content_db': 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'content.db')
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # this was annoying me with warnings
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['WTF_CSRF_ENABLED'] = False  # turned off for now

# database setup
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
migrate = Migrate(app, db)

# login stuff
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# table to store who likes what posts
likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('post_id', db.Integer, primary_key=True),  # Just the post ID
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

# create database tables
def init_db():
    """Create the database tables"""
    with app.app_context():
        try:
            # create all tables
            db.create_all()
            print("Database tables created successfully")
        except Exception as e:
            print(f"Database error: {e}")

# Run this when we start the app
if __name__ == "__main__":
    init_db()

# user class - stores user information
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128))  # Store hashed passwords only
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    avatar = db.Column(db.String(120))  # Profile picture filename

    # Link to posts this user made (cross-database relationship)
    posts = db.relationship('Post', backref='author', lazy=True,
                          primaryjoin="User.id == foreign(Post.user_id)", viewonly=True)
    # Link to comments this user made (cross-database relationship)
    comments = db.relationship('Comment', backref='author', lazy=True,
                            primaryjoin="User.id == foreign(Comment.user_id)", viewonly=True)
    # Posts this user liked (many-to-many relationship)
    liked_posts = db.relationship(
        'Post',
        secondary=likes,
        backref=db.backref('likes', lazy='dynamic'),
        lazy='dynamic',
        primaryjoin="User.id == likes.c.user_id",
        secondaryjoin="Post.id == likes.c.post_id"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def like_post(self, post):
        """like a post"""
        try:
            if not self.has_liked_post(post):
                # add like to database
                db.session.execute(
                    likes.insert().values(user_id=self.id, post_id=post.id)
                )
                return True
            return False
        except Exception as e:
            print(f"error liking post: {e}")
            return False

    def unlike_post(self, post):
        """Remove like from a post"""
        try:
            if self.has_liked_post(post):
                # Remove like from database
                db.session.execute(
                    likes.delete().where(
                        (likes.c.user_id == self.id) & (likes.c.post_id == post.id)
                    )
                )
                return True
            return False
        except Exception as e:
            print(f"Error unliking post: {e}")
            return False

    def has_liked_post(self, post):
        """Check if user already liked this post"""
        try:
            # Check if like exists in database
            result = db.session.execute(
                db.select([likes]).where(
                    (likes.c.user_id == self.id) & (likes.c.post_id == post.id)
                )
            ).first()
            return result is not None
        except Exception as e:
            print(f"Error checking like: {e}")
            return False

# Post pictures
class PostImage(db.Model):
    __bind_key__ = 'content_db'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', name='fk_image_post'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Post(db.Model):
    __bind_key__ = 'content_db'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), nullable=False, default='general')
    comments = db.relationship('Comment', backref='post', lazy=True, cascade="all, delete-orphan")
    images = db.relationship('PostImage', backref='post', lazy=True, cascade="all, delete-orphan")
    
    @property
    def likes(self):
        """Get the likes for this post"""
        class LikeQuery:
            def __init__(self, post_id):
                self.post_id = post_id
            
            def count(self):
                """Count likes for this post"""
                try:
                    # Count how many people liked this post
                    result = db.session.execute(
                        db.select(db.func.count(likes.c.user_id)).where(
                            likes.c.post_id == self.post_id
                        )
                    ).scalar()
                    return result or 0
                except Exception as e:
                    print(f"Error counting likes: {e}")
                    return 0
        
        return LikeQuery(self.id)

# Comment class - stores comments on posts
class Comment(db.Model):
    __bind_key__ = 'content_db'  # Use separate database for content
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)  # Comment text content
    user_id = db.Column(db.Integer, nullable=False)  # ID of user who wrote comment
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', name='fk_comment_post'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # When comment was created

# Highlight search words in text
def highlight(text, query):
    """
    Highlight search terms in text by wrapping them in <mark> tags
    """
    if not query:
        return text  # No search term provided
    
    # Escape HTML to prevent injection attacks
    text = escape(text)
    query = escape(query)
    
    # Use regex to find and replace the search term (case insensitive)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    highlighted = pattern.sub(f'<mark>{query}</mark>', text)
    
    return highlighted

# Get user statistics for profile page
def get_user_stats(user_id):
    """
    Get comprehensive user statistics including posts, comments, and likes
    """
    try:
        # Get post count
        post_count = Post.query.filter_by(user_id=user_id).count()
        
        # Get comment count
        comment_count = Comment.query.filter_by(user_id=user_id).count()
        
        # Get likes given count
        likes_given = db.session.execute(
            db.select(db.func.count(likes.c.post_id)).where(
                likes.c.user_id == user_id
            )
        ).scalar() or 0
        
        # Get likes received count (likes on user's posts)
        likes_received = db.session.execute(
            db.text("""
                SELECT COUNT(*) FROM likes l
                JOIN post p ON l.post_id = p.id
                WHERE p.user_id = :user_id
            """),
            {'user_id': user_id}
        ).scalar() or 0
        
        return {
            'posts': post_count,
            'comments': comment_count,
            'likes_given': likes_given,
            'likes_received': likes_received
        }
    except Exception as e:
        print(f"Error getting user stats: {e}")
        return {'posts': 0, 'comments': 0, 'likes_given': 0, 'likes_received': 0}

# Get trending posts for homepage
def get_trending_posts(limit=10):
    """
    Get posts with most engagement in the last 7 days
    """
    try:
        result = db.session.execute(
            db.text("""
                SELECT p.id, p.title, p.content, p.created_at, p.category,
                       u.username,
                       COUNT(DISTINCT l.user_id) AS like_count,
                       COUNT(DISTINCT c.id) AS comment_count,
                       (COUNT(DISTINCT l.user_id) + COUNT(DISTINCT c.id)) AS engagement_score
                FROM post p
                JOIN user u ON p.user_id = u.id
                LEFT JOIN likes l ON p.id = l.post_id AND l.created_at >= datetime('now', '-7 days')
                LEFT JOIN comment c ON p.id = c.post_id AND c.created_at >= datetime('now', '-7 days')
                WHERE p.created_at >= datetime('now', '-30 days')
                GROUP BY p.id, p.title, p.content, p.created_at, p.category, u.username
                ORDER BY engagement_score DESC, p.created_at DESC
                LIMIT :limit
            """),
            {'limit': limit}
        ).fetchall()
        
        return [dict(row._mapping) for row in result]
    except Exception as e:
        print(f"Error getting trending posts: {e}")
        return []

# Load user for login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Give current time to all web pages
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# Load user info
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Handle like and unlike for posts
def process_post_like(post_id):
    """
    Like or unlike a post
    """
    # Get the post
    post = Post.query.get_or_404(post_id)
    
    # Check if user already liked this post
    if current_user.has_liked_post(post):
        # Remove like
        success = current_user.unlike_post(post)
        action = 'unliked'
    else:
        # Add like
        success = current_user.like_post(post)
        action = 'liked'
    
    # Save to database
    db.session.commit()
    
    # Return what happened
    return success, action, post.likes.count()

def allowed_file(filename):
    """Check if file type is OK"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_uploaded_file(file, file_prefix, entity_id):
    """
    Save an uploaded file with proper naming and security checks

    Args:
        file: The uploaded file object
        file_prefix: String prefix for the filename (e.g., 'user' or 'post')
        entity_id: ID of the entity this file belongs to

    Returns:
        str: The saved filename or None if file invalid
    """
    if file and file.filename != '' and allowed_file(file.filename):
        # Create secure filename with timestamp to prevent overwrites
        extension = file.filename.rsplit('.', 1)[1].lower()
        secure_filename = f"{file_prefix}_{entity_id}_{int(datetime.utcnow().timestamp())}.{extension}"

        # Save file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename)
        file.save(file_path)
        return secure_filename
    return None

# Authentication routes
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Password validation
        if len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return redirect(url_for('signup'))
        if not re.search(r'[A-Z]', password):
            flash('Password must contain at least one uppercase letter', 'error')
            return redirect(url_for('signup'))
        if not re.search(r'[a-z]', password):
            flash('Password must contain at least one lowercase letter', 'error')
            return redirect(url_for('signup'))
        if not re.search(r'[0-9]', password):
            flash('Password must contain at least one number', 'error')
            return redirect(url_for('signup'))

        # Check if username and email already exist
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'error')
            return redirect(url_for('signup'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('signup'))

        # Create new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please log in', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember'))
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        flash('Wrong email or password', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Home page
@app.route('/')
def index():
    """Show the main page with posts."""
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', 'all')

    # Get posts by category
    query = Post.query
    if category != 'all':
        query = query.filter_by(category=category)

    # Get newest posts first
    latest_posts = query.order_by(Post.created_at.desc()).paginate(page=page, per_page=8)

    # Removed most liked posts query
    from sqlalchemy import func, desc  # Keep import, might be used elsewhere

    # Removed most commented posts query

    # Add empty lists to maintain compatibility
    most_liked_posts = []
    most_discussed_posts = []

    return render_template('index.html', 
                          posts=latest_posts, 
                          most_liked_posts=most_liked_posts, 
                          most_discussed_posts=most_discussed_posts,
                          current_category=category)

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    """Let users make a new post."""
    if request.method == 'POST':
        title = request.form['title'].strip()
        content = request.form['content'].strip()
        category = request.form.get('category', 'general')

        if len(title) < 5:
            flash('Title needs at least 5 characters', 'error')
            return redirect(url_for('create_post'))

        if len(content) < 10:
            flash('Content needs at least 10 characters', 'error')
            return redirect(url_for('create_post'))
        
        if len(content) > 5000:
            flash('Post content cannot exceed 5000 characters', 'error')
            return redirect(url_for('create_post'))

        new_post = Post(
            title=title,
            content=content,
            user_id=current_user.id,
            category=category
        )
        db.session.add(new_post)
        db.session.commit()

        # Process image upload - only allow one image
        if 'images' in request.files:
            file = request.files['images']  # Use a single file instead of a list

            # Use the encapsulated function to handle file upload
            secure_filename = save_uploaded_file(file, "post", new_post.id)

            if secure_filename:
                # Create database record
                post_image = PostImage(
                    filename=secure_filename,
                    post_id=new_post.id
                )
                db.session.add(post_image)
                db.session.commit()

        flash('Post published successfully!', 'success')
        return redirect(url_for('view_post', post_id=new_post.id))

    return render_template('create_post.html')

@app.route('/post/<int:post_id>')
def view_post(post_id):
    """Show one post."""
    post = Post.query.get_or_404(post_id)
    from datetime import datetime
    return render_template('view_post.html', post=post, now=datetime.utcnow())

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    """Let users add comments to posts."""
    # Get the post
    post = Post.query.get_or_404(post_id)
    content = request.form['content'].strip()

    # Check if comment is OK
    if len(content) < 3:
        flash('Comment needs at least 3 characters', 'error')
    elif len(content) > 1000:
        flash('Comment too long (max 1000 characters)', 'error')
    else:
        # Make content safe
        content = content.replace('<', '&lt;').replace('>', '&gt;')

        # Make new comment
        new_comment = Comment(
            content=content,
            user_id=current_user.id,
            post=post
        )
        # Save comment
        db.session.add(new_comment)
        db.session.commit()
        flash('Comment added successfully!', 'success')

    return redirect(url_for('view_post', post_id=post.id))

@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    """Like or unlike a post."""
    # Handle the like/unlike action
    success, action, likes_count = process_post_like(post_id)

# Get the post
    post = Post.query.get_or_404(post_id)

    # Check if this is an AJAX call
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        # Return JSON for AJAX calls
        return jsonify({
            'success': success, 
            'action': action, 
            'likes_count': likes_count,
            'user_has_liked': current_user.has_liked_post(post) if success else None
        })
    else:
        # Regular form - show message and redirect
        if success:
            flash(f'You have {action} this post!', 'success')

        # Go back to where user came from
        referrer = request.referrer
        if referrer and 'post/' not in referrer:
            return redirect(url_for('index'))
        return redirect(url_for('view_post', post_id=post.id))

@app.route('/api/post/<int:post_id>/likes', methods=['GET'])
def get_post_likes(post_id):
    """Get like count for a post."""
    try:
        post = Post.query.get_or_404(post_id)
        likes_count = post.likes.count()
        
        user_has_liked = False
        if current_user.is_authenticated:
            user_has_liked = current_user.has_liked_post(post)
        
        return jsonify({
            'success': True,
            'likes_count': likes_count,
            'user_has_liked': user_has_liked,
            'post_id': post_id
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/profile/<username>')
@login_required
def profile(username):
    """Show user profile page with comprehensive statistics"""
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).limit(10).all()
    
    # Get user statistics using our new function
    stats = get_user_stats(user.id)
    
    # Get user's recent comments
    recent_comments = Comment.query.filter_by(user_id=user.id).order_by(Comment.created_at.desc()).limit(5).all()
    
    return render_template('profile.html', user=user, posts=posts, stats=stats, recent_comments=recent_comments)

@app.route('/search')
def search():
    """Search for posts."""
    query = request.args.get('q', '').strip()
    if query:
        page = request.args.get('page', 1, type=int)
        posts = Post.query.filter(
            Post.title.ilike(f'%{query}%') |
            Post.content.ilike(f'%{query}%')
        ).order_by(Post.created_at.desc()).paginate(page=page, per_page=5)
    else:
        posts = []
    # Sort posts
    sort_by = request.args.get('sort', 'newest')

    return render_template('search.html', posts=posts, query=query, sort=sort_by)

@app.route('/trending')
def trending():
    """Show trending posts with most engagement"""
    trending_posts = get_trending_posts(limit=20)
    return render_template('trending.html', posts=trending_posts)

@app.route('/api/user_stats/<int:user_id>')
@login_required
def api_user_stats(user_id):
    """API endpoint to get user statistics"""
    # Only allow users to see their own stats or make it public
    if current_user.id != user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    stats = get_user_stats(user_id)
    return jsonify(stats)

@app.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('profile', username=current_user.username))

    file = request.files['avatar']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('profile', username=current_user.username))

   # Save the file
    filename = save_uploaded_file(file, "user", current_user.id)
    if filename:
        current_user.avatar = filename
        db.session.commit()
        flash('Profile picture uploaded successfully!', 'success')
    else:
        flash('Only image files allowed (png, jpg, jpeg, gif)', 'error')

    return redirect(url_for('profile', username=current_user.username))

# Other pages
@app.route('/about')
def about():
    return render_template('about.html', now=datetime.now())

@app.route('/terms')
def terms():
    return render_template('terms_of_use.html', now=datetime.now())

@app.route('/privacy')
def privacy():
    return render_template('privacy.html', now=datetime.now())

@app.route('/contact')
def contact():
    return render_template('contact.html', now=datetime.now())

@app.route('/community-rules')
def community_rules():
    """Rules page"""
    return render_template('community_rules.html', now=datetime.now())

@app.route('/faq')
def faq():
    """Help page"""
    return render_template('faq.html')
# User stuff

# Change username and delete account
@app.route('/update_username', methods=['POST'])
@login_required
def update_username():
    new_username = request.form['username'].strip()

    # Check username length
    if len(new_username) < 3:
        flash('Username must be at least 3 characters long', 'error')
        return redirect(url_for('profile', username=current_user.username))

    # Check if username is taken
    if new_username != current_user.username and User.query.filter_by(username=new_username).first():
        flash('Username already taken', 'error')
        return redirect(url_for('profile', username=current_user.username))

    # Change username
    current_user.username = new_username
    db.session.commit()
    flash('Username updated successfully!', 'success')
    return redirect(url_for('profile', username=current_user.username))

@app.route('/delete_account')
@login_required
def delete_account():
    """Delete user account forever."""
    # Delete all user posts
    Post.query.filter_by(user_id=current_user.id).delete()

    # Delete all user comments
    Comment.query.filter_by(user_id=current_user.id).delete()

    # Delete all user likes
    db.session.execute(likes.delete().where(likes.c.user_id == current_user.id))

    # Save user info before deleting
    user_id = current_user.id
    username = current_user.username

    # Log out user
    logout_user()

    # Delete user account
    User.query.filter_by(id=user_id).delete()
    db.session.commit()

    flash(f'Account {username} has been permanently deleted', 'success')
    return redirect(url_for('index'))

# AJAX like route
@app.route('/api/like/<int:post_id>', methods=['POST'])
@login_required
def api_like_post(post_id):
    """Like/unlike a post with AJAX."""
    # Get the post
    post = Post.query.get_or_404(post_id)

    # Check if user already liked the post
    if current_user.has_liked_post(post):
        # Remove like
        success = current_user.unlike_post(post)
        action = 'unliked'
    else:
        # Add like
        success = current_user.like_post(post)
        action = 'liked'

    # Save changes
    db.session.commit()

    # Send back JSON
    from flask import jsonify
    return jsonify({
        'success': success,
        'action': action,
        'likes_count': post.likes.count()
    })


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    """Let user delete their own post."""
    # Get the post
    post = Post.query.get_or_404(post_id)

    # Check if user owns this post
    if current_user.id != post.user_id:
        flash('You do not have permission to delete this post', 'error')
        return redirect(url_for('view_post', post_id=post_id))

    # Delete all comments on this post
    Comment.query.filter_by(post_id=post_id).delete()

    # Delete all pictures on this post
    post_images = PostImage.query.filter_by(post_id=post_id).all()
    for image in post_images:
        # Delete actual picture file
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"Error deleting image file {image_path}: {e}")

    # Delete the post
    db.session.delete(post)
    db.session.commit()

    # Tell user post was deleted
    flash('Post successfully deleted', 'success')

    # Go back to home page
    return redirect(url_for('index'))

# Run the app
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # Database is already set up
    port = int(os.environ.get('PORT', 8082))  # Use port 8082
    app.run(debug=True, host='0.0.0.0', port=port)