# migrate_to_phoenix.py
import pymysql
import phoenixdb
import phoenixdb.cursor

# --- MySQL 连接配置 ---
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'db': 'calculater',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# --- Phoenix/HBase 连接配置 ---
PHOENIX_URL = 'http://192.168.28.101:8765/'

def migrate_performance_data():
    """
    一次性脚本，将 model_performance 表的数据从MySQL迁移到Phoenix/HBase。
    """
    # 1. 从MySQL读取数据
    print("Connecting to MySQL...")
    try:
        mysql_conn = pymysql.connect(**MYSQL_CONFIG)
        with mysql_conn.cursor() as cursor:
            cursor.execute("SELECT dataset_name, model_name, metric_name, score FROM model_performance")
            performance_data = cursor.fetchall()
            print(f"Successfully fetched {len(performance_data)} records from MySQL.")
    except Exception as e:
        print(f"Error connecting to or reading from MySQL: {e}")
        return
    finally:
        if 'mysql_conn' in locals():
            mysql_conn.close()

    if not performance_data:
        print("No performance data found in MySQL. Exiting.")
        return

    # 2. 将数据写入Phoenix/HBase
    print(f"Connecting to Phoenix at {PHOENIX_URL}...")
    try:
        phoenix_conn = phoenixdb.connect(PHOENIX_URL, autocommit=True)
        with phoenix_conn.cursor() as cursor:
            print("Starting data upsert to Phoenix/HBase...")
            
            # 使用 executemany 进行批量操作，效率更高
            sql = "UPSERT INTO MODEL_PERFORMANCE (DATASET_NAME, MODEL_NAME, METRIC_NAME, SCORE) VALUES (?, ?, ?, ?)"
            
            # 准备数据格式
            data_to_upsert = [
                (row['dataset_name'], row['model_name'], row['metric_name'], row['score'])
                for row in performance_data
            ]
            
            cursor.executemany(sql, data_to_upsert)
            
            print(f"Data migration completed successfully! Upserted {len(data_to_upsert)} records.")
    except Exception as e:
        print(f"An error occurred during Phoenix operation: {e}")
    finally:
        if 'phoenix_conn' in locals():
            phoenix_conn.close()

if __name__ == '__main__':
    migrate_performance_data()
