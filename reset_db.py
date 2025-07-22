import os
import sys
import shutil

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 获取数据库文件路径
COMMUNITY_DB = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'community.db')
CONTENT_DB = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'content.db')

def reset_db():
    """删除并重新创建数据库"""
    # 删除现有数据库文件
    for db_file in [COMMUNITY_DB, CONTENT_DB]:
        if os.path.exists(db_file):
            print(f"删除数据库文件: {db_file}")
            os.remove(db_file)

    print("数据库文件已删除。启动应用程序将自动创建新的数据库。")
    print("请运行: python app.py")

if __name__ == "__main__":
    confirm = input("这将删除所有数据库数据。确定要继续吗? (y/n): ")
    if confirm.lower() == 'y':
        reset_db()
    else:
        print("操作已取消")
