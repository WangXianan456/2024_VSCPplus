# -*- coding: utf-8 -*-
import web
import pymysql
import re
import matplotlib.pyplot as plt
import joblib
import csv
from sklearn import metrics
from sklearn.linear_model import LinearRegression
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn import svm
import hashlib
import tempfile
import mysql.connector
from datetime import datetime
import sys
from sklearn.decomposition import PCA
import redis
from pymongo import MongoClient
from sklearn.preprocessing import StandardScaler
import time
import os
from redis.lock import Lock
from pymilvus import Milvus,connections, Collection, FieldSchema, CollectionSchema, DataType, utility
import phoenixdb
import phoenixdb.cursor


def sqlSelect(sql):
    conn = pymysql.connect(host='localhost', port=3306, user='root', passwd='123456', db='calculater')
    cur = conn.cursor()
    cur.execute(sql)
    sqlData = cur.fetchall()
    cur.close()
    conn.close()
    return sqlData


def sqlWrite(sql):
    conn = pymysql.connect(host='localhost', port=3306, user='root', passwd='123456', db='calculater')
    cur = conn.cursor()
    cur.execute(sql)
    cur.close()
    conn.commit()
    conn.close()
    return

def connect_db():
    try:
        # 对于较新的 PyMySQL 版本
        return pymysql.connect(
            host='localhost',
            port=3306,
            user='root',
            password='123456',
            db='calculater',
            charset='utf8mb4',
         
        )
    except pymysql.Error as err:
        print(f"Database error: {err}")
        return None
    
def get_available_datasets():
    db = connect_db()
    if not db:
        return []
    try:
        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT id, dataset_name FROM datasets ORDER BY dataset_name")
            datasets = cursor.fetchall()
            # 将 'dataset_name' 重命名为 'name' 以便在模板中更简洁地使用
            return [{'id': d['id'], 'name': d['dataset_name']} for d in datasets]
    except Exception as e:
        print(f"获取可用数据集时出错: {e}")
        return []
    finally:
        db.close()
        
# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# MongoDB connection
mongo_client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
mongo_db = mongo_client['stat_education']
mongo_preferences = mongo_db['user_preferences']
mongo_analysis_history = mongo_db['analysis_history']

# Milvus connection (compatible with 2.3.x)
connections.connect(alias="default", host='localhost', port='19530')

collection_name = 'dataset_embeddings'

# Initialize Milvus collection (modern API)

if not utility.has_collection(collection_name):
    print(f"创建新集合: {collection_name}")
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=64)
    ]
    schema = CollectionSchema(fields)
    milvus_collection = Collection(collection_name, schema)
    
    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "L2",
        "params": {"nlist": 1024}
    }
    milvus_collection.create_index("embedding", index_params)
else:
    print(f"集合已存在: {collection_name}")
    milvus_collection = Collection(collection_name)
    milvus_collection.load()
    
# MySQL connection

# MySQL connection (MySQL 8.4 compatible)
def connect_db():
    try:
        # 对于较新的 PyMySQL 版本
        return pymysql.connect(
            host='localhost',
            port=3306,
            user='root',
            password='123456',
            db='calculater',
            charset='utf8mb4',
        
        )
    except pymysql.Error as err:
        print(f"Database error: {err}")
        return None

# Redis distributed lock
def acquire_lock(lock_name, timeout=10):
    lock_key = f"lock:{lock_name}"
    lock_value = str(time.time())
    if redis_client.setnx(lock_key, lock_value):
        redis_client.expire(lock_key, timeout)
        return True
    return False

def release_lock(lock_name):
    lock_key = f"lock:{lock_name}"
    redis_client.delete(lock_key)

