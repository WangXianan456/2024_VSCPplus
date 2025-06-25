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
            cursorclass=pymysql.cursors.DictCursor
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
            cursorclass=pymysql.cursors.DictCursor
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


urls = (
    '/', 'index',
    '/login', 'LoginPage',
    '/register', 'RegisterPage',
    '/logout', 'Logout',
    '/CheckLogin', 'CheckLogin',
    '/ForgotPassword', 'ForgotPassword',
    '/ResetPassword', 'ResetPassword',

    '/calculate', 'Calculate',
    '/calculateApp.html', 'index',
    '/FisherPlus.html', 'fisher',
    '/Linear.html', 'linear',
    '/MLinear.html', 'MultipleLinear',
    '/Logistic.html', 'Logic',
    '/SVM.html', 'Svm',
    '/Goldfish.html', 'goldfish',

    '/saveSvmHistory', 'saveSvmHistory',
    '/calculate1', 'calculate1',
    '/calculate2', 'calculate2',
    '/UploadCSV', 'UploadCSV',
'/uploadAndPredict', 'UploadAndPredict',

    '/FisherHistory.html', 'HistoryPage',
    '/LinearHistory.html', 'Linearhistory',
    '/LogicHistory.html', 'Logistichistory',
    '/SVMHistory.html', 'SVMHistory',
    '/SaveHistory', 'SaveHistory',
    '/saveLinearHistory', 'SaveLinearHistory',
    '/saveLogicHistory', 'saveLogicHistory',
    '/admin.html', 'Admin',
    '/admin', 'Admin',
    '/Guan.html','guan',
    '/list_users', 'ListUsers',
    '/add_user', 'AddUser',
    '/delete_user', 'DeleteUser',
    '/change_password', 'ChangePassword',
    '/update_user', 'UpdateUser',
    
    '/static/(.*)', 'static',  # Add static files route
    '/Recommendation.html', 'Recommendation',
    '/check_recommendation_status', 'CheckRecommendationStatus',
    '/generateRecommendation', 'GenerateRecommendation',
    
    '/trigger_recommendation', 'TriggerRecommendation', # <-- 新增：专门用于触发任务
    '/compare_models', 'compare_models',
    '/saveRecommendation', 'SaveRecommendation'

)


def round_to_4(value):
    if isinstance(value, float):
        return round(value, 4)
    elif isinstance(value, list):
        return [round_to_4(v) for v in value]
    elif isinstance(value, dict):
        return {k: round_to_4(v) for k, v in value.items()}
    return value


class index:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')
        else:
            username = '未登录'
        print(f"Rendering work page with username: {username}")
        return render.calculateApp(username)

    def POST(self):
        return render.calculateApp()

class LoginPage:
    def POST(self):
        i = web.input()
        account = i.get('account')  # 获取account字段
        password = i.get('password')

        login_success, role = validate_login(account, password)
        if login_success:
            # 从数据库中获取用户名
            username = get_username_from_db(account)
            session.logged_in = True
            session.account = account
            session.username = username
            session.role = role
            print(f"用户登录成功: account={account}, username={username}, role={role}")
            
            web.header('Content-Type', 'application/json')
            if role == 'admin':
                return json.dumps({'success': True, 'redirect': '/admin'})
            else:
                return json.dumps({'success': True, 'redirect': '/'})
        else:
            web.header('Content-Type', 'application/json')
            return json.dumps({'success': False, 'error': '用户名或密码错误'})
        
        
class Logout:
    def POST(self):
        session.kill()
        return json.dumps({'success': True, 'message': '您已成功退出登录。'})

class guan:
    def GET(self):
        return render.Guan()

class RegisterPage:
    def GET(self):
        return render.register()

    def POST(self):
        i = web.input()
        username = i.username
        account = i.account
        password = hashlib.sha256(i.password.encode()).hexdigest()
        if add_user(username, account, password):
            print(f"User registered: {account}")
            web.header('Content-Type', 'application/json')
            return json.dumps({'success': True})
        else:
            web.header('Content-Type', 'application/json')
            return json.dumps({'success': False, 'error': '注册失败，请重试'})


