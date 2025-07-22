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

# Initialize Flask app
app = Flask(__name__)

# App configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'my-high-school-project-2023')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'community.db')
app.config['SQLALCHEMY_BINDS'] = {
    'content_db': 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'content.db')
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Initialize extensions
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
migrate = Migrate(app, db)

# Login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Likes association table
likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('post_id', db.Integer, primary_key=True),  # Removed cross-database foreign key
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

# Database initialization function
def init_db():
    """Create all database tables."""
    with app.app_context():
        try:
            # Create all database tables (main database and bound databases)
            db.create_all()
            print("Database tables created successfully")
        except Exception as e:
            print(f"Database initialization error: {e}")

# Initialize database when running this file directly
if __name__ == "__main__":
    init_db()

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    avatar = db.Column(db.String(120))

    # Cross-database relationship to content.db
    posts = db.relationship('Post', backref='author', lazy=True,
                          primaryjoin="User.id == foreign(Post.user_id)", viewonly=True)
    # Cross-database relationship to content.db
    comments = db.relationship('Comment', backref='author', lazy=True,
                            primaryjoin="User.id == foreign(Comment.user_id)", viewonly=True)
    # Cross-database many-to-many relationship
    liked_posts = db.relationship(
        'Post',
        secondary=likes,
        backref=db.backref('likes', lazy='dynamic'),
        lazy='dynamic',
        primaryjoin="User.id == foreign(likes.c.user_id)",
        secondaryjoin="foreign(Post.id) == likes.c.post_id",
        viewonly=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def like_post(self, post):
        try:
            if not self.has_liked_post(post):
                self.liked_posts.append(post)
                return True
            return False
        except Exception:
            # if error happens, return to False
            return False

    def unlike_post(self, post):
        try:
            if self.has_liked_post(post):
                self.liked_posts.remove(post)
                return True
            return False
        except Exception:
            # if error happens return to False
            return False

    def has_liked_post(self, post):
        try:
            return self.liked_posts.filter(
                likes.c.post_id == post.id
            ).count() > 0
        except Exception:
            # if there is no error, or error happens, return to False
            return False

# Post model
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

# Comment model
class Comment(db.Model):
    __bind_key__ = 'content_db'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    # links multi database
    user_id = db.Column(db.Integer, nullable=False)
    # Same-database foreign key to content.db
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', name='fk_comment_post'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Helper function to highlight query keywords in search results
@app.template_filter('highlight')
def highlight(text, query):
    """
    Highlight parts of the text that contain the query keyword
    :param text: Original text
    :param query: Query keyword
    :return: HTML with highlighted text
    """
    # Prevent XSS attacks by escaping HTML
    text = escape(text)
    query = escape(query)

    # Case-insensitive replacement
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    result = pattern.sub(f'<span class="highlight-match">{query}</span>', text)

    return result
# Like association table

# Ensure the database is initialized immediately when the app starts
init_db()

# Provide current time to all templates via context processor
@app.context_processor
def inject_now():
    return {'now': datetime.now()}
# User model
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper function for handling post likes
def process_post_like(post_id):
    """
    Process like/unlike functionality for a post

    Args:
        post_id: ID of the post to like/unlike

    Returns:
        tuple: (success, action, likes_count)
            - success: Boolean indicating if the operation was successful
            - action: String 'liked' or 'unliked'
            - likes_count: Updated count of likes for the post
    """
    # Ensure post exists
    post = Post.query.get_or_404(post_id)

    # Check if user already liked the post
    if current_user.has_liked_post(post):
        # Unlike
        success = current_user.unlike_post(post)
        action = 'unliked'
    else:
        # Like
        success = current_user.like_post(post)
        action = 'liked'

    # Save relationship change to database
    db.session.commit()

    return success, action, post.likes.count()

def allowed_file(filename):
    """Check if the file extension is allowed"""
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

# Main route
@app.route('/')
def index():
    """
    Home page route - Displays list of posts with pagination and category filtering
    Equivalent SQL:
    - All categories: SELECT * FROM post ORDER BY created_at DESC LIMIT 8 OFFSET (page-1)*8
    - Specific category: SELECT * FROM post WHERE category = :category ORDER BY created_at DESC LIMIT 8 OFFSET (page-1)*8
    """
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', 'all')

    # Build query - filter by specific category
    query = Post.query
    if category != 'all':
        query = query.filter_by(category=category)

    # Latest posts - ordered by creation time descending
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
    post = Post.query.get_or_404(post_id)
    from datetime import datetime
    return render_template('view_post.html', post=post, now=datetime.utcnow())

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    """
    Add comment functionality
    Equivalent SQL:
    1. Retrieve post: SELECT * FROM post WHERE id = :post_id LIMIT 1
    2. Insert comment: INSERT INTO comment (content, user_id, post_id, created_at) 
                       VALUES (:content, :user_id, :post_id, CURRENT_TIMESTAMP)
    """
    # Retrieve the post and ensure it exists
    post = Post.query.get_or_404(post_id)
    content = request.form['content'].strip()

    # Data validation - ensure comment content is valid
    if len(content) < 3:
        flash('Comment needs at least 3 characters', 'error')
    elif len(content) > 1000:  # Additional validation
        flash('Comment too long (max 1000 characters)', 'error')
    else:
        # Prevent HTML injection
        content = content.replace('<', '&lt;').replace('>', '&gt;')

        # Create new comment
        new_comment = Comment(
            content=content,
            user_id=current_user.id,
            post=post
        )
        # Save to database
        db.session.add(new_comment)
        db.session.commit()
        flash('Comment added successfully!', 'success')

    return redirect(url_for('view_post', post_id=post.id))

@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    """
    Like/Unlike functionality - using Many-To-Many relationship
    Equivalent SQL:
    1. Check if already liked: 
       SELECT COUNT(*) FROM likes 
       WHERE user_id = :user_id AND post_id = :post_id

    2. Add like:
       INSERT INTO likes (user_id, post_id, created_at)
       VALUES (:user_id, :post_id, CURRENT_TIMESTAMP)

    3. Remove like:
       DELETE FROM likes 
       WHERE user_id = :user_id AND post_id = :post_id
    """
    # Use a generic processing function to handle like/unlike actions
    success, action, likes_count = process_post_like(post_id)

    # 获取原始post对象用于重定向
    post = Post.query.get_or_404(post_id)

    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        # Return JSON response for AJAX requests
        return jsonify({
            'success': success, 
            'action': action, 
            'likes_count': likes_count
        })
    else:
        # Regular form submission - redirect with flash message
        if success:
            flash(f'You have {action} this post!', 'success')

        # Try to determine if request came from index page or post view
        referrer = request.referrer
        if referrer and 'post/' not in referrer:
            return redirect(url_for('index'))
        return redirect(url_for('view_post', post_id=post.id))

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).paginate(page=page, per_page=5)

    # Get user's comments
    comments = Comment.query.filter_by(user_id=user.id).order_by(Comment.created_at.desc()).all()

    return render_template('profile.html', user=user, posts=posts, comments=comments)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if query:
        page = request.args.get('page', 1, type=int)
        posts = Post.query.filter(
            Post.title.ilike(f'%{query}%') |
            Post.content.ilike(f'%{query}%')
        ).order_by(Post.created_at.desc()).paginate(page=page, per_page=5)
    else:
        posts = []
    # Add sorting functionality
    sort_by = request.args.get('sort', 'newest')

    return render_template('search.html', posts=posts, query=query, sort=sort_by)

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

    # 使用封装的函数处理文件上传
    filename = save_uploaded_file(file, "user", current_user.id)
    if filename:
        current_user.avatar = filename
        db.session.commit()
        flash('Profile picture uploaded successfully!', 'success')
    else:
        flash('Only image files allowed (png, jpg, jpeg, gif)', 'error')

    return redirect(url_for('profile', username=current_user.username))

