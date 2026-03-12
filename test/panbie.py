import random

def generate_similar_data(num_samples, x_range, y_range):
    data = []
    for _ in range(num_samples):
        x = round(random.uniform(*x_range), 2)
        y = round(random.uniform(*y_range), 2)
        data.append((x, y))
    return data

# 生成类似的数据集
data_set_1 = generate_similar_data(7, (23000, 35000), (11000, 19000))
data_set_2 = generate_similar_data(7, (7000, 12000), (8000, 14000))

# 打印生成的数据
for data in data_set_1:
    print(f"{data[0]} {data[1]}")
print()
for data in data_set_2:
    print(f"{data[0]} {data[1]}")