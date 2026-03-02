function checkLogin() {
    $.ajax({
        url: '/CheckLogin',
        method: 'GET',
        success: function(response) {
            try {
                if (typeof response === "string") {
                    response = JSON.parse(response);
                }
                if (response.logged_in) {
                       window.open('FisherHistory.html', '_blank');
                } else {
                    document.getElementById('errorModal').style.display = 'block';
                }
            } catch (e) {
                console.error('Error parsing response:', e);
            }
        },
        error: function() {
            alert('未登录账号！无法显示历史记录！');
        }
    });
}

function goToRecommendation() {
    $.ajax({
        url: '/CheckLogin',
        method: 'GET',
        success: function(response) {
            try {
                if (typeof response === "string") {
                    response = JSON.parse(response);
                }
                
                if (response.logged_in) {
                    window.location.href = '/Recommendation.html';
                } else {
                    // 如果页面上有登录错误提示弹窗（优先使用主页已有的id=errorModal）
                    if (document.getElementById('errorModal')) {
                        document.getElementById('errorModal').style.display = 'block';
                    } else if (document.getElementById('loginModal')) {
                        // 或者直接弹出登录框
                        document.getElementById('loginModal').style.display = 'block';
                    } else {
                        // 如果都没有（比如在简单子页面），提示并跳转回主页
                        alert('请先登录账号！');
                        window.location.href = '/'; 
                    }
                }
            } catch (e) {
                console.error('Error parsing response:', e);
            }
        },
        error: function(xhr, status, error) {
            alert('服务器连接失败，请检查网络！');
        }
    });
}      