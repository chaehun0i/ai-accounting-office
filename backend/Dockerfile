FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-dev.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.lock
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini docker-entrypoint.py ./
RUN pip install --no-deps -e . && useradd --create-home --uid 10001 office && mkdir /app/storage && chown office:office /app/storage
USER office
EXPOSE 8000
CMD ["python", "docker-entrypoint.py"]
