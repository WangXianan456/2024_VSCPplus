/**
 * ===================================================================
 * recommendation.js - 推荐页面的主控制脚本
 * 
 * 负责处理三种页面状态：
 * 1. initial: 显示“生成推荐”按钮。
 * 2. pending: 显示加载动画并轮询检查任务状态。
 * 3. ready:   显示推荐结果、图表和偏好设置表单。
 * ===================================================================
 */

/**
 * 主入口函数：当DOM加载完成后执行。
 */
document.addEventListener('DOMContentLoaded', () => {
    const recoDataElement = document.getElementById('reco-data');
    if (!recoDataElement) {
        console.error('关键元素 #reco-data 未找到，脚本无法执行。');
        return;
    }

    // 从DOM中获取当前页面状态
    const status = recoDataElement.dataset.status;

    // 根据状态执行不同的初始化逻辑
    switch (status) {
        case 'initial':
            console.log('状态: initial. 绑定“生成”按钮事件。');
            bindTriggerButton('generate-btn');
            break;

        case 'pending':
            console.log('状态: pending. 开始轮询任务状态。');
            startPolling();
            break;

        case 'ready':
            console.log('状态: ready. 初始化结果展示页面。');
            initializeReadyState(recoDataElement);
            break;

        default:
            console.error(`未知的页面状态: ${status}`);
    }
});

/**
 * 初始化“就绪”状态的页面：渲染结果、图表、绑定事件。
 * @param {HTMLElement} recoDataElement - 包含推荐数据的DOM元素。
 */
function initializeReadyState(recoDataElement) {
    try {
        const recoDataString = recoDataElement.textContent;
        if (!recoDataString) {
            throw new Error('推荐数据为空。');
        }
        const recoData = JSON.parse(recoDataString);

        renderRecommendationList(recoData);
        initConfidenceChart(recoData);
        setupFormSubmitHandler();
        bindTriggerButton('regenerate-btn');

    } catch (error) {
        console.error('初始化推荐结果页面时出错:', error);
        alert('渲染推荐结果失败，请尝试重新生成。');
    }
}

/**
 * 渲染推荐的模型和数据集列表。
 * @param {Object} recoData - 包含推荐数据的对象。
 */
function renderRecommendationList(recoData) {
    const listElement = document.getElementById('recommendations-list'); // 注意：HTML中的ID已更新
    if (!listElement) {
        console.error('列表元素 #recommendations-list 未找到。');
        return;
    }
    listElement.innerHTML = ''; // 清空旧内容

    if (recoData.models && recoData.models.length > 0) {
        recoData.models.forEach((model, index) => {
            const confidence = (recoData.confidence[index] * 100).toFixed(1);
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.innerHTML = `推荐模型: <strong>${model}</strong> <span class="badge">${confidence}% 置信度</span>`;
            listElement.appendChild(li);
        });
        recoData.datasets.forEach((datasetId) => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.innerHTML = `推荐数据集ID: <strong>${datasetId}</strong>`;
            listElement.appendChild(li);
        });
    } else {
        const li = document.createElement('li');
        li.className = 'list-group-item';
        li.textContent = '暂无有效的推荐结果。';
        listElement.appendChild(li);
    }
}

/**
 * 绑定触发推荐计算的按钮（“生成”或“重新生成”）。
 * @param {string} buttonId - 按钮的DOM ID。
 */
function bindTriggerButton(buttonId) {
    const btn = document.getElementById(buttonId);
    if (btn) {
        btn.addEventListener('click', triggerRecommendation);
    }
}

/**
 * 向后端发送请求以触发推荐任务。
 */
function triggerRecommendation() {
    const btn = this;
    btn.disabled = true;
    btn.innerHTML = '<span class="glyphicon glyphicon-refresh" style="animation: spin 1s linear infinite;"></span> 处理中...';

    // 判断是否为“重新生成推荐”按钮
    const isRegenerate = btn.id === 'regenerate-btn';

    fetch('/trigger_recommendation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(isRegenerate ? { force: true } : {})
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok' || data.status === 'pending') {
                window.location.reload();
            } else {
                throw new Error(data.message || '提交任务失败');
            }
        })
        .catch(error => {
            console.error('触发推荐任务时出错:', error);
            alert(`操作失败: ${error.message}`);
            btn.disabled = false;
            btn.innerHTML = btn.id === 'generate-btn' ? '开始生成推荐' : '重新生成推荐';
        });
}

/**
 * 开始轮询，定期检查推荐任务是否完成。
 */
function startPolling() {
    const intervalId = setInterval(() => {
        fetch('/check_recommendation_status')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'ready') {
                    clearInterval(intervalId);
                    window.location.reload();
                }
            })
            .catch(error => {
                console.error('轮询检查状态时出错:', error);
                // 可以在这里添加错误处理，比如轮询几次失败后停止
            });
    }, 3000); // 每3秒检查一次
}

// ===================================================================
// 以下是您已有的、功能完善的函数，保持不变。
// ===================================================================

/**
 * 初始化置信度图表。
 * @param {Object} recoData - 推荐数据对象。
 */
