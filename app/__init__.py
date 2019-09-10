from flask import Flask
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_caching import Cache
from celery import Celery

from app.flask_celery import make_celery

bootstrap = Bootstrap()
db = SQLAlchemy()
cache = Cache()

def create_app(config_name):
    app = Flask(__name__)
    if config_name == 'testing':
        app.config.from_object("app.config.testing")
    else:
        app.config.from_object("app.config.default")
    
    
    app.config.from_envvar("OGN_CONFIG_MODULE", silent=True)
    
    # Initialize other things
    bootstrap.init_app(app)
    db.init_app(app)
    cache.init_app(app)
    #celery = make_celery(app)
    #migrate = Migrate(app, db)

    from app.main import bp as blueprint_main
    app.register_blueprint(blueprint_main)
    
    return app
