import random

def generate_regression_data(num_samples, x_range, y_range):
    x_values = [round(random.uniform(*x_range), 2) for _ in range(num_samples)]
    y_values = [round(random.uniform(*y_range), 2) for _ in range(num_samples)]
    return x_values, y_values

# 生成类似的数据集
x_values, y_values = generate_regression_data(10, (50, 150), (200, 500))

# 打印生成的横坐标值
for x in x_values:
    print(x)
print()

# 打印生成的纵坐标值
for y in y_values:
    print(y)