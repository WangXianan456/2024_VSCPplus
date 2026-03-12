import csv
from sklearn import metrics
from sklearn.linear_model import LinearRegression
import joblib

trainX, trainY = [], []
fobj = open("E:\\Goldfish.csv", "r", encoding="utf-8")
fobj.readline()
reader = csv.reader(fobj)
for t in reader:
    t = [float(tt) for tt in t]
    trainX.append(t[1:-1])
    trainY.append(t[-1])
fobj.close()

model = LinearRegression()
model.fit(trainX, trainY)
joblib.dump(model,"lr.model")

print("模型参数:", model.coef_)

testX = [[1, 0.455, 0.365, 0.095, 0.514, 0.2245, 0.101, 0.15],
         [1, 0.44, 0.365, 0.125, 0.516, 0.2155, 0.114, 0.155]]

pred = model.predict(testX)

pred_rounded=[round(p,2)for p in pred]
print("预测结果:", pred)
