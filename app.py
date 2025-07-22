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
    db.Column('post_id', db.Integer, primary_key=True),  # 移除跨数据库外键
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

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
        if not self.has_liked_post(post):
            self.liked_posts.append(post)
            return True
        return False

    def unlike_post(self, post):
        if self.has_liked_post(post):
            self.liked_posts.remove(post)
            return True
        return False

    def has_liked_post(self, post):
        return self.liked_posts.filter(
            likes.c.post_id == post.id
        ).count() > 0

# Post model
class Post(db.Model):
    __bind_key__ = 'content_db'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    # 使用简单整数列，不使用外键约束（跨数据库）
    user_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), nullable=False, default='general')
    comments = db.relationship('Comment', backref='post', lazy=True, cascade="all, delete-orphan")

# Comment model
class Comment(db.Model):
    __bind_key__ = 'content_db'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    # 跨数据库关系，不使用外键约束
    user_id = db.Column(db.Integer, nullable=False)
    # Same-database foreign key to content.db
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', name='fk_comment_post'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 稍后在应用初始化完成后创建数据库表
def init_db():
    with app.app_context():
        try:
            # 先创建主数据库表
            db.create_all()
            # 然后创建内容数据库表
            db.create_all(bind='content_db')
            print("数据库表创建成功")
        except Exception as e:
            print(f"数据库初始化错误: {e}")

# 在应用初始化后调用init_db

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and            filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

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

    return render_template('signup_enhanced.html')

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

    return render_template('login_enhanced.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Main route
@app.route('/')
def index():
    """
    首页路由 - 显示帖子列表，支持分页和分类筛选
    等效SQL:
    - 所有分类: SELECT * FROM post ORDER BY created_at DESC LIMIT 8 OFFSET (page-1)*8
    - 特定分类: SELECT * FROM post WHERE category = :category ORDER BY created_at DESC LIMIT 8 OFFSET (page-1)*8
    """
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', 'all')

    # 构建查询 - 筛选特定分类
    query = Post.query
    if category != 'all':
        query = query.filter_by(category=category)

    # 排序并分页 - 确保最新的帖子显示在前面
    posts = query.order_by(Post.created_at.desc()).paginate(page=page, per_page=8)
    return render_template('index_enhanced.html', posts=posts, current_category=category)

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
        flash('Post published successfully!', 'success')
        return redirect(url_for('view_post', post_id=new_post.id))

    return render_template('create_post.html')

@app.route('/post/<int:post_id>')
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('view_post_simple.html', post=post)

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    """
    添加评论功能
    等效SQL:
    1. 检索帖子: SELECT * FROM post WHERE id = :post_id LIMIT 1
    2. 插入评论: INSERT INTO comment (content, user_id, post_id, created_at) 
                VALUES (:content, :user_id, :post_id, CURRENT_TIMESTAMP)
    """
    # 检索帖子并确保存在
    post = Post.query.get_or_404(post_id)
    content = request.form['content'].strip()

    # 数据验证 - 确保评论内容有效
    if len(content) < 3:
        flash('Comment needs at least 3 characters', 'error')
    elif len(content) > 1000:  # 添加额外验证
        flash('Comment too long (max 1000 characters)', 'error')
    else:
        # 防止HTML注入
        content = content.replace('<', '&lt;').replace('>', '&gt;')

        # 创建新评论
        new_comment = Comment(
            content=content,
            user_id=current_user.id,
            post=post
        )
        # 保存到数据库
        db.session.add(new_comment)
        db.session.commit()
        flash('Comment added successfully!', 'success')

    return redirect(url_for('view_post', post_id=post.id))

@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    """
    点赞/取消点赞功能 - 使用Many-To-Many关系
    等效SQL:
    1. 检查是否已点赞: 
       SELECT COUNT(*) FROM likes 
       WHERE user_id = :user_id AND post_id = :post_id

    2. 添加点赞:
       INSERT INTO likes (user_id, post_id, created_at)
       VALUES (:user_id, :post_id, CURRENT_TIMESTAMP)

    3. 取消点赞:
       DELETE FROM likes 
       WHERE user_id = :user_id AND post_id = :post_id
    """
    # 确保帖子存在
    post = Post.query.get_or_404(post_id)

    # 检查用户是否已经点赞（利用many-to-many关系）
    if current_user.has_liked_post(post):
        # 取消点赞
        success = current_user.unlike_post(post)
        action = 'unliked'
    else:
        # 添加点赞
        success = current_user.like_post(post)
        action = 'liked'

    # 保存关系变更到数据库
    db.session.commit()

    # 通知用户操作结果
    if success:
        flash(f'You have {action} this post!', 'success')

    return redirect(url_for('view_post', post_id=post.id))

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).paginate(page=page, per_page=5)
    return render_template('profile.html', user=user, posts=posts)

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
    return render_template('search.html', posts=posts, query=query)

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

    if file and allowed_file(file.filename):
        filename = f"user_{current_user.id}.{file.filename.rsplit('.', 1)[1].lower()}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        current_user.avatar = filename
        db.session.commit()
        flash('Profile picture uploaded successfully!', 'success')
    else:
        flash('Only image files allowed (png, jpg, jpeg, gif)', 'error')

    return redirect(url_for('profile', username=current_user.username))

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # 初始化数据库
    init_db()
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