# Footer page routes
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
    """Community Rules page"""
    return render_template('community_rules.html', now=datetime.now())
# User profile routes

# Username update and account deletion routes
@app.route('/update_username', methods=['POST'])
@login_required
def update_username():
    new_username = request.form['username'].strip()

    # Validate username length
    if len(new_username) < 3:
        flash('Username must be at least 3 characters long', 'error')
        return redirect(url_for('profile', username=current_user.username))

    # Check if the username is already taken
    if new_username != current_user.username and User.query.filter_by(username=new_username).first():
        flash('Username already taken', 'error')
        return redirect(url_for('profile', username=current_user.username))

    # Update username
    current_user.username = new_username
    db.session.commit()
    flash('Username updated successfully!', 'success')
    return redirect(url_for('profile', username=current_user.username))

@app.route('/delete_account')
@login_required
def delete_account():
    # Delete all posts by the user
    Post.query.filter_by(user_id=current_user.id).delete()

    # Delete all comments by the user
    Comment.query.filter_by(user_id=current_user.id).delete()

    # Save user ID so we can access it after deleting the user
    user_id = current_user.id
    username = current_user.username

    # Log out the user
    logout_user()

    # Delete user account
    User.query.filter_by(id=user_id).delete()
    db.session.commit()

    flash(f'Account {username} has been permanently deleted', 'success')
    return redirect(url_for('index'))

# Improved like route with AJAX support
@app.route('/api/like/<int:post_id>', methods=['POST'])
@login_required
def api_like_post(post_id):
    """
    AJAX version of like/unlike functionality
    Returns JSON response for client-side processing
    """
    # Ensure post exists
    post = Post.query.get_or_404(post_id)

    # Check if user already liked the post
    if current_user.has_liked_post(post):
        # Unlike
        success = current_user.unlike_post(post)
        action = 'unliked'
    else:
        # Like
        success = current_user.like_post(post)
        action = 'liked'

    # Save relationship change to database
    db.session.commit()

    # Return JSON response
    from flask import jsonify
    return jsonify({
        'success': success,
        'action': action,
        'likes_count': post.likes.count()
    })


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    """
    Delete Post Function
    1. Check if user is the post author
    2. Delete post and all its comments
    3. Redirect back to home page
    """
    # Get the post
    post = Post.query.get_or_404(post_id)

    # Check if current user is the post author
    if current_user.id != post.user_id:
        flash('You do not have permission to delete this post', 'error')
        return redirect(url_for('view_post', post_id=post_id))

    # Delete all comments for this post
    Comment.query.filter_by(post_id=post_id).delete()

    # Delete all images associated with the post
    post_images = PostImage.query.filter_by(post_id=post_id).all()
    for image in post_images:
        # 删除实际的图片文件
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"Error deleting image file {image_path}: {e}")

    # Delete the post (will cascade delete post_images records due to relationship)
    db.session.delete(post)
    db.session.commit()

    # Tell user the post was deleted
    flash('Post successfully deleted', 'success')

    # Go back to home page
    return redirect(url_for('index'))

# Note: These routes have already been defined above

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # The database has already been initialized earlier
    port = int(os.environ.get('PORT', 8082))  # Change default port to 8082
    app.run(debug=True, host='0.0.0.0', port=port)
# Note: The database has already been initialized earlier