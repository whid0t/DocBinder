FROM python:3.12-slim
WORKDIR /app
COPY matrix-bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY matrix-bot/docbinder_bot ./docbinder_bot
CMD ["python", "-m", "docbinder_bot"]

