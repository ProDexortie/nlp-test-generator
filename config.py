import os
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()

class Config:
    # Базовые настройки
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
    
    # Настройки MongoDB
    MONGO_URI = os.environ.get('MONGO_URI') or 'no mongodb_URI provided'
    
    # Настройки NLP
    SPACY_MODEL = os.environ.get('SPACY_MODEL') or 'ru_core_news_md'
    
    # Настройки тестов
    DEFAULT_QUESTIONS_COUNT = 10
    DEFAULT_TEST_DURATION = 30  # в минутах
    
    # Настройки приложения
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 МБ максимальный размер файла