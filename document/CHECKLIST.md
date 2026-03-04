# ✅ 其他电脑部署检查清单

## 📋 部署前准备

### 1. 文件打包
- [ ] 确认所有必需文件都在项目文件夹中
- [ ] 压缩整个 `stratagy` 文件夹为 ZIP
- [ ] 压缩包大小合理（< 100MB，不含大量CSV数据）

### 2. 测试环境（当前电脑）
- [x] Python 3.13.5 已安装 ✅
- [x] 所有依赖包已安装 ✅
- [x] 应用可正常启动 ✅
- [x] 环境检查脚本通过 ✅

---

## 🖥️ 目标电脑部署步骤

### Windows 电脑

#### 步骤 1：安装 Python
```powershell
# 下载 Python 3.10+ from python.org
# 安装时勾选 "Add Python to PATH"
python --version  # 验证安装
```

#### 步骤 2：解压项目
```powershell
# 解压 ZIP 到任意位置
# 例如：C:\Users\YourName\stratagy
cd C:\Users\YourName\stratagy
```

#### 步骤 3：运行环境检查
```powershell
python check_environment.py
```

#### 步骤 4：安装依赖（如需要）
```powershell
pip install -r requirements.txt

# 如果慢，使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 步骤 5：启动应用
```powershell
# 方法1：双击运行
启动应用.bat

# 方法2：命令行运行
streamlit run app.py
```

---

### macOS 电脑

#### 步骤 1：安装 Python
```bash
# 检查是否已安装
python3 --version

# 如未安装，从 python.org 下载
# 或使用 Homebrew
brew install python@3.10
```

#### 步骤 2：解压项目
```bash
# 解压 ZIP 到任意位置
cd ~/Downloads/stratagy
```

#### 步骤 3：赋予执行权限
```bash
chmod +x 启动应用.command
chmod +x check_environment.py
```

#### 步骤 4：运行环境检查
```bash
python3 check_environment.py
```

#### 步骤 5：安装依赖（如需要）
```bash
pip3 install -r requirements.txt
```

#### 步骤 6：启动应用
```bash
# 方法1：双击运行
# 启动应用.command

# 方法2：命令行运行
./启动应用.command
```

---

### Linux 电脑 (Ubuntu/Debian)

#### 步骤 1：安装 Python 和 pip
```bash
sudo apt update
sudo apt install python3 python3-pip
python3 --version
```

#### 步骤 2：解压项目
```bash
unzip stratagy.zip
cd stratagy
```

#### 步骤 3：赋予执行权限
```bash
chmod +x 启动应用.command
chmod +x check_environment.py
```

#### 步骤 4：运行环境检查
```bash
python3 check_environment.py
```

#### 步骤 5：安装依赖
```bash
pip3 install -r requirements.txt
```

#### 步骤 6：启动应用
```bash
./启动应用.command
```

---

## 🔍 兼容性测试清单

### 环境兼容性
- [ ] Python 3.8 - 3.9（基础兼容）
- [ ] Python 3.10 - 3.11（推荐版本）
- [ ] Python 3.12+（最新版本，应兼容）

### 操作系统兼容性
- [ ] Windows 10 / 11
- [ ] macOS 10.14+ (Mojave)
- [ ] Ubuntu 18.04+ / Debian 10+
- [ ] CentOS / RHEL 7+

### 依赖包兼容性测试

#### 核心依赖
```bash
# Streamlit (Web框架)
python -c "import streamlit; print(f'Streamlit {streamlit.__version__}')"

# AkShare (数据源)
python -c "import akshare; print('AkShare OK')"

# Pandas (数据处理)
python -c "import pandas; print(f'Pandas {pandas.__version__}')"

# Numpy (数值计算)
python -c "import numpy; print(f'NumPy {numpy.__version__}')"

# Plotly (可视化)
python -c "import plotly; print(f'Plotly {plotly.__version__}')"

# Optuna (优化)
python -c "import optuna; print(f'Optuna {optuna.__version__}')"
```

---

## 🐛 常见问题预案

### 问题 1：Python 版本过低
**症状**：`SyntaxError` 或 `ImportError`

**解决**：
```bash
# 升级 Python
# Windows: 重新下载安装
# macOS: brew upgrade python
# Linux: 使用 deadsnakes PPA (Ubuntu)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10
```

### 问题 2：pip 命令无法识别
**症状**：`'pip' is not recognized`

**解决**：
```bash
# Windows
python -m pip install -r requirements.txt

