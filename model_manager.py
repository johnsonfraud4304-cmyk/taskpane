"""
TaskPane 模型管理工具
- 切换默认模型
- 列出可用模型
- 简单的速度对比
"""
import subprocess
import requests
import time
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def run(cmd):
    """Run shell command with conda env cleared"""
    env = os.environ.copy()
    for k in ["CONDA_DEFAULT_ENV", "CONDA_PREFIX", "CONDA_SHLVL"]:
        env.pop(k, None)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)


def list_models():
    """列出已下载模型"""
    r = run(["ollama", "list"])
    print("已下载模型:")
    print(r.stdout)


def recommend():
    """根据硬件推荐模型"""
    import platform
    print(f"\n你的硬件: {platform.machine()}")
    r = run(["sysctl", "hw.memsize"])
    mem_gb = int(r.stdout.split()[1]) / 1024**3
    print(f"内存: {mem_gb:.0f} GB")
    print()
    if mem_gb < 12:
        print("推荐: qwen2:0.5b (轻量)")
    elif mem_gb < 20:
        print("推荐: qwen2.5:7b (你的情况)")
        print("备选: qwen2.5:3b (更快), deepseek-r1:8b (推理)")
    else:
        print("推荐: qwen2.5:14b")
    print()


def benchmark(model, prompt="用一句话介绍你自己"):
    """测模型速度"""
    print(f"\n测速 {model}...")
    r = requests.post("http://127.0.0.1:11434/api/generate",
                      json={"model": model, "prompt": prompt, "stream": False},
                      timeout=120)
    d = r.json()
    evals = d.get('eval_count', 0)
    dur = d.get('eval_duration', 1) / 1e9
    speed = evals / dur if dur > 0 else 0
    print(f"  生成 tokens: {evals}")
    print(f"  耗时: {dur:.2f}s")
    print(f"  速度: {speed:.1f} tok/s")
    print(f"  响应: {d.get('response', '')[:100]}")
    return speed


def main():
    print("=" * 60)
    print("TaskPane 模型管理工具")
    print("=" * 60)
    list_models()
    recommend()
    print("可用操作:")
    print("  list    - 列出模型")
    print("  bench   - 测速当前模型")
    print("  pull X  - 下载模型 X")
    print("  use X   - 切换默认模型 (写 .env_model)")
    print()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "list":
            list_models()
        elif cmd == "bench":
            model = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("TASKPANE_MODEL", "qwen2.5:7b")
            benchmark(model)
        elif cmd == "pull":
            model = sys.argv[2]
            print(f"下载 {model}...")
            subprocess.Popen(["env"] + [f"-u{k}" for k in
                                      ["CONDA_DEFAULT_ENV", "CONDA_PREFIX", "CONDA_SHLVL"]]
                             + ["ollama", "pull", model])
        elif cmd == "use":
            model = sys.argv[2]
            Path(".env_model").write_text(model)
            os.environ["TASKPANE_MODEL"] = model
            print(f"✅ 默认模型设为 {model}")
            print("   重启 TaskPane 生效: scripts/start.sh")
    else:
        main()