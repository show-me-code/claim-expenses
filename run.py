"""
差旅费用报销系统 - 一键启动
双击此文件即可启动系统
"""
import os
import sys
import subprocess
import threading
import time
import webbrowser

# 配置
PYTHON_EXE = 'python'  # 使用系统Python，或修改为你的Python路径
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_DIR, 'src', 'backend')
SERVER_URL = 'http://localhost:5000'

def main():
    print("=" * 50)
    print("  差旅费用报销系统 - 正在启动...")
    print("=" * 50)
    print()

    # 创建目录
    os.makedirs(os.path.join(PROJECT_DIR, 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_DIR, 'output'), exist_ok=True)

    # 启动后端
    print("[启动后端服务器]")
    os.chdir(BACKEND_DIR)
    proc = subprocess.Popen([PYTHON_EXE, 'app.py'])

    # 等待服务器就绪
    print("等待服务器就绪...")
    time.sleep(6)

    # 打开浏览器
    print("[打开浏览器]")
    webbrowser.open(SERVER_URL)

    print()
    print("=" * 50)
    print("  系统已启动!")
    print(f"  请在浏览器中使用: {SERVER_URL}")
    print(f"  Excel报表目录: {os.path.join(PROJECT_DIR, 'output')}")
    print("=" * 50)
    print()
    print("关闭此窗口将停止服务器")
    print()

    # 等待用户输入
    input("按 Enter 键停止服务器...")

    proc.terminate()
    print("服务器已停止")

if __name__ == '__main__':
    main()