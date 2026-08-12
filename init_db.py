# init_db.py
import os
from database import Base, engine  # 假设 database.py 里导出了 Base 和 engine
# 如果 database.py 里名字不一样，下面会报错，把报错发我

def init():
    # 确保数据目录存在（如果需要）
    db_path = "bimuyu.db"
    if os.path.exists(db_path):
        print(f"数据库已存在：{db_path}，跳过创建表结构（若需重建请删掉该文件）")
    else:
        Base.metadata.create_all(bind=engine)
        print(f"已创建数据库和表：{db_path}")

if __name__ == "__main__":
    init()