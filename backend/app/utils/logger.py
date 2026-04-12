"""
Configuración de registro
Proporciona gestión unificada de registros, con salida tanto a la consola como a archivos
"""

import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler


def _ensure_utf8_stdout():
    """
    Asegura que stdout/stderr utilicen codificación UTF-8
    Resuelve el problema de visualización incorrecta de caracteres chinos en la consola de Windows
    """
    if sys.platform == 'win32':
        # En Windows, reconfigura la salida estándar a UTF-8
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')


def setup_logger(name: str = 'mirofish', level: int = logging.DEBUG) -> logging.Logger:
    """
    Configura el logger
    
    Args:
        name: Nombre del logger
        level: Nivel de registro
        
    Returns:
        Logger configurado
    """
    # Asegura que el directorio de registros exista
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Crear logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Evita que el registro se propague al logger raíz, evitando la salida duplicada
    logger.propagate = False
    
    # Si ya tiene manejadores, no agregues duplicados
    if logger.handlers:
        return logger
    
    # Formato de registro
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 1. Manejador de archivos - Registro detallado (nombre por fecha, con rotación)
    log_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # 2. Manejador de consola - Registro conciso (INFO y superior)
    # Asegura que Windows use codificación UTF-8 para evitar la visualización incorrecta de caracteres chinos
    _ensure_utf8_stdout()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # Agregar manejadores
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str = 'mirofish') -> logging.Logger:
    """
    Obtiene el logger (crea uno si no existe)
    
    Args:
        name: Nombre del logger
        
    Returns:
        Instancia del logger
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# 创建默认日志器
logger = setup_logger()


# 便捷方法
def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
    logger.critical(msg, *args, **kwargs)

