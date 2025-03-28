import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
from flask_migrate import Migrate


db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = "auth.login"
login.login_message = "Please sign in to access this page"


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.main import bp as main_pb
    app.register_blueprint(main_pb)

    return app


from app import models