# Custom JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Fetch analysis history from MySQL
def fetch_mysql_history(username):
    db = connect_db()
    if not db:
        return []
    
    cursor = db.cursor(pymysql.cursors.DictCursor) 
    history = []
    
    # Fetch from linears table
    cursor.execute("""
        SELECT 'Linear Regression' AS model, input_time AS timestamp
        FROM linears
        JOIN user ON linears.user_id = user.id
        WHERE user.username = %s
    """, (username,))
    history.extend(cursor.fetchall())
    
    # Fetch from fisher table
    cursor.execute("""
        SELECT 'Fisher Discriminant' AS model, input_time AS timestamp
        FROM fisher
        JOIN user ON fisher.user_id = user.id
        WHERE user.username = %s
    """, (username,))
    history.extend(cursor.fetchall())
    
    # Fetch from logistic table
    cursor.execute("""
        SELECT 'Logistic Regression' AS model, input_time AS timestamp
        FROM logistic
        JOIN user ON logistic.user_id = user.id
        WHERE user.username = %s
    """, (username,))
    history.extend(cursor.fetchall())
    
    # Fetch from svm table
    cursor.execute("""
        SELECT 'SVM' AS model, input_time AS timestamp
        FROM svm
        JOIN user ON svm.user_id = user.id
        WHERE user.username = %s
    """, (username,))
    history.extend(cursor.fetchall())
    
    cursor.close()
    db.close()
    
    # Convert timestamps to datetime objects
    for item in history:
        if isinstance(item['timestamp'], str):
            try:
                item['timestamp'] = datetime.strptime(item['timestamp'], '%Y-%m-%d %H:%M:%S')
            except:
                pass
                
    return sorted(history, key=lambda x: x['timestamp'], reverse=True)[:5]  # Limit to recent 5

def generate_recommendations_for_user(username):
    """为指定用户生成推荐数据"""
    print(f"开始为用户 {username} 生成推荐数据...")
    user_prefs = mongo_preferences.find_one({'username': username}) or {'preferred_models': []}
    mysql_history = fetch_mysql_history(username)
    mongo_history = list(mongo_analysis_history.find({'username': username}).sort('timestamp', -1).limit(5))
    
    combined_history = []
    seen = set()
    for item in mysql_history + mongo_history:
        key = f"{item['model']}_{item['timestamp']}"
        if key not in seen:
            combined_history.append(item)
            seen.add(key)
    combined_history = sorted(combined_history, key=lambda x: x['timestamp'], reverse=True)[:5]
    
    query_vector = np.random.rand(1, 64)
    scaler = StandardScaler()
    query_vector = scaler.fit_transform(query_vector)[0].tolist()
    
    search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
    results = milvus_collection.search(
        data=[query_vector],
        anns_field="embedding",
        param=search_params,
        limit=5,
        output_fields=["id"]
    )
    
    recommended_datasets = [hit.id for hits in results for hit in hits]
    
    model_counts = {}
    for item in combined_history:
        model = item['model']
        model_counts[model] = model_counts.get(model, 0) + 1
    recommended_models = user_prefs.get('preferred_models', []) + list(model_counts.keys())
    recommended_models = list(dict.fromkeys(recommended_models))[:3]
    
    recommendations = {
        'models': recommended_models,
        'datasets': recommended_datasets,
        'confidence': [0.9 - i * 0.05 for i in range(len(recommended_models))]
    }
    
    print(f"为用户 {username} 生成推荐数据完成: {recommendations}")
    return recommendations

# Add new route to urls
urls = (
    '/static/(.*)', 'static',  # Add static files route
    '/Recommendation.html', 'Recommendation',
    '/saveRecommendation', 'SaveRecommendation'
)

# Static file handler
class static:
    def GET(self, path):
        try:
            web.header('Content-Type', 'application/javascript; charset=UTF-8')
            return open('static/' + path, 'rb').read()
        except IOError:
            raise web.notfound()

# Initialize web application components FIRST
app = web.application(urls, globals())
store = web.session.DiskStore('sessions')  # Use persistent directory
session = web.session.Session(app, store)
render = web.template.render('templates/')
web.config.debug = False


