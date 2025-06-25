# worker.py
import redis
import json
import time
from calculator import redis_client, DateTimeEncoder, generate_recommendations_for_user # 从主应用导入所需资源

TASK_QUEUE_KEY = "recom:task_queue"
RESULT_CACHE_PREFIX = "recom:model_data:"
CACHE_EXPIRATION_SECONDS = 3600

def main():
    print("后台工作进程已启动，等待推荐任务...")
    while True:
        try:
            # BRPOP 是一个阻塞式操作，它会等待直到队列中有任务
            # '0' 表示无限期等待
            # 返回的是一个元组 (队列名, 任务内容)
            _, task_data = redis_client.brpop(TASK_QUEUE_KEY, 0)
            
            task = json.loads(task_data)
            username = task.get('username')

            if not username:
                print("收到的任务格式不正确，已忽略。")
                continue

            print(f"收到任务，开始为用户 '{username}' 生成推荐...")
            
           # 1. 执行核心计算逻辑
            recommendations = generate_recommendations_for_user(username)

            # 2. 将结果存入缓存
            cache_key = f"recom:model_data:{username}"
            serialized_data = json.dumps(recommendations, cls=DateTimeEncoder)
            redis_client.setex(cache_key, CACHE_EXPIRATION_SECONDS, serialized_data)

            # 3. 删除“任务进行中”的标记 (这是新增的关键步骤)
            task_in_progress_key = f"recom:task_in_progress:{username}"
            redis_client.delete(task_in_progress_key)

            print(f"用户 '{username}' 的推荐结果已生成并存入缓存，'进行中'标记已移除。")

        except redis.exceptions.ConnectionError as e:
            print(f"Redis连接错误: {e}. 5秒后重试...")
            time.sleep(5)
        except Exception as e:
            print(f"处理任务时发生未知错误: {e}")
            # 避免因单个任务失败而导致整个worker崩溃
            time.sleep(1)

if __name__ == '__main__':
    main()
