# SSH 远程开发连接指南

> 适用范围：开发者首次配置 SSH 远程连接，或在新机器上恢复开发环境。

## 服务器信息

| 项目 | 值 |
|---|---|
| SSH 别名 | `stratagy` |
| 项目目录 | `/opt/stratagy` |

> SSH 别名 `stratagy` 对应的主机地址和登录用户由本地 `~/.ssh/config` 配置，详见下方步骤一。

---

## 一、配置本地 SSH 别名

在本地机器的 `~/.ssh/config`（Windows：`C:\Users\<你的用户名>\.ssh\config`）中添加以下内容（地址和用户由服务器提供方确认）：

```
Host stratagy
    HostName <服务器IP或域名>
    User <登录用户>
    IdentityFile ~/.ssh/id_rsa
```

> 若使用其他密钥文件，将 `~/.ssh/id_rsa` 替换为实际路径。

配置完成后验证连接：

```bash
ssh stratagy
```

---

## 二、VS Code Remote-SSH 连接

1. 安装扩展：[Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh)
2. 按 `Ctrl+Shift+P` → `Remote-SSH: Connect to Host...`
3. 选择 `stratagy`
4. 连接成功后，点击左下角 `Open Folder`，输入 `/opt/stratagy`

> **不要**在本地克隆仓库后再新建工作区。直接通过 Remote-SSH 打开服务器上的目录即可。

---

## 三、Cursor Remote-SSH 连接

1. 安装 Cursor 后，同样支持 Remote-SSH 扩展（继承自 VS Code）
2. 步骤与 VS Code 相同：`Ctrl+Shift+P` → `Remote-SSH: Connect to Host...` → `stratagy` → `/opt/stratagy`

---

## 四、常用运维命令（连接后在服务器执行）

```bash
# 查看应用运行状态
systemctl status stratagy

# 重启应用
systemctl restart stratagy

# 查看实时日志
journalctl -u stratagy -f

# 查看最近 50 条日志
journalctl -u stratagy -n 50 --no-pager
```

---

## 五、本地同步增量更新（可选）

若在本地修改了代码并需要推送到服务器，使用以下脚本：

```bat
# 增量同步（Windows）
deploy\sync.bat

# 全量上传并重新部署（Windows）
deploy\upload_and_deploy.bat
```

支持 `--dry-run` 参数预览操作，不实际执行。

---

## 注意事项

- **不要创建新的本地工作区**，直接 SSH 远程连接到 `/opt/stratagy` 进行开发。
- 代码修改后，服务会自动读取新文件（Streamlit 热重载），必要时手动重启：`systemctl restart stratagy`。
- 应用访问地址：[https://www.gfm156.com/strategy](https://www.gfm156.com/strategy)
