FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip curl ca-certificates zstd && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .

ENV API_HOST=0.0.0.0 \
    API_PORT=8000 \
    START_OLLAMA=true \
    OLLAMA_BASE_URL=http://localhost:11434 \
    OLLAMA_MODEL=llama3.2:3b \
    PROMPT_SOURCE=hardcoded

EXPOSE 8000
EXPOSE 11434

CMD ["/bin/bash", "run.sh"]