def validate_login(account, password):
    db = connect_db()
    if not db:
        return False, None
    
    try:
        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            # 使用SHA-256加密密码进行比对
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            
            # 使用account字段进行查询
            cursor.execute("""
                SELECT id, username, role 
                FROM user 
                WHERE account = %s AND password = %s
            """, (account, hashed_password))
            
            user = cursor.fetchone()
            
            if user:
                return True, user['role']
            return False, None
    except Exception as e:
        print(f"登录验证错误: {e}")
        return False, None
    finally:
        db.close()
        
def get_username_from_db(account):
    """从数据库获取用户名"""
    db = connect_db()
    if not db:
        return account  # 默认返回account
    
    try:
        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT username FROM user WHERE account = %s", (account,))
            user = cursor.fetchone()
            return user['username'] if user else account
    except Exception as e:
        print(f"获取用户名错误: {e}")
        return account
    finally:
        db.close()

def add_user(username, account, password):
    db = connect_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("INSERT INTO user (username, account, password) VALUES (%s, %s, %s)",
                           (username, account, password))
            db.commit()
            return True
        except mysql.connector.Error as err:
            print(f"添加用户错误: {err}")
        finally:
            cursor.close()
            db.close()
    return False


class Admin:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')
        else:
            username = '未登录'
        print(f"Rendering work page with username: {username}")
        return render.admin(username)

    def POST(self):
        return render.admin()

class fisher:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')
        else:
            username = '未登录'
        print(f"Rendering work page with username: {username}")
        return render.FisherPlus(username)

    def POST(self):
        return render.FisherPlus()


class Logic:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')
        else:
            username = '未登录'
        print(f"Rendering work page with username: {username}")
        return render.Logistic(username)


class Svm:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')
        else:
            username = '未登录'
        print(f"Rendering work page with username: {username}")
        return render.SVM(username)


def get_user_id_from_db(account):
    if session.get('logged_in'):
        db = connect_db()
        if db:
            cursor = db.cursor()
            try:
                cursor.execute("SELECT id FROM user WHERE account = %s", (account,))
                result = cursor.fetchone()
                if result:
                    return result[0]  # 返回用户的id
                else:
                    raise ValueError("未找到用户！")
            except mysql.connector.Error as err:
                print(f"数据库错误: {err}")
            finally:
                cursor.close()
                db.close()
    return ValueError("用户未登录")


class Calculate:
    def POST(self):
        data = json.loads(web.data())
        coordinates1 = np.array(data['coordinates1'])
        coordinates2 = np.array(data['coordinates2'])

        u1 = np.mean(coordinates1, axis=0)
        u2 = np.mean(coordinates2, axis=0)

        S1 = np.cov(coordinates1, rowvar=False)
        S2 = np.cov(coordinates2, rowvar=False)
        Sw = S1 + S2

        reg_lambda = 1e-5
        Sw_reg = Sw + np.eye(Sw.shape[0]) * reg_lambda

        w = np.linalg.inv(Sw_reg).dot(u1 - u2)
        theta = -0.5 * np.dot(w.T, (u1 + u2))

        m = -w[0] / w[1]
        c = -theta / w[1]

        result = {
            'u1': round_to_4(u1.tolist()),
            'u2': round_to_4(u2.tolist()),
            'S1': round_to_4(S1.tolist()),
            'S2': round_to_4(S2.tolist()),
            'Sw': round_to_4(Sw.tolist()),
            'w': round_to_4(w.tolist()),
            'theta': round(theta, 4),
            'L': {'m': round(m, 4), 'c': round(c, 4)}
        }
        web.header('Content-Type', 'application/json')
        return json.dumps(result)


