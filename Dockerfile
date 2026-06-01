FROM ubuntu:24.04

RUN apt update && \
    apt install -y python3 python3-pip curl zstd

RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app

COPY requirements.txt .
RUN pip3 install -r requirements.txt --break-system-packages

COPY . .

EXPOSE 8000
EXPOSE 11434

CMD ollama serve & \
    sleep 5 && \
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000