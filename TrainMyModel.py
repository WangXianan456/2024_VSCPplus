import csv
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.neighbors import KNeighborsRegressor
import joblib

# 读取数据
trainX, trainY = [], []
with open("E:\\Goldfish.csv", "r", encoding="utf-8") as f:
    next(f)  # 跳过标题行
    reader = csv.reader(f)
    for t in reader:
        t = [float(tt) for tt in t]
        trainX.append(t[1:-1])
        trainY.append(t[-1])

# 定义模型
models = {
    '线性回归': LinearRegression(),
    '决策树': DecisionTreeRegressor(),
    '随机森林': RandomForestRegressor(),
    '梯度提升机': GradientBoostingRegressor(),
    '支持向量机': SVR(),
    'K最近邻': KNeighborsRegressor()
}

# 训练和保存模型
for name, model in models.items():
    model.fit(trainX, trainY)
    joblib.dump(model, f"{name}.model")
    print(f"{name}模型保存成功。")

# 测试数据
testX = [[1, 0.455, 0.365, 0.095, 0.514, 0.2245, 0.101, 0.15],
         [1, 0.44, 0.365, 0.125, 0.516, 0.2155, 0.114, 0.155]]

# 预测并打印结果
for name, model in models.items():
    pred = model.predict(testX)
    pred_rounded = [round(p, 2) for p in pred]
    print(f"{name}预测结果:", pred_rounded)