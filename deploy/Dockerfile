FROM python:3.12-slim

# 1. 设置时区 (关键！)
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 2. 安装系统依赖
# libpq-dev: postgres 驱动需要
# locales: 中文支持
# pkg-config: 编译数据库驱动时可能需要
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    locales \
    tzdata \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 3. 配置中文 Locale (关键！CTP报错常见原因)
RUN sed -i '/zh_CN.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen
ENV LANG=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8

WORKDIR /app

# 4. 依赖层
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 代码层
COPY . .

# 默认命令，会被 compose 覆盖
CMD ["python", "src/main/main.py"]
