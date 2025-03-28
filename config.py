import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'

    # MySQL configuration for Amazon Lightsail
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_HOST = os.environ.get('DB_HOST')
    DB_PORT = os.environ.get('DB_PORT') or '3306'
    DB_NAME = os.environ.get('DB_NAME')

    # Construct MySQL connection string
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload folder configuration
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB max upload size