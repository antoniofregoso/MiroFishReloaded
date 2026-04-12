"""
Configuración
Carga la configuración desde el archivo .env en el directorio raíz del proyecto
"""

import os
from dotenv import load_dotenv

# Carga el archivo .env en el directorio raíz del proyecto
# Ruta: MiroFish/.env (relativo a backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # Si no hay .env en el directorio raíz, intenta cargar variables de entorno (para entorno de producción)
    load_dotenv(override=True)


class Config:
    """Clase de configuración de Flask"""
    
    # Configuración de Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # Configuración de JSON - Deshabilita el escape ASCII para que los caracteres chinos se muestren directamente (en lugar del formato \uXXXX)
    JSON_AS_ASCII = False
    
    # Configuración de LLM (usa el formato OpenAI统一)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    
    # Configuración de Zep
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # Configuración de carga de archivos
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # Configuración de procesamiento de texto
    DEFAULT_CHUNK_SIZE = 500  # Tamaño de chunk predeterminado
    DEFAULT_CHUNK_OVERLAP = 50  # Superposición de chunk predeterminada
    
    # Configuración de simulación OASIS
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # Configuración de acciones disponibles en la plataforma OASIS
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def validate(cls):
        """Valida la configuración necesaria"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY no configurado")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY no configurado")
        return errors