function initConfidenceChart(recoData) {
    const ctx = document.getElementById('confidenceChart');
    if (!ctx) return;

    new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: {
            labels: recoData.models,
            datasets: [{
                label: '推荐置信度',
                data: recoData.confidence,
                backgroundColor: 'rgba(54, 162, 235, 0.6)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                yAxes: [{ ticks: { beginAtZero: true, max: 1.0 } }]
            }
        }
    });
}

/**
 * 设置偏好保存表单的提交处理。
 */
function setupFormSubmitHandler() {
    const form = document.getElementById('recom-savePreferenceForm');
    if (!form) {
        console.warn('找不到表单: #recom-savePreferenceForm');
        return;
    }

    // 在表单上方或下方添加一个用于显示消息的 div
    const messageDiv = document.createElement('div');
    messageDiv.id = 'form-message';
    form.parentNode.insertBefore(messageDiv, form);


    form.addEventListener('submit', async function (e) {
        e.preventDefault();

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = '保存中...';

        // 清除旧消息
        messageDiv.textContent = '';
        messageDiv.className = '';

        try {
            const model = document.getElementById('recom-model').value;
            const dataset_id = document.getElementById('recom-dataset_id').value;

            if (!model || !dataset_id) {
                throw new Error('请填写所有字段');
            }

            const response = await fetch('/saveRecommendation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: model, dataset_id: dataset_id })
            });

            const data = await response.json();

            // --- 修改这里 ---
            if (data.success) {
                // 不再使用 alert，而是在页面上显示消息
                messageDiv.textContent = data.message;
                messageDiv.className = 'alert alert-success mt-2'; // 使用Bootstrap样式
            } else {
                throw new Error(data.message || '保存失败');
            }
        } catch (error) {
            console.error('保存偏好出错:', error);
            // 在页面上显示错误消息
            messageDiv.textContent = `保存失败: ${error.message}`;
            messageDiv.className = 'alert alert-danger mt-2';
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalBtnText;
        }
    });
}

// 添加一个简单的CSS动画给加载图标
const style = document.createElement('style');
style.innerHTML = `@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`;
document.head.appendChild(style);

/**
 * ===================================================================
 * 模型性能实验室 - 控制脚本
 * ===================================================================
 */
document.addEventListener('DOMContentLoaded', () => {
    const compareBtn = document.getElementById('run-comparison-btn');
    if (compareBtn) {
        compareBtn.addEventListener('click', runComparison);
    }
});

// 用于存储图表实例，以便在更新时销毁旧图表
let comparisonChartInstance = null;

/**
 * 执行模型比较：收集用户选择，调用API，然后绘制图表。
 */
function runComparison() {
    const dataset = document.getElementById('compare-dataset-select').value;
    const selectedModels = [];
    document.querySelectorAll('#compare-model-selection input[type="checkbox"]:checked').forEach(checkbox => {
        selectedModels.push(checkbox.value);
    });

    if (selectedModels.length === 0) {
        alert('请至少选择一个模型进行比较！');
        return;
    }

    // 调用新的后端API
    fetch('/compare_models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            dataset_name: dataset,
            models: selectedModels
        })
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`服务器错误: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            // 使用获取到的预计算分数来绘制图表
            drawComparisonChart(data);
        })
        .catch(error => {
            console.error('获取比较数据时出错:', error);
            alert(`获取比较数据失败: ${error.message}`);
        });
}

/**
 * 使用 Chart.js 绘制模型性能对比图。
 * @param {Array} results - 从API获取的模型性能数据数组。
 */
function drawComparisonChart(results) {
    const ctx = document.getElementById('comparisonChart');
    if (!ctx) return;

    // 如果图表实例已存在，先销毁它
    if (comparisonChartInstance) {
        comparisonChartInstance.destroy();
    }

    if (results.length === 0) {
        // 如果没有数据，可以显示一条消息
        const context = ctx.getContext('2d');
        context.clearRect(0, 0, ctx.width, ctx.height);
        context.textAlign = 'center';
        context.fillText('未找到所选模型在该数据集上的性能数据。', ctx.width / 2, 50);
        return;
    }

    const labels = results.map(r => r.model);
    const scores = results.map(r => r.score);
    const metricName = results[0].metric_name;
    const datasetName = document.getElementById('compare-dataset-select').value;

    comparisonChartInstance = new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: `性能 (${metricName})`,
                data: scores,
                backgroundColor: [
                    'rgba(54, 162, 235, 0.6)',
                    'rgba(255, 206, 86, 0.6)',
                    'rgba(75, 192, 192, 0.6)',
                    'rgba(153, 102, 255, 0.6)',
                    'rgba(255, 99, 132, 0.6)'
                ],
                borderColor: [
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(153, 102, 255, 1)',
                    'rgba(255, 99, 132, 1)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            title: {
                display: true,
                text: `模型在 ${datasetName} 数据集上的性能对比`,
                fontSize: 16
            },
            legend: {
                display: false
            },
            scales: {
                xAxes: [{
                    ticks: {
                        beginAtZero: true,
                        // 对于准确率等指标，最大值为1
                        suggestedMax: (metricName.includes('accuracy') || metricName.includes('score')) ? 1.0 : undefined
                    }
                }]
            }
        }
    });
}
