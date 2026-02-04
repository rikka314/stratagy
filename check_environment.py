#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境检查脚本
运行此脚本以检查系统环境是否满足应用运行要求
"""

import sys
import subprocess
from typing import Tuple

def print_header(text: str):
    """打印分隔线标题"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_success(text: str):
    """打印成功信息"""
    print(f"✅ {text}")

def print_error(text: str):
    """打印错误信息"""
    print(f"❌ {text}")

def print_warning(text: str):
    """打印警告信息"""
    print(f"⚠️  {text}")

def check_python_version() -> bool:
    """检查 Python 版本"""
    print_header("检查 Python 版本")
    
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    print(f"当前 Python 版本: {version_str}")
    print(f"Python 路径: {sys.executable}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_error(f"Python 版本过低！需要 3.8+，当前为 {version_str}")
        return False
    elif version.minor < 10:
        print_warning(f"Python 版本较旧，推荐使用 3.10+")
        return True
    else:
        print_success(f"Python 版本符合要求")
        return True

def check_package(package_name: str, import_name: str = None) -> Tuple[bool, str]:
    """检查单个包是否安装"""
    if import_name is None:
        import_name = package_name
    
    try:
        module = __import__(import_name)
        version = getattr(module, '__version__', 'unknown')
        return True, version
    except ImportError:
        return False, None

def check_dependencies() -> bool:
    """检查所有依赖包"""
    print_header("检查依赖包")
    
    packages = [
        ("streamlit", "streamlit"),
        ("akshare", "akshare"),
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("plotly", "plotly"),
        ("optuna", "optuna"),
    ]
    
    all_installed = True
    missing_packages = []
    
    for package_name, import_name in packages:
        installed, version = check_package(package_name, import_name)
        
        if installed:
            print_success(f"{package_name:15s} {version}")
        else:
            print_error(f"{package_name:15s} 未安装")
            all_installed = False
            missing_packages.append(package_name)
    
    if not all_installed:
        print("\n" + "-" * 60)
        print("缺失的包可以通过以下命令安装：")
        print(f"pip install {' '.join(missing_packages)}")
        print("\n或安装所有依赖：")
        print("pip install -r requirements.txt")
    
    return all_installed

def check_network() -> bool:
    """检查网络连接（测试获取股票数据）"""
    print_header("检查网络连接和数据获取")
    
    try:
        print("正在测试 AkShare 数据获取...")
        import akshare as ak
        import pandas as pd
        
        # 测试获取少量数据
        df = ak.stock_us_daily(symbol='AAPL', adjust='qfq')
        
        if df is not None and len(df) > 0:
            print_success(f"数据获取成功！获得 {len(df)} 行数据")
            print(f"最新日期: {df.iloc[-1][0]}")
            return True
        else:
            print_error("数据获取失败：返回数据为空")
            return False
            
    except ImportError:
        print_error("AkShare 未安装，无法测试数据获取")
        return False
    except Exception as e:
        print_error(f"数据获取失败: {str(e)}")
        print_warning("请检查网络连接")
        return False

def check_file_structure() -> bool:
    """检查文件结构"""
    print_header("检查文件结构")
    
    import os
    
    required_files = [
        "app.py",
        "requirements.txt",
        "README.md",
    ]
    
    required_dirs = [
        "data",
        "document",
    ]
    
    all_present = True
    
    for file in required_files:
        if os.path.exists(file):
            print_success(f"文件存在: {file}")
        else:
            print_error(f"文件缺失: {file}")
            all_present = False
    
    for directory in required_dirs:
        if os.path.exists(directory) and os.path.isdir(directory):
            file_count = len(os.listdir(directory))
            print_success(f"目录存在: {directory}/ ({file_count} 个文件)")
        else:
            print_warning(f"目录缺失: {directory}/")
    
    return all_present

def get_system_info():
    """获取系统信息"""
    print_header("系统信息")
    
    import platform
    
    print(f"操作系统: {platform.system()} {platform.release()}")
    print(f"处理器: {platform.processor() or platform.machine()}")
    print(f"Python 实现: {platform.python_implementation()}")
    
    try:
        import psutil
        mem = psutil.virtual_memory()
        print(f"内存: {mem.total / (1024**3):.1f} GB (可用: {mem.available / (1024**3):.1f} GB)")
        print(f"CPU 核心数: {psutil.cpu_count(logical=False)} 物理核心, {psutil.cpu_count()} 逻辑核心")
    except ImportError:
        print_warning("未安装 psutil，无法获取详细系统信息")

def main():
    """主函数"""
    print("\n" + "🔍 量化交易策略分析器 - 环境检查工具" + "\n")
    
    results = {}
    
    # 1. 检查 Python 版本
    results['python'] = check_python_version()
    
    # 2. 检查依赖包
    results['dependencies'] = check_dependencies()
    
    # 3. 检查文件结构
    results['files'] = check_file_structure()
    
    # 4. 获取系统信息
    get_system_info()
    
    # 5. 检查网络（可选，较慢）
    print("\n是否测试网络连接和数据获取？（需要几秒钟）")
    user_input = input("输入 y/n (默认 y): ").strip().lower()
    
    if user_input != 'n':
        results['network'] = check_network()
    
    # 总结
    print_header("检查结果总结")
    
    all_passed = all(results.values())
    
    if all_passed:
        print_success("所有检查通过！环境配置正确。")
        print("\n可以运行以下命令启动应用：")
        print("  streamlit run app.py")
        print("\n或直接双击启动脚本：")
        print("  macOS/Linux: 启动应用.command")
        print("  Windows: 启动应用.bat")
    else:
        print_error("部分检查未通过，请根据上述提示修复问题。")
        
        if not results.get('dependencies', True):
            print("\n建议先安装依赖：")
            print("  pip install -r requirements.txt")
    
    print("\n" + "=" * 60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  检查被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
