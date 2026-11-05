FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home servicio
COPY *.py ./
RUN mkdir /app/datos && chown servicio:servicio /app/datos
USER servicio
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