class TriggerRecommendation:
    def POST(self):
        web.header('Content-Type', 'application/json')
        if not session.get('logged_in'):
            return json.dumps({'status': 'error', 'message': 'Not logged in'})
        
        username = session.get('username')
        task_in_progress_key = f"recom:task_in_progress:{username}"
        cache_key = f"recom:model_data:{username}"

        # 新增：判断是否为强制刷新
        try:
            data = json.loads(web.data())
        except Exception:
            data = {}
        force = data.get('force', False)

        # 如果是强制刷新，先删除缓存和任务标记
        if force:
            redis_client.delete(cache_key)
            redis_client.delete(task_in_progress_key)

        # 如果结果已经存在，没必要重新生成（除非force）
        if not force and redis_client.exists(cache_key):
            return json.dumps({'status': 'info', 'message': 'Recommendation already exists.'})

        # 如果任务已经在进行中，也告知前端
        if redis_client.exists(task_in_progress_key):
            return json.dumps({'status': 'info', 'message': 'Task already in progress.'})

        print(f"为用户 '{username}' 创建推荐任务。")
        task = {'username': username}
        redis_client.lpush("recom:task_queue", json.dumps(task))
        # 标记任务已推送，10分钟过期
        redis_client.setex(task_in_progress_key, 600, "1") 
        print("任务已推送到队列。")
        return json.dumps({'status': 'pending', 'message': 'Recommendation task started.'})

class CheckRecommendationStatus:
    def GET(self):
        if not session.get('logged_in'):
            return json.dumps({'status': 'error', 'message': 'Not logged in'})
        
        username = session.get('username')
        cache_key = f"recom:model_data:{username}"
        task_in_progress_key = f"recom:task_in_progress:{username}"
        
        if redis_client.exists(cache_key):
            return json.dumps({'status': 'ready'})
        elif redis_client.exists(task_in_progress_key):
            return json.dumps({'status': 'pending'})
        else:
            # 如果既没有结果也没有进行中的任务，可以认为是初始状态
            # 或者根据您的业务逻辑返回 'initial'
            return json.dumps({'status': 'initial'})

# 新增一个类来处理生成请求，这比在GET请求中创建任务更好
class GenerateRecommendation:
    def POST(self):
        web.header('Content-Type', 'application/json')
        if not session.get('logged_in'):
            return json.dumps({'status': 'error', 'message': 'Not logged in'})
        
        username = session.get('username')
        task_in_progress_key = f"recom:task_in_progress:{username}"

        if redis_client.exists(task_in_progress_key):
            return json.dumps({'status': 'info', 'message': 'Task already in progress'})

        print(f"为用户 '{username}' 创建推荐任务。")
        task = {'username': username}
        redis_client.lpush("recom:task_queue", json.dumps(task))
        # 标记任务已推送，10分钟过期
        redis_client.setex(task_in_progress_key, 600, "1") 
        print("任务已推送到队列。")
        return json.dumps({'status': 'success', 'message': 'Task started'})

