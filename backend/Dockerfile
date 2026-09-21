# KnowRAG 后端镜像
# 基础镜像 Python 版本与本机 conda 环境（3.13.14）保持一致，避免依赖编译差异。
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先只复制依赖清单，让 pip 安装层可以被后续代码改动复用缓存。
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 使用非 root 用户运行，降低容器逃逸后的影响面。
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 健康检查直接打应用自身的 /health，避免仅检测端口开放而漏掉应用未就绪的情况。
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