class linear:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')
        else:
            username = '未登录'
        print(f"Rendering work page with username: {username}")
        return render.Linear(username)

    def POST(self):

        return render.Linear()


class MultipleLinear:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')
        else:
            username = '未登录'
        print(f"Rendering work page with username: {username}")
        return render.MLinear(username)


class UploadCSV:
    def POST(self):
        x = web.input(csvfile={})
        if 'csvfile' not in x or not x['csvfile'].filename:
            return web.notfound("CSV file not found")

        csvfile = x['csvfile'].file
        try:
            df = pd.read_csv(csvfile, skiprows=1)  # 修改此处以跳过第一行
        except Exception as e:
            return web.badrequest("Error reading CSV file: " + str(e))

        if df.shape[1] < 2:
            return web.badrequest("CSV file must contain at least two columns.")

        try:
            X = df.iloc[:, :-1]
            y = df.iloc[:, -1]
            X = sm.add_constant(X)  # Ensure the intercept is included
            model = sm.OLS(y, X).fit()

            # Performing PCA
            pca = PCA(n_components=2)
            pca_points = pca.fit_transform(X.iloc[:, 1:])  # Exclude the constant term added earlier

            # Adding labels to points
            labels = ["X{}".format(i+1) for i in range(len(X.columns) - 1)]
            labels = ["const"] + labels  # Include the constant term label
            points_list = [{'x': point[0], 'y': point[1], 'label': label} for point, label in zip(pca_points, labels[1:])]  # Exclude the constant term label in plotting

        except Exception as e:
            return web.internalerror("Error fitting model or applying PCA: " + str(e))

        predictions = model.predict(X)
        equation_terms = ["{:.4f}".format(param) + ("*{}".format(name) if name != "const" else "") for param, name in zip(model.params, labels)]
        equation = "Y = " + " + ".join(equation_terms)

        result = {
            'summary': model.summary().as_text(),
            'predictions': [round(pred, 4) for pred in predictions],
            'equation': equation,
            'points': points_list  # Including PCA points for front-end plotting
        }

        web.header('Content-Type', 'application/json')
        return json.dumps(result)


class goldfish:
    def GET(self):
        username = session.get('username', '未登录')
        id = 13
        sql = f"select * from abalone where id={id}"
        sqlData = sqlSelect(sql)
        models = {
            '线性回归': '线性回归.model',
            '决策树': '决策树.model',
            '随机森林': '随机森林.model',
            '梯度提升机': '梯度提升机.model',
            '支持向量机': '支持向量机.model'
        }
        results = {}
        model_errors = {}
        real_age = float(sqlData[0][-1])  # 假设真实年龄存储在最后一个字段

        for name, filename in models.items():
            model = joblib.load(filename)
            testX = [[float(t) for t in sqlData[0][1:-1]]]
            pred_age = model.predict(testX)[0]
            results[name] = round(pred_age, 4)
            # 计算平均绝对误差
            abs_error = abs(pred_age - real_age)
            model_errors[name] = round(abs_error, 4)

        return render.goldfish(id, sqlData, results, model_errors, username)

    def POST(self):
        username = session.get('username', '未登录')
        webData = web.input()
        id = webData["bid"]
        sql = f"select * from abalone where id={id}"
        sqlData = sqlSelect(sql)
        models = {
            '线性回归': '线性回归.model',
            '决策树': '决策树.model',
            '随机森林': '随机森林.model',
            '梯度提升机': '梯度提升机.model',
            '支持向量机': '支持向量机.model'
        }
        results = {}
        model_errors = {}
        real_age = float(sqlData[0][-1])  # 假设真实年龄存储在最后一个字段

        for name, filename in models.items():
            model = joblib.load(filename)
            testX = [[float(t) for t in sqlData[0][1:-1]]]
            pred_age = model.predict(testX)[0]
            results[name] = round(pred_age, 4)
            # 计算平均绝对误差
            abs_error = abs(pred_age - real_age)
            model_errors[name] = round(abs_error, 4)

        return render.goldfish(id, sqlData, results, model_errors, username)


