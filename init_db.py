import os
import sys
from app import app, db, User, Post, Comment

with app.app_context():
    # Delete all tables (if exist) in both databases
    db.drop_all()
    db.drop_all(bind=['content_db'])
    
    # Create all tables in both databases
    db.create_all()
    db.create_all(bind=['content_db'])
    
    # Add test users
    user1 = User(username="Teacher", email="teacher@school.com")
    user1.set_password("teacher123")
    db.session.add(user1)
    
    user2 = User(username="Student A", email="student1@school.com")
    user2.set_password("student123")
    db.session.add(user2)
    
    # Add test posts
    post1 = Post(title="Welcome to School Community", 
                content="这是第一个测试帖子，请大家遵守规则！",
                author=user1)
    db.session.add(post1)
    
    post2 = Post(title="作业求助", 
                content="数学作业第5题有人会吗？",
                author=user2)
    db.session.add(post2)
    
    # 提交到数据库
    db.session.commit()
    print("✅ Database initialized!")
    print(f"- 2 users (teacher/student)")
    print(f"- 2 posts")
    print(f"File size: {os.path.getsize('database.db')} bytes")