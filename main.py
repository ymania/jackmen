"""Railway 入口 — 从 backend/ 导入 FastAPI app"""
import sys, os, importlib.util

backend = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend)

# 用 importlib 加载 backend/main.py，避免和本文件同名冲突
spec = importlib.util.spec_from_file_location("backend_main", os.path.join(backend, "main.py"))
backend_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_main)

app = backend_main.app