class UploadAndPredict:
    def POST(self):
        web.header('Content-Type', 'application/json')  # 设置响应类型为JSON
        username = session.get('username', '未登录')
        webData = web.input(modelFile={})

        if 'modelFile' not in webData or not webData['modelFile'].filename:
            return web.notfound(json.dumps({"error": "请上传模型文件。"}))

        model_file = webData['modelFile'].file
        model = joblib.load(model_file)  # 加载上传的模型文件

        id = webData.get('bid', 13)  # 可以从表单中获取ID或默认使用ID 13
        sql = f"select * from abalone where id={id}"
        sqlData = sqlSelect(sql)
        if not sqlData:
            return web.notfound(json.dumps({"error": "未找到指定的数据。"}))

        testX = [[float(t) for t in sqlData[0][1:-1]]]
        pred_age = model.predict(testX)[0]
        real_age = float(sqlData[0][-1])
        abs_error = abs(pred_age - real_age)

        results = {
            'predicted_age': round(pred_age, 4),
            'real_age': real_age,
            'absolute_error': round(abs_error, 4)
        }

        return json.dumps(results)  # 返回JSON数据

class calculate1:
    def POST(self):
        data = web.data()
        data = json.loads(data)
        X = np.array(data['X'])
        y = np.array(data['y'])
        m, n = X.shape

        # 添加偏置项
        x1 = np.hstack((np.ones((m, 1)), X))
        theta = np.zeros(n + 1)

        # 梯度下降参数
        alpha = 0.01
        iterations = 1000

        for _ in range(iterations):
            z = np.dot(x1, theta)
            z = np.clip(z, -20, 20)
            h = 1 / (1 + np.exp(-z))
            h = np.clip(h, 1e-10, 1 - 1e-10)
            J = -1 / m * (np.dot(y, np.log(h)) + np.dot((1 - y), np.log(1 - h)))
            deltaJ = 1 / m * np.dot(x1.T, (h - y))
            theta -= alpha * deltaJ

        w = theta[1:]
        b = theta[0]
        log_odds = np.log(h / (1 - h))

        x_boundary = np.array([np.min(X[:, 0]), np.max(X[:, 0])])
        y_boundary = -(w[0] * x_boundary + b) / w[1]
        decisionBoundary = [{'x': round(float(x_boundary[0]), 4), 'y': round(float(y_boundary[0]-3800), 4)},
                            {'x': round(float(x_boundary[1]), 4), 'y': round(float(y_boundary[1]-3800), 4)}]

        result = {
            'x1': [list(map(lambda x: round(x, 4), row)) for row in x1.tolist()],
            'theta': list(map(lambda x: round(x, 4), theta)),
            'z': list(map(lambda x: round(x, 4), z)),
            'h': list(map(lambda x: round(x, 4), h)),
            'J': round(J, 4),
            'deltaJ': list(map(lambda x: round(x, 4), deltaJ)),
            'w': list(map(lambda x: round(x, 4), w)),
            'b': round(b, 4),
            'logOdds': list(map(lambda x: round(x, 4), log_odds)),
            'decisionBoundary': decisionBoundary
        }

        plt.scatter(X[:, 0], X[:, 1], c=y, cmap='bwr')
        plt.plot(x_boundary, y_boundary, 'k--')
        plt.xlabel('Feature 1')
        plt.ylabel('Feature 2')
        plt.title('Decision Boundary')
        plt.savefig('/decision_boundary.png')
        plt.close()

        web.header('Content-Type', 'application/json')
        return json.dumps(result)


