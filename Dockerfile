# Базовый легковесный образ Python 3.11
FROM python:3.11-slim

# Установка рабочей директории внутри контейнера
WORKDIR /app

# Отключение буферизации вывода для мгновенного отображения логов в Railway Dashboard
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Копирование зависимостей и установка
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода проекта
COPY . .

# Команда запуска бота
CMD ["python", "main.py"]
