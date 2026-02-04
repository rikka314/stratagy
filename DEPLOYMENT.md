# 📦 部署与运行指南

## 🚀 快速启动

### macOS / Linux
1. 双击 `启动应用.command` 文件
2. 浏览器自动打开 http://localhost:8501
3. 开始使用！

### Windows
1. 双击 `启动应用.bat` 文件
2. 浏览器自动打开 http://localhost:8501
3. 开始使用！

---

## 📋 系统要求

### 最低配置
- **操作系统**：Windows 10/11、macOS 10.14+、Ubuntu 18.04+
- **Python 版本**：3.8 或更高（推荐 3.10+）
- **内存**：2GB RAM（推荐 4GB+）
- **硬盘空间**：500MB（含依赖库）
- **网络**：需要联网下载股票数据

### 推荐配置
- **Python 版本**：3.10 或 3.11
- **内存**：8GB RAM
- **处理器**：多核 CPU（贝叶斯优化更快）

---

## 🔧 首次安装步骤

### 步骤 1：安装 Python

#### Windows
1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.10+ 安装包
3. **重要**：安装时勾选 "Add Python to PATH"
4. 安装完成后，打开命令提示符验证：
   ```cmd
   python --version
   ```

#### macOS
1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.10+ 安装包
3. 或使用 Homebrew：
   ```bash
   brew install python@3.10
   ```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3.10 python3-pip
```

---

### 步骤 2：运行启动脚本

#### macOS
```bash
# 第一次运行需要赋予执行权限
chmod +x 启动应用.command

# 之后双击运行，或命令行运行
./启动应用.command
```

#### Windows
```cmd
# 直接双击运行
启动应用.bat
```

#### Linux
```bash
chmod +x 启动应用.command
./启动应用.command
```

启动脚本会**自动**：
1. ✅ 检查 Python 版本
2. ✅ 安装所需依赖（首次运行）
3. ✅ 启动应用
4. ✅ 显示访问地址

---

## 📦 手动安装依赖

如果自动安装失败，可以手动安装：

```bash
# 进入项目目录
cd /path/to/stratagy

# 安装依赖
pip install -r requirements.txt

# 或者逐个安装
pip install akshare numpy pandas plotly streamlit optuna
```

---

## 🌐 网络访问（局域网共享）

### 启动应用后，可通过局域网访问：

#### 查看本机 IP 地址

**Windows**:
```cmd
ipconfig
```
找到 "IPv4 地址"，例如：192.168.1.100

**macOS/Linux**:
```bash
ifconfig | grep "inet "
# 或
ip addr show
```

#### 访问地址
- **本机访问**：http://localhost:8501
- **局域网访问**：http://192.168.1.100:8501（替换为实际 IP）

**注意**：确保防火墙允许 8501 端口访问。

---

## 🔍 部署检查清单

### ✅ 环境检查

在命令行运行以下命令检查环境：

```bash
# 1. 检查 Python 版本
python3 --version
# 应输出：Python 3.8.x 或更高

# 2. 检查 pip
pip3 --version

# 3. 测试导入核心库
python3 -c "import streamlit; print('Streamlit:', streamlit.__version__)"
python3 -c "import akshare; print('AkShare: OK')"
python3 -c "import pandas; print('Pandas: OK')"
python3 -c "import numpy; print('NumPy: OK')"
python3 -c "import plotly; print('Plotly: OK')"
python3 -c "import optuna; print('Optuna: OK')"

# 4. 测试数据获取（需要网络）
python3 -c "import akshare as ak; df = ak.stock_us_daily(symbol='AAPL'); print(f'数据行数: {len(df)}')"
```

如果所有命令都成功执行，说明环境配置正确！

---

### ✅ 文件完整性检查

确保以下文件存在：

```
stratagy/
├── app.py                    # 主程序文件
├── requirements.txt          # 依赖列表
├── 启动应用.command          # macOS/Linux 启动脚本
├── 启动应用.bat              # Windows 启动脚本
├── README.md                 # 项目说明
├── data/                     # 数据文件夹
│   ├── aapl_daily.csv
│   ├── googl_daily.csv
│   └── ...
└── document/                 # 文档文件夹
    ├── CODE_EXPLANATION.md
    ├── STRATEGY_IMPROVEMENT.md
    └── ...
```

---

## 🐛 常见问题排查

### 问题 1：Python 命令无法识别

**症状**：
```
'python' 不是内部或外部命令
```

**解决**：
1. 重新安装 Python，勾选 "Add Python to PATH"
2. 或手动添加到环境变量
3. Windows 尝试用 `py` 命令：
   ```cmd
   py --version
   py -m pip install -r requirements.txt
   ```

---

### 问题 2：pip 安装速度慢或失败

**解决**：使用国内镜像源

```bash
# 临时使用清华源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或阿里源
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 永久配置（推荐）
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### 问题 3：端口 8501 被占用

