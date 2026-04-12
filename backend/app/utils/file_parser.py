"""
Herramienta de análisis de archivos
Soporta extracción de texto de archivos PDF, Markdown y TXT
"""

import os
from pathlib import Path
from typing import List, Optional


def _read_text_with_fallback(file_path: str) -> str:
    """
    Lee el archivo de texto, detecta automáticamente la codificación cuando falla UTF-8.
    
    Utiliza una estrategia de retroceso de múltiples niveles:
    1. Primero intenta la decodificación UTF-8
    2. Usa charset_normalizer para detectar la codificación
    3. Retrocede a chardet para detectar la codificación
    4. Finalmente usa UTF-8 + errors='replace' como último recurso
    
    Args:
        file_path: Ruta del archivo
        
    Returns:
        Contenido de texto decodificado
    """
    data = Path(file_path).read_bytes()
    
    # Primero intenta UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    
    # 尝试使用 charset_normalizer 检测编码
    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception:
        pass
    
    # 回退到 chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass
    
    # 最终兜底：使用 UTF-8 + replace
    if not encoding:
        encoding = 'utf-8'
    
    return data.decode(encoding, errors='replace')


class FileParser:
    """Parser de archivos"""
    
    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}
    
    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        Extrae texto del archivo
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            Texto extraído
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
        
        suffix = path.suffix.lower()
        
        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Formato de archivo no soportado: {suffix}")
        
        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)
        
        raise ValueError(f"Formato de archivo no soportado: {suffix}")
    
    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """Extrae texto del PDF"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("Se requiere PyMuPDF: pip install PyMuPDF")
        
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """Extrae texto del Markdown, soporta detección automática de codificación"""
        return _read_text_with_fallback(file_path)
    
    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """Extrae texto del TXT, soporta detección automática de codificación"""
        return _read_text_with_fallback(file_path)
    
    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        Extrae texto de múltiples archivos y los combina
        
        Args:
            file_paths: Lista de rutas de archivos
            
        Returns:
            Texto combinado
        """
        all_texts = []
        
        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== 文档 {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== 文档 {i}: {file_path} (提取失败: {str(e)}) ===")
        
        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str, 
    chunk_size: int = 500, 
    overlap: int = 50
) -> List[str]:
    """
    Divide el texto en trozos
    
    Args:
        text: Texto original
        chunk_size: Número de caracteres por trozo
        overlap: Número de caracteres de superposición
        
    Returns:
        Lista de trozos de texto
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Intenta dividir en el límite de la oración
        if end < len(text):
            # Busca el final de la oración más cercano
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # El siguiente trozo comienza desde la posición de superposición
        start = end - overlap if end < len(text) else len(text)
    
    return chunks

