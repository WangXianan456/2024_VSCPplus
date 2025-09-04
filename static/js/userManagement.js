function fetchUsers() {
    $.ajax({
        url: '/list_users',
        method: 'GET',
        success: function(response) {
            let data = response;
            if (typeof response === 'string') {
                try {
                    data = JSON.parse(response);
                } catch (e) {
                    console.error("Error parsing response:", e);
                    data = [];
                }
            }

            // 修正：如果后端返回的是对象且有 users 字段，则取 users 字段
            if (!Array.isArray(data) && typeof data === 'object' && data.users) {
                data = data.users;
            }

            if (!Array.isArray(data)) {
                console.error("Expected an array but received:", typeof data);
                data = [];
            }
            console.log("Received data:", data);

            let rows = '';
            data.forEach(user => {
                rows += `<tr>
                    <td>${user.id}</td>
                    <td>${user.username}</td>
                    <td>${user.account}</td>
                    <td>
                        <button onclick="showChangePasswordForm(${user.id})">修改密码</button>
                        <button onclick="showEditUserForm(${user.id}, '${user.username}', '${user.account}')">编辑</button>
                        <button onclick="deleteUser(${user.id})">删除</button>
                    </td>
                </tr>`;
            });
            $('#userTable').html(rows);
        },
        error: function(xhr, status, error) {
            console.error("Error fetching users:", error);
        }
    });
}

function deleteUser(id) {
    $.ajax({
        url: '/delete_user',
        method: 'POST',
        data: { id: id },
        success: function(data) {
            if (data.success) {
                alert('用户删除成功');
                fetchUsers();  // 确保重新加载用户列表
            } else {
                alert('删除失败: ' + data.error);
            }
        }
    });
}

function showChangePasswordForm(userId) {
    const newPassword = prompt('请输入新密码:');
    if (newPassword) {
        changeUserPassword(userId, newPassword);
    }
}

function changeUserPassword(userId, newPassword) {
    $.ajax({
        url: '/change_password',
        method: 'POST',
        data: { id: userId, password: newPassword },
        success: function(data) {
            if (data.success) {
                alert('密码修改成功');
            } else {
                alert('密码修改失败: ' + data.error);
            }
        }
    });
}

function showAddUserForm() {
    $('#addUserForm').show();
}

function addUser() {
    const username = $('#newUsername').val();
    const account = $('#newAccount').val();
    const password = $('#newPassword').val();
    $.ajax({
        url: '/add_user',
        method: 'POST',
        data: { username: username, account: account, password: password },
        success: function(data) {
            if (data.success) {
                alert('用户添加成功');
                $('#addUserForm').hide();
                fetchUsers();
            } else {
                alert('添加失败: ' + data.error);
            }
        }
    });
}

function showEditUserForm(userId, username, account) {
    const newUsername = prompt('更新用户名:', username);
    const newAccount = prompt('更新账号:', account);
    if (newUsername && newAccount) {
        updateUser(userId, newUsername, newAccount);
    }
}

function updateUser(userId, username, account) {
    $.ajax({
        url: '/update_user',
        method: 'POST',
        data: { id: userId, username: username, account: account },
        success: function(data) {
            if (data.success) {
                alert('用户信息更新成功');
                fetchUsers();
            } else {
                alert('更新失败: ' + data.error);
            }
        }
    });
}

$(document).ready(function() {
    fetchUsers();
});
