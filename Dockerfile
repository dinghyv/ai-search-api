FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY db.py so.py api_server.py mcp_server.py admin_ui.py ./
COPY engines ./engines

ENV HOST=0.0.0.0
ENV PORT=8787
ENV DB_PATH=/app/data/search_api.db

VOLUME ["/app/data"]
EXPOSE 8787

CMD ["python", "api_server.py"]