**症状**：
```
OSError: [Errno 48] Address already in use
```

**解决**：

**方法1**：更改端口
```bash
streamlit run app.py --server.port 8502
```

**方法2**：关闭占用端口的进程

macOS/Linux:
```bash
lsof -ti:8501 | xargs kill -9
```

Windows:
```cmd
netstat -ano | findstr :8501
taskkill /PID <进程ID> /F
```

---

### 问题 4：无法下载股票数据

**症状**：
```
ConnectionError / TimeoutError
```

**原因**：
- 网络不通
- AkShare API 限流

**解决**：
1. 检查网络连接
2. 等待几分钟后重试
3. 使用本地数据（已有的 CSV 文件）

---

### 问题 5：macOS 提示"无法打开，因为来自身份不明的开发者"

**解决**：
1. 右键点击 `启动应用.command`
2. 选择"打开"
3. 点击"打开"按钮确认

或者命令行运行：
```bash
chmod +x 启动应用.command
./启动应用.command
```

---

## 📤 打包分发

### 方法 1：直接分享项目文件夹

将整个 `stratagy` 文件夹打包为 ZIP：
1. 确保包含所有文件（app.py, requirements.txt, 启动脚本等）
2. 压缩成 `量化交易策略分析器.zip`
3. 分享给他人
4. 接收者解压后运行启动脚本即可

---

### 方法 2：使用 Docker（高级）

创建 `Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
```

构建和运行：
```bash
docker build -t quant-strategy .
docker run -p 8501:8501 quant-strategy
```

---

### 方法 3：生成可执行文件（实验性）

使用 PyInstaller 打包：

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包（可能遇到兼容性问题）
pyinstaller --onefile --add-data "data:data" app.py
```

**注意**：Streamlit 应用打包成 EXE 可能遇到问题，不推荐此方法。

---

## 🔒 安全建议

### 1. 网络安全
- ⚠️ 默认配置仅限本地访问
- 如需公网访问，请使用反向代理（Nginx）+ HTTPS
- 不要在公网直接暴露 8501 端口

### 2. 数据安全
- 📁 数据文件夹 `data/` 存储在本地
- 不上传到公共仓库（已在 .gitignore）
- 定期备份数据

### 3. API 密钥（如需扩展）
- 不要在代码中硬编码 API 密钥
- 使用环境变量或配置文件
- 示例：
  ```python
  import os
  api_key = os.getenv('STOCK_API_KEY')
  ```

---

## 📊 性能优化

### 1. 数据缓存
- Streamlit 已启用 `@st.cache_data` 装饰器
- 首次加载慢，后续访问快
- 如需清除缓存：侧边栏点击"刷新数据"

### 2. 参数优化速度
- **贝叶斯优化**：60 次试验 ≈ 30 秒
- **随机搜索**：200 次试验 ≈ 60 秒
- CPU 多核可加速

### 3. 大数据量处理
- 如果股票数据超过 10,000 行
- 考虑分段处理或采样

---

## 📞 技术支持

### 问题反馈
- 📧 Email：（填写您的邮箱）
- 🐛 GitHub Issues：（填写仓库地址）

### 日志文件
运行出错时，查看日志：
```bash
# Streamlit 日志路径
~/.streamlit/logs/
```

---

## 🎓 进阶使用

### 1. 自定义配置

创建 `.streamlit/config.toml`:
```toml
[server]
port = 8501
headless = true

[theme]
primaryColor = "#FF4B4B"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
```

### 2. 添加新股票

将 CSV 文件放入 `data/` 文件夹：
- 文件名格式：`symbol_daily.csv`（如 `tsla_daily.csv`）
- 列名：date, open, high, low, close, volume

### 3. 扩展功能

- 添加更多技术指标
- 集成机器学习模型
- 多股票组合优化
- 实时数据推送

---

## ✅ 验证部署成功

在浏览器访问 http://localhost:8501 后：

1. ✅ 页面正常加载
2. ✅ 侧边栏显示股票选择
3. ✅ 可以选择股票并查看数据
4. ✅ 图表正常显示
5. ✅ 参数搜索功能正常
6. ✅ 回测结果正确计算

**恭喜！部署成功！** 🎉

---

## 📝 版本信息

- **应用版本**：v2.0
- **Python 要求**：3.8+
- **最后更新**：2026-02-04
- **维护状态**：活跃维护中

---

## 📄 许可证

本项目仅供学习和研究使用。

**免责声明**：
- 本应用提供的投资建议仅供参考
- 不构成任何投资建议或承诺
- 投资有风险，决策需谨慎
- 使用本应用造成的任何损失，开发者概不负责

---

**祝您使用愉快！** 📈✨