# macOS/Linux
python3 -m pip install -r requirements.txt
```

### 问题 3：依赖安装失败
**症状**：`Could not find a version that satisfies the requirement`

**解决**：
```bash
# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或逐个安装
pip install streamlit -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install akshare -i https://pypi.tuna.tsinghua.edu.cn/simple
# ...
```

### 问题 4：无法启动 Streamlit
**症状**：`ModuleNotFoundError: No module named 'streamlit'`

**解决**：
```bash
# 确认 streamlit 已安装
pip show streamlit

# 重新安装
pip install --upgrade streamlit
```

### 问题 5：端口被占用
**症状**：`Address already in use`

**解决**：
```bash
# 更换端口
streamlit run app.py --server.port 8502

# 或关闭占用进程（见 DEPLOYMENT.md）
```

---

## 📊 性能基准测试

在目标电脑上运行基准测试：

### 测试 1：数据加载速度
```python
import time
import akshare as ak

start = time.time()
df = ak.stock_us_daily(symbol='AAPL', adjust='qfq')
elapsed = time.time() - start

print(f"数据行数: {len(df)}")
print(f"加载耗时: {elapsed:.2f} 秒")
# 预期：< 5 秒
```

### 测试 2：参数优化速度
```
# 在应用中运行贝叶斯优化 60 次
# 预期耗时：
# - 快速电脑（8核+）：20-30 秒
# - 普通电脑（4核）：40-60 秒
# - 慢速电脑（2核）：80-120 秒
```

### 测试 3：内存使用
```bash
# 运行应用后检查内存
# 预期：< 500MB
```

---

## 🌐 网络要求

### 必需网络连接
- [x] 首次安装依赖包（需要 PyPI 访问）
- [x] 获取股票数据（需要 AkShare API 访问）

### 离线使用
- [ ] 依赖包已安装 → 可离线运行应用框架
- [ ] 股票数据已下载到 `data/` → 可离线回测
- [ ] 新数据获取 → **需要联网**

### 网络速度建议
- 最低：1 Mbps
- 推荐：10 Mbps+

---

## 🔒 防火墙配置

### Windows Defender
```
首次运行时可能弹出防火墙提示
→ 选择"允许访问"
```

### 端口访问
```
默认端口：8501
局域网访问需要：
- 防火墙允许 8501 端口入站
- 或临时关闭防火墙测试
```

---

## 📦 打包清单

### 必需文件
```
stratagy/
├── app.py                 ✅ 主程序
├── requirements.txt       ✅ 依赖列表
├── check_environment.py   ✅ 环境检查
├── 启动应用.command       ✅ macOS/Linux 启动
├── 启动应用.bat           ✅ Windows 启动
├── README.md             ✅ 项目说明
├── DEPLOYMENT.md         ✅ 部署指南
└── CHECKLIST.md          ✅ 本检查清单
```

### 可选文件
```
├── data/                 📁 股票数据（可选）
│   ├── aapl_daily.csv
│   └── ...
├── document/             📁 文档（推荐）
│   ├── CODE_EXPLANATION.md
│   ├── STRATEGY_IMPROVEMENT.md
│   └── ...
└── .gitignore           🔧 Git配置（可选）
```

---

## ✅ 最终验证

在目标电脑上执行以下验证：

### 1. 环境检查通过
```bash
python3 check_environment.py
# 应显示：✅ 所有检查通过！
```

### 2. 应用正常启动
```bash
streamlit run app.py
# 应在浏览器打开 http://localhost:8501
```

### 3. 功能测试
- [ ] 侧边栏显示正常
- [ ] 可以选择股票
- [ ] 数据加载成功
- [ ] 图表显示正常
- [ ] 参数调整生效
- [ ] 回测计算正确
- [ ] 参数优化可运行

### 4. 性能测试
- [ ] 页面响应 < 2 秒
- [ ] 图表渲染流畅
- [ ] 参数优化合理耗时

---

## 📞 支持渠道

如果在其他电脑部署遇到问题：

1. **查看文档**
   - `DEPLOYMENT.md` - 详细部署指南
   - `README.md` - 项目说明

2. **运行诊断**
   ```bash
   python check_environment.py
   ```

3. **查看日志**
   ```bash
   # Streamlit 日志
   ~/.streamlit/logs/
   ```

4. **联系支持**
   - 提供：操作系统、Python版本、错误信息
   - 附上：`check_environment.py` 的输出

---

## 🎯 部署成功标准

当以下所有项目都 ✅ 时，部署成功：

- [x] 环境检查脚本通过
- [x] 应用可以启动
- [x] 浏览器可以访问
- [x] 所有核心功能正常
- [x] 性能符合预期
- [x] 无报错或警告

**恭喜！应用已成功部署到新电脑！** 🎉

---

**文档版本**：v1.0  
**最后更新**：2026-02-04  
**适用系统**：Windows / macOS / Linux
