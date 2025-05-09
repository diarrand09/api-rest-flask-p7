# app/__init__.py
from flask import Flask
from flask_jwt_extended import JWTManager
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import timedelta

# Importer la configuration
from app.config import config

# Initialiser l'application Flask
def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialiser JWT
    jwt = JWTManager(app)
    
    # Configurer la connexion à la base de données
    def get_db_connection():
        conn = psycopg2.connect(
            host=app.config['DB_HOST'],
            database=app.config['DB_NAME'],
            user=app.config['DB_USER'],
            password=app.config['DB_PASSWORD'],
            cursor_factory=RealDictCursor
        )
        return conn
    
    # Rendre la connexion disponible pour les routes
    app.config['get_db_connection'] = get_db_connection
    
    # Enregistrer les blueprints pour les routes
    from app.routes import users, groups, prompts, votes, notes, achats
    
    app.register_blueprint(users.bp)
    app.register_blueprint(groups.bp)
    app.register_blueprint(prompts.bp)
    app.register_blueprint(votes.bp)
    app.register_blueprint(notes.bp)
    app.register_blueprint(achats.bp)
    
    return app

# app/config.py
import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'votre_clé_secrète_par_défaut'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'votre_clé_jwt_par_défaut'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_NAME = os.environ.get('DB_NAME') or 'pojat_db'
    DB_USER = os.environ.get('DB_USER') or 'postgres'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or 'postgres'

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True
    DB_NAME = 'pojat_test_db'

class ProductionConfig(Config):
    DEBUG = False
    # En production, assurez-vous d'avoir défini les variables d'environnement appropriées

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# app/utils/db.py
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import current_app

def get_db_connection():
    """
    Crée une connexion à la base de données PostgreSQL
    """
    return current_app.config['get_db_connection']()

def execute_query(query, params=None, fetch=True):
    """
    Exécute une requête SQL et retourne le résultat
    
    Args:
        query (str): Requête SQL à exécuter
        params (tuple, optional): Paramètres pour la requête
        fetch (bool, optional): Si True, retourne le résultat de la requête
        
    Returns:
        list: Résultat de la requête si fetch=True, None sinon
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                result = cur.fetchall()
            else:
                result = None
            conn.commit()
            return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# app/utils/auth.py
from flask_jwt_extended import create_access_token, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils.db import execute_query

def authenticate_user(email, password):
    """
    Authentifie un utilisateur et retourne un token JWT
    
    Args:
        email (str): Email de l'utilisateur
        password (str): Mot de passe de l'utilisateur
        
    Returns:
        dict: Informations de l'utilisateur avec le token JWT
    """
    query = """
    SELECT id_utilisateur, email, password, role
    FROM utilisateur
    WHERE email = %s
    """
    
    result = execute_query(query, (email,))
    
    if not result:
        return None
    
    user = result[0]
    
    if not check_password_hash(user['password'], password):
        return None
    
    # Créer le token JWT
    additional_claims = {
        'role': user['role']
    }
    
    access_token = create_access_token(
        identity=user['id_utilisateur'],
        additional_claims=additional_claims
    )
    
    return {
        'id': user['id_utilisateur'],
        'email': user['email'],
        'role': user['role'],
        'access_token': access_token
    }

def hash_password(password):
    """
    Génère un hash sécurisé du mot de passe
    
    Args:
        password (str): Mot de passe en clair
        
    Returns:
        str: Hash du mot de passe
    """
    return generate_password_hash(password)

# run.py
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)