"""
MiroFish Backend 启动入口
"""

import os
import sys

# Solucionar el problema de visualización de caracteres chinos en la consola de Windows: establecer la codificación UTF-8 antes de todas las importaciones
if sys.platform == 'win32':
    # Establecer la variable de entorno para asegurar que Python use UTF-8
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    # Reconfigurar el flujo de salida estándar a UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Agregar el directorio raíz del proyecto a la ruta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def main():
    """Función principal"""
    # Validar configuración
    errors = Config.validate()
    if errors:
        print("Errores de configuración:")
        for err in errors:
            print(f"  - {err}")
        print("\nPor favor, revise la configuración en el archivo .env")
        sys.exit(1)
    
    # Crear aplicación
    app = create_app()
    
    # Obtener configuración de ejecución
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG
    
    # Iniciar servicio
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    main()