class calculate2:
    def POST(self):
        data = web.data()
        try:
            params = json.loads(data)
            X = np.array(params['X'], dtype=float).reshape(-1, 2)
            y = np.array(params['y'], dtype=int)

            model = svm.SVC(kernel='linear', C=1.0)
            model.fit(X, y)

            support_vectors = round_to_4(model.support_vectors_.tolist())
            dual_coefs = round_to_4(model.dual_coef_.tolist())
            intercept = round_to_4(model.intercept_.tolist())
            weights = round_to_4(model.coef_.tolist())

            w = model.coef_[0]
            b = model.intercept_[0]
            x_points = np.linspace(min(X[:, 0]), max(X[:, 0]), 2)
            y_points = -(w[0] / w[1]) * x_points - b / w[1]

            decision_boundary = [{"x": round(x_points[0], 4), "y": round(y_points[0], 4)},
                                 {"x": round(x_points[1], 4), "y": round(y_points[1], 4)}]

            response = {
                "support_vectors": support_vectors,
                "dual_coefs": dual_coefs,
                "intercept": intercept,
                "weights": weights,
                "decision_boundary": decision_boundary
            }

            web.header('Content-Type', 'application/json')
            return json.dumps(response)
        except KeyError as e:
            return web.badrequest(f"Missing parameter: {e}")
        except AttributeError as e:
            return web.badrequest(f"AttributeError: {e}")
        except json.JSONDecodeError as e:
            return web.badrequest(f"JSON decode error: {e}")


class SaveHistory:
    def POST(self):
        if session.get('logged_in'):
            data = json.loads(web.data())
            username = session.get('username')

            db = connect_db()
            cursor = db.cursor()

            sql = """
                INSERT INTO fisher (user_id, data1, data2, u1, u2, S1, S2, Sw, w, theta, L, input_time)
                SELECT user.id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                FROM user
                WHERE user.username = %s
            """
            cursor.execute(sql, (
                data['data1'],
                data['data2'],
                data['u1'],
                data['u2'],
                data['S1'],
                data['S2'],
                data['Sw'],
                data['w'],
                data['theta'],
                data['L'],
                username
            ))
            db.commit()
            cursor.close()
            db.close()

            return json.dumps({'success': True})
        else:
            return json.dumps({'success': False, 'message': '用户未登录'})


class CheckLogin:
    def GET(self):
        if session.get('logged_in'):
            return json.dumps({'logged_in': True})
        else:
            return json.dumps({'logged_in': False})


class HistoryPage:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')

            db = connect_db()
            cursor = db.cursor(pymysql.cursors.DictCursor) 
            sql = """
                SELECT fisher.*, user.username 
                FROM fisher 
                JOIN user ON fisher.user_id = user.id 
                WHERE user.username = %s 
                ORDER BY fisher.input_time DESC
            """
            cursor.execute(sql, (username,))
            history_data = cursor.fetchall()
            cursor.close()
            db.close()
            return render.FisherHistory(username, history_data)


class SaveLinearHistory:
    def POST(self):
        if session.get('logged_in'):
            try:
                data = json.loads(web.data())  # 直接解析数据
                username = session.get('username')

                db = connect_db()
                cursor = db.cursor()

                # 准备插入的数据
                data1 = json.dumps(data['data1'])
                data2 = json.dumps(data['data2'])
                regression_result = data['regressionResult']

                # 构造插入的 SQL 语句
                sql = """
                    INSERT INTO linears(user_id, data1, data2, x_avg, y_avg, Lxx, Lyy, Lxy, slope, intercept, L, SSe, sigma, r, rr, input_time)
                    SELECT user.id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    FROM user
                    WHERE user.username = %s
                """
                cursor.execute(sql, (
                    data1,
                    data2,
                    regression_result['x_avg'],
                    regression_result['y_avg'],
                    regression_result['Lxx'],
                    regression_result['Lyy'],
                    regression_result['Lxy'],
                    regression_result['slope'],
                    regression_result['intercept'],
                    f"y = {regression_result['slope']} * x + {regression_result['intercept']}",
                    regression_result['SSe'],
                    regression_result['sigma'],
                    regression_result['r'],
                    regression_result['rr'],
                    username
                ))

                db.commit()
                cursor.close()
                db.close()

                return json.dumps({'status': 'success'})
            except Exception as e:
                return json.dumps({'status': 'failure', 'message': str(e)})
        else:
            return json.dumps({'status': 'failure', 'message': '用户未登录'})

