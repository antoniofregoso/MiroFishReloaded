"""
Servicios de procesamiento de texto
"""

from typing import List, Optional
from ..utils.file_parser import FileParser, split_text_into_chunks


class TextProcessor:
    """Procesador de texto"""
    
    @staticmethod
    def extract_from_files(file_paths: List[str]) -> str:
        """Extraer texto de múltiples archivos"""
        return FileParser.extract_from_multiple(file_paths)
    
    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """
        Dividir texto
        
        Args:
            text: Texto original
            chunk_size: Tamaño del bloque
            overlap: Tamaño de solapamiento
            
        Returns:
            Lista de bloques de texto
        """
        return split_text_into_chunks(text, chunk_size, overlap)
    
    @staticmethod
    def preprocess_text(text: str) -> str:
        """
        Preprocesar texto
        - Eliminar espacios en blanco excesivos
        - Normalizar saltos de línea
        
        Args:
            text: Texto original
            
        Returns:
            Texto procesado
        """
        import re
        
        # Normalizar saltos de línea
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Eliminar líneas vacías consecutivas (mantener un máximo de dos saltos de línea)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Eliminar espacios en blanco al principio y al final de cada línea
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    @staticmethod
    def get_text_stats(text: str) -> dict:
        """Obtener estadísticas del texto"""
        return {
            "total_chars": len(text),
            "total_lines": text.count('\n') + 1,
            "total_words": len(text.split()),
        }

