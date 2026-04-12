"""
Mecanismo de reintento de llamadas a la API: Gestiona la lógica de reintento 
para llamadas a API externas como LLM.
"""

import time
import random
import functools
from typing import Callable, Any, Optional, Type, Tuple
from ..utils.logger import get_logger

logger = get_logger('mirofish.retry')


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorador con retroceso exponencial
    
    Args:
        max_retries: Número máximo de reintentos
        initial_delay: Retraso inicial (segundos)
        max_delay: Retraso máximo (segundos)
        backoff_factor: Factor de retroceso
        jitter: Agregar jitter aleatorio
        exceptions: Tipos de excepciones a reintentar
        on_retry: Función de devolución de llamada al reintentar (excepción, recuento de reintentos)
    
    Usage:
        @retry_with_backoff(max_retries=3)
        def call_llm_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"La función {func.__name__} falló después de {max_retries} reintentos: {str(e)}")
                        raise
                    
                    # Calcular retraso
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"La función {func.__name__} falló en el intento {attempt + 1}: {str(e)}, "
                        f"reintentando en {current_delay:.1f} segundos..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    time.sleep(current_delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Versión asíncrona del decorador de reintentos
    """
    import asyncio
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"La función asíncrona {func.__name__} falló después de {max_retries} reintentos: {str(e)}")
                        raise
                    
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"La función asíncrona {func.__name__} falló en el intento {attempt + 1}: {str(e)}, "
                        f"reintentando en {current_delay:.1f} segundos..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    await asyncio.sleep(current_delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


class RetryableAPIClient:
    """
    Cliente API reintentable
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def call_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        **kwargs
    ) -> Any:
        """
        Ejecuta la llamada a la función y reintenta si falla
        
        Args:
            func: Función a llamar
            *args: Argumentos de la función
            exceptions: Tipos de excepciones a reintentar
            **kwargs: Argumentos de palabra clave de la función
            
        Returns:
            Valor de retorno de la función
        """
        last_exception = None
        delay = self.initial_delay
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
                
            except exceptions as e:
                last_exception = e
                
                if attempt == self.max_retries:
                    logger.error(f"API调用在 {self.max_retries} 次重试后仍失败: {str(e)}")
                    raise
                
                current_delay = min(delay, self.max_delay)
                current_delay = current_delay * (0.5 + random.random())
                
                logger.warning(
                    f"La llamada a la API falló en el intento {attempt + 1}: {str(e)}, "
                    f"reintentando en {current_delay:.1f} segundos..."
                )
                
                time.sleep(current_delay)
                delay *= self.backoff_factor
        
        raise last_exception
    
    def call_batch_with_retry(
        self,
        items: list,
        process_func: Callable,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        continue_on_failure: bool = True
    ) -> Tuple[list, list]:
        """
        Llama por lotes y reintenta individualmente cada elemento fallido
        
        Args:
            items: Lista de elementos a procesar
            process_func: Función de procesamiento que acepta un solo item como parámetro
            exceptions: Tipos de excepciones a reintentar
            continue_on_failure: Si falla un elemento, ¿continuar procesando los demás?
            
        Returns:
            (Lista de resultados exitosos, Lista de elementos fallidos)
        """
        results = []
        failures = []
        
        for idx, item in enumerate(items):
            try:
                result = self.call_with_retry(
                    process_func,
                    item,
                    exceptions=exceptions
                )
                results.append(result)
                
            except Exception as e:
                logger.error(f"处理第 {idx + 1} 项失败: {str(e)}")
                failures.append({
                    "index": idx,
                    "item": item,
                    "error": str(e)
                })
                
                if not continue_on_failure:
                    raise
        
        return results, failures