class Linearhistory:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')

            db = connect_db()
            cursor = db.cursor(pymysql.cursors.DictCursor) 
            sql = """
                    SELECT linears.*, user.username
                    FROM linears
                    JOIN user ON linears.user_id = user.id
                    WHERE user.username = %s
            """

            cursor.execute(sql, (username,))
            history_data = cursor.fetchall()
            cursor.close()
            db.close()
            return render.LinearHistory(username, history_data)
        else:
            return render.HistoryError()


class ForgotPassword:
    def POST(self):
        i = web.input()
        username = i.username
        account = i.account

        db = connect_db()
        if db:
            cursor = db.cursor()
            cursor.execute("SELECT id FROM user WHERE username = %s AND account = %s", (username, account))
            user = cursor.fetchone()
            cursor.close()
            db.close()

            if user:

                return json.dumps({'success': True, 'user_id': user[0]})
            else:
                return json.dumps({'success': False, 'error': '未找到匹配的用户信息'})
        else:
            return json.dumps({'success': False, 'error': '数据库连接失败'})


class ResetPassword:
    def POST(self):
        i = web.input()
        user_id = i.user_id
        new_password = i.new_password

        db = connect_db()
        if db:
            cursor = db.cursor()
            new_password_hash = hashlib.sha256(new_password.encode()).hexdigest()  # 使用哈希加密新密码
            cursor.execute("UPDATE user SET password = %s WHERE id = %s", (new_password_hash, user_id))
            db.commit()
            cursor.close()
            db.close()
            return json.dumps({'success': True, 'message': '密码已重置。'})
        else:
            return json.dumps({'success': False, 'error': '数据库连接失败'})

class saveLogicHistory:
    def POST(self):
        if session.get('logged_in'):
            data = json.loads(web.data())
            username = session.get('username')

            db = connect_db()
            cursor = db.cursor()

            sql = """
                INSERT INTO logistic (user_id, x1, theta, z, h, J, deltaJ, w, b, log_odds, decision_boundary, input_time)
                SELECT user.id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                FROM user
                WHERE user.username = %s
            """
            cursor.execute(sql, (
                json.dumps(data['x1']),
                json.dumps(data['theta']),
                json.dumps(data['z']),
                json.dumps(data['h']),
                data['J'],
                json.dumps(data['deltaJ']),
                json.dumps(data['w']),
                data['b'],
                json.dumps(data['logOdds']),
                json.dumps(data['decisionBoundary']),
                username
            ))
            db.commit()
            cursor.close()
            db.close()

            return json.dumps({'success': True})
        else:
            return json.dumps({'success': False, 'message': '用户未登录'})


class Logistichistory:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')

            db = connect_db()
            cursor = db.cursor(pymysql.cursors.DictCursor) 
            sql = """
                SELECT logistic.*, user.username 
                FROM logistic 
                JOIN user ON logistic.user_id = user.id 
                WHERE user.username = %s 
                ORDER BY logistic.input_time DESC
            """
            cursor.execute(sql, (username,))
            history_data = cursor.fetchall()
            cursor.close()
            db.close()

            return render.LogicHistory(username, history_data)
        else:
            return "用户未登录，请登录后再试。"


