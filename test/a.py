import matplotlib.pyplot as plt

# 数据：文明持续时间（年份）
years = [-2000, -1000, 0, 1000, 1500, 1600]
maya = [1, 1, 1, 1, 1, 0]  # 玛雅：公元前2000年至1500年
aztec = [0, 0, 0, 0, 2, 0]  # 阿兹特克：公元1325年至1521年
inca = [0, 0, 0, 0, 3, 0]   # 印加：公元1200年至1533年

# 绘制折线图
plt.plot(years, maya, label='Maya', color='blue')
plt.plot(years, aztec, label='Aztec', color='red')
plt.plot(years, inca, label='Inca', color='green')

# 添加标签和标题
plt.xlabel('Year (BC/AD)')
plt.ylabel('Civilization Presence')
plt.title('Timeline of Maya, Aztec, and Inca Civilizations')
plt.legend()

# 显示图表
plt.grid(True)
plt.show()
