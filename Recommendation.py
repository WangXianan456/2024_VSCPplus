
# -*- coding: utf-8 -*-
import web
import pymysql
import redis
from pymongo import MongoClient
from pymilvus import Milvus, IndexType, MetricType
import numpy as np
import json
from sklearn.preprocessing import StandardScaler
import hashlib
import time
from datetime import datetime
import tempfile

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# MongoDB connection
mongo_client = MongoClient('mongodb://localhost:27017/')
mongo_db = mongo_client['stat_education']
mongo_preferences = mongo_db['user_preferences']
mongo_history = mongo_db['analysis_history']

# Milvus connection
milvus_client = Milvus(host='localhost', port='19530')
collection_name = 'dataset_embeddings'
if not milvus_client.has_collection(collection_name):
    milvus_client.create_collection({
        'collection_name': collection_name,
        'dimension': 64,  # Example dimension for dataset embeddings
        'index_file_size': 1024,
        'metric_type': MetricType.L2
    })
    milvus_client.create_index(collection_name, IndexType.IVF_FLAT, {'nlist': 1024})

# MySQL connection
def connect_db():
    try:
        return pymysql.connect(host='localhost', port=3306, user='root', passwd='123456', db='calculater')
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

# Fetch analysis history from MySQL
def fetch_mysql_history(username):
    db = connect_db()
    if not db:
        return []
    
    cursor = db.cursor(dictionary=True)
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
    return sorted(history, key=lambda x: x['timestamp'], reverse=True)[:5]  # Limit to recent 5

# Add new route to urls
urls = (
    '/Recommendation.html', 'Recommendation',
    '/saveRecommendation', 'SaveRecommendation'
)

class Recommendation:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')
            # Check Redis cache for recommendations
            cache_key = f"recommendations:{username}"
            cached_results = redis_client.get(cache_key)
            if cached_results:
                return render.Recommendation(username, json.loads(cached_results))
            
            # Fetch user preferences from MongoDB
            user_prefs = mongo_preferences.find_one({'username': username}) or {'preferred_models': []}
            
            # Fetch history from MySQL and MongoDB
            mysql_history = fetch_mysql_history(username)
            mongo_history = list(mongo_history.find({'username': username}).sort('timestamp', -1).limit(5))
            
            # Combine and deduplicate history
            combined_history = []
            seen = set()
            for item in mysql_history + mongo_history:
                key = f"{item['model']}_{item['timestamp']}"
                if key not in seen:
                    combined_history.append(item)
                    seen.add(key)
            combined_history = sorted(combined_history, key=lambda x: x['timestamp'], reverse=True)[:5]
            
            # Generate dataset embedding (simplified)
            dataset = np.random.rand(1, 64)  # Replace with actual dataset embedding
            scaler = StandardScaler()
            dataset = scaler.fit_transform(dataset)
            
            # Query Milvus for similar datasets
            milvus_client.insert(collection_name, dataset.tolist())
            search_params = {'nprobe': 10}
            results = milvus_client.search(collection_name, dataset.tolist(), 5, MetricType.L2, search_params)
            recommended_datasets = [result.id for result in results[0]]
            
            # Generate recommendations based on history and preferences
            model_counts = {}
            for item in combined_history:
                model = item['model']
                model_counts[model] = model_counts.get(model, 0) + 1
            recommended_models = user_prefs.get('preferred_models', []) + list(model_counts.keys())
            recommended_models = list(dict.fromkeys(recommended_models))[:3]  # Deduplicate and limit
            
            recommendations = {
                'models': recommended_models,
                'datasets': recommended_datasets,
                'confidence': [0.9 - i * 0.05 for i in range(len(recommended_models))]  # Example confidence
            }
            
            # Cache recommendations in Redis
            redis_client.setex(cache_key, 3600, json.dumps(recommendations))
            return render.Recommendation(username, recommendations)
        else:
            return "用户未登录，请登录后再试。"

    def POST(self):
        if session.get('logged_in'):
            username = session.get('username')
            data = json.loads(web.data())
            model = data.get('model')
            dataset_id = data.get('dataset_id')
            
            # Acquire distributed lock
            if acquire_lock(f"recommendation:{username}"):
                try:
                    # Save preference to MongoDB
                    mongo_preferences.update_one(
                        {'username': username},
                        {'$set': {'preferred_models': [model], 'last_updated': datetime.now()}},
                        upsert=True
                    )
                    # Save analysis history to MongoDB
                    mongo_history.insert_one({
                        'username': username,
                        'model': model,
                        'dataset_id': dataset_id,
                        'timestamp': datetime.now()
                    })
                    return json.dumps({'success': True})
                finally:
                    release_lock(f"recommendation:{username}")
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
            
            # Save to MongoDB
            mongo_history.insert_one({
                'username': username,
                'model': model,
                'dataset_id': dataset_id,
                'timestamp': datetime.now()
            })
            return json.dumps({'success': True})
        else:
            return json.dumps({'success': False, 'message': '用户未登录'})

# Update render and session
render = web.template.render('templates/')
web.config.debug = False
app = web.application(urls, globals())
root = tempfile.mkdtemp()
store = web.session.DiskStore(root)
session = web.session.Session(app, store)

if __name__ == "__main__":
    web.httpserver.runsimple(app.wsgifunc(), ("127.0.0.1", 8080))
    app.run()