class saveSvmHistory:
    def POST(self):
        if session.get('logged_in'):
            try:
                data = json.loads(web.data())  # 直接解析数据
                username = session.get('username')

                db = connect_db()
                cursor = db.cursor()

                # 准备插入的数据
                dataX = json.dumps(data['X'])
                dataY = json.dumps(data['y'])
                support_vectors = json.dumps(data['supportVectors'])
                dual_coefs = json.dumps(data['dualCoefs'])
                intercept = data['intercept']
                weights = json.dumps(data['weights'])
                decision_boundary = json.dumps(data['decisionBoundary'])

                # 构造插入的 SQL 语句
                sql = """
                    INSERT INTO svm(user_id, dataX, dataY, support_vectors, dual_coefs, intercept, weights, decision_boundary, input_time)
                    SELECT user.id, %s, %s, %s, %s, %s, %s, %s, NOW()
                    FROM user
                    WHERE user.username = %s
                """
                cursor.execute(sql, (
                    dataX,
                    dataY,
                    support_vectors,
                    dual_coefs,
                    intercept,
                    weights,
                    decision_boundary,
                    username
                ))

                db.commit()
                cursor.close()
                db.close()

                return json.dumps({'success': True})
            except Exception as e:
                return json.dumps({'status': 'failure', 'message': str(e)})
        else:
            return json.dumps({'status': 'failure', 'message': '用户未登录'})


class SVMHistory:
    def GET(self):
        if session.get('logged_in'):
            username = session.get('username', '未登录')

            db = connect_db()
            cursor = db.cursor(pymysql.cursors.DictCursor)
            sql = """
                    SELECT svm.*, user.username
                    FROM svm
                    JOIN user ON svm.user_id = user.id
                    WHERE user.username = %s
            """

            cursor.execute(sql, (username,))
            history_data = cursor.fetchall()
            cursor.close()
            db.close()
            return render.SVMHistory(username, history_data)
        else:
            return render.HistoryError()

class ListUsers:
    def GET(self):
        try:
            db = connect_db()
            cursor = db.cursor()
            cursor.execute("SELECT id, username, account FROM user WHERE role != 'admin'")
            users = cursor.fetchall()
            # 转换元组为字典列表
            users = [{'id': user[0], 'username': user[1], 'account': user[2]} for user in users]
            cursor.close()
            db.close()
            return json.dumps(users)
        except Exception as e:
            return json.dumps({'success': False, 'message': str(e)})

class AddUser:
    def POST(self):
        try:
            i = web.input()
            username = i.username.strip()
            account = i.account.strip()
            password = hashlib.sha256(i.password.encode()).hexdigest()
            db = connect_db()
            cursor = db.cursor()
            cursor.execute("INSERT INTO user (username, account, password) VALUES (%s, %s, %s)", (username, account, password))
            db.commit()
            cursor.close()
            db.close()
            return json.dumps({'success': True, 'message': '用户已添加'})
        except Exception as e:
            return json.dumps({'success': False, 'message': str(e)})


class DeleteUser:
    def POST(self):
        i = web.input()
        user_id = i.id
        db = connect_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM user WHERE id = %s", (user_id,))
        db.commit()
        cursor.close()
        db.close()
        return json.dumps({'success': True, 'message': '用户已删除'})


class ChangePassword:
    def POST(self):
        i = web.input()
        user_id = i.id
        new_password = i.password
        hashed_password = hashlib.sha256(new_password.encode()).hexdigest()  # 使用相同的哈希算法加密新密码
        db = connect_db()
        cursor = db.cursor()
        cursor.execute("UPDATE user SET password = %s WHERE id = %s", (hashed_password, user_id))
        db.commit()
        cursor.close()
        db.close()
        return json.dumps({'success': True, 'message': '密码已更新'})


class UpdateUser:
    def POST(self):
        i = web.input()
        user_id = i.id
        username = i.username
        account = i.account
        db = connect_db()
        cursor = db.cursor()
        cursor.execute("UPDATE user SET username = %s, account = %s WHERE id = %s", (username, account, user_id))
        db.commit()
        cursor.close()
        db.close()
        return json.dumps({'success': True, 'message': '用户信息已更新'})
class static:
    def GET(self, path):
        try:
            web.header('Content-Type', 'application/javascript; charset=UTF-8')
            return open('static/' + path, 'rb').read()
        except IOError:
            raise web.notfound()
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