# --- 请用下面的代码块完全替换您现有的 Recommendation 类 ---
class Recommendation:
    def GET(self):
        if not session.get('logged_in'):
            # 理论上应该重定向到登录页，但这里保持与您原来一致
            return "用户未登录，请登录后再试。"
            
        username = session.get('username')
        print(f"用户 '{username}' 请求推荐页面")

        # 1. 确定当前状态
        status = ''
        recommendations = None
        
        cache_key = f"recom:model_data:{username}"
        task_in_progress_key = f"recom:task_in_progress:{username}"

        if redis_client.exists(cache_key):
            status = 'ready'
            print(f"状态: ready (命中缓存: {cache_key})")
            cached_results = redis_client.get(cache_key)
            recommendations = json.loads(cached_results)
        elif redis_client.exists(task_in_progress_key):
            status = 'pending'
            print(f"状态: pending (任务进行中: {task_in_progress_key})")
        else:
            status = 'initial'
            print("状态: initial (无缓存或进行中的任务)")

        # 2. 准备模板所需的所有数据
        # 即使在非 'ready' 状态下，也传递一个空列表，避免模板出错
        available_datasets = get_available_datasets() if status == 'ready' else []

        # 3. 使用确定的状态，调用唯一的模板
        return render.Recommendation(
            username=username, 
            recommendations=recommendations, 
            json=json, 
            available_datasets=available_datasets, 
            status=status
        )

    def POST(self):
        # POST方法保持不变
        if session.get('logged_in'):
            username = session.get('username')
            data = json.loads(web.data())
            model = data.get('model')
            dataset_id = data.get('dataset_id')
            
            lock = Lock(redis_client, f"recommendation:{username}", timeout=10)
            if lock.acquire(blocking=False):
                try:
                    mongo_preferences.update_one(
                        {'username': username},
                        {
                            '$set': {
                                'preferred_models': [model],
                                'last_updated': datetime.now()
                            },
                            '$setOnInsert': {'created_at': datetime.now()}
                        },
                        upsert=True
                    )
                    mongo_analysis_history.insert_one({
                        'username': username,
                        'model': model,
                        'dataset_id': dataset_id,
                        'timestamp': datetime.now()
                    })
                    return json.dumps({'success': True})
                finally:
                    lock.release()
            else:
                return json.dumps({'success': False, 'message': '无法获取锁，请稍后重试'})
        else:
            return json.dumps({'success': False, 'message': '用户未登录'})


class SaveRecommendation:
    def POST(self):
        if session.get('logged_in'):
            username = session.get('username')
            data = json.loads(web.data())
            model = data.get('model')
            dataset_id = data.get('dataset_id')
            
            mongo_analysis_history.insert_one({
                'username': username,
                'model': model,
                'dataset_id': dataset_id,
                'timestamp': datetime.now()
            })

            return json.dumps({'success': True, 'message': '偏好已成功保存！'})
        else:

            return json.dumps({'success': False, 'message': '用户未登录'})
        
class compare_models:
    def POST(self):
        """
        处理模型比较请求。
        从前端接收一个数据集名称和多个模型名称，
        从数据库查询它们的性能分数并返回。
        """
        web.header('Content-Type', 'application/json')
        
        try:
            data = json.loads(web.data())
            dataset_name = data.get('dataset_name')
            selected_models = data.get('models')

            if not dataset_name or not selected_models:
                web.ctx.status = '400 Bad Request'
                return json.dumps({"error": "缺少数据集或模型名称"})

            db = connect_db()
            if not db:
                web.ctx.status = '500 Internal Server Error'
                return json.dumps({"error": "数据库连接失败"})

            with db.cursor() as cursor:
                # 使用参数化查询来防止SQL注入
                # 为 IN 子句创建占位符
                placeholders = ', '.join(['%s'] * len(selected_models))
                
                sql = f"""
                    SELECT 
                        model_name AS model, 
                        metric_name, 
                        score 
                    FROM 
                        model_performance 
                    WHERE 
                        dataset_name = %s AND model_name IN ({placeholders})
                """
                
                # 组合查询参数
                params = [dataset_name] + selected_models
                
                cursor.execute(sql, params)
                results = cursor.fetchall()
                
                return json.dumps(results)

        except json.JSONDecodeError:
            web.ctx.status = '400 Bad Request'
            return json.dumps({"error": "无效的JSON请求"})
        except Exception as e:
            print(f"比较模型时出错: {e}")
            web.ctx.status = '500 Internal Server Error'
            return json.dumps({"error": f"服务器内部错误: {e}"})
        finally:
            if 'db' in locals() and db.open:
                db.close()
                
web.config.debug = False
app = web.application(urls, globals())
root = tempfile.mkdtemp()
store = web.session.DiskStore('sessions')  
session = web.session.Session(app, store)

# calculator.py (文件末尾)
render = web.template.render('templates/', globals={
    'session': session
})

render_pending = web.template.render('templates/')
if __name__ == "__main__":
    # Create sessions directory if not exists
    if not os.path.exists('sessions'):
        os.makedirs('sessions')
    
    web.httpserver.runsimple(app.wsgifunc(), ("127.0.0.1", 8080))
    app.run()