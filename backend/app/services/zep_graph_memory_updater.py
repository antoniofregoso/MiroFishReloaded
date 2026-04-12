"""
El servicio de actualización de memoria del gráfico Zep
actualiza dinámicamente la actividad del agente simulado en el gráfico Zep.
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_locale, set_locale

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Registros de actividad del agente"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        Convierte la actividad en una descripción de texto que se pueda enviar a Zep.
        
        Utiliza un formato de descripción en lenguaje natural para que Zep pueda extraer entidades y relaciones.
        No agrega prefijos relacionados con la simulación para evitar inducir a error la actualización del gráfico.
        """
        # Genera diferentes descripciones según el tipo de acción
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # Devuelve directamente el formato "nombre del agente: descripción de la actividad", sin prefijos de simulación
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"publicó una publicación: 「{content}」"
        return "publicó una publicación"
    
    def _describe_like_post(self) -> str:
        """Me gusta una publicación: incluye la publicación original y la información del autor."""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"le dio like a la publicación de {post_author}: 「{post_content}」"
        elif post_content:
            return f"le dio like a una publicación: 「{post_content}」"
        elif post_author:
            return f"le dio like a una publicación de {post_author}"
        return "le dio like a una publicación"
    
    def _describe_dislike_post(self) -> str:
        """Dislike a una publicación: incluye la publicación original y la información del autor."""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"le dio dislike a la publicación de {post_author}: 「{post_content}」"
        elif post_content:
            return f"le dio dislike a una publicación: 「{post_content}」"
        elif post_author:
            return f"le dio dislike a una publicación de {post_author}"
        return "le dio dislike a una publicación"
    
    def _describe_repost(self) -> str:
        """Retuitea una publicación: incluye el contenido original y la información del autor."""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"retuiteó la publicación de {original_author}: 「{original_content}」"
        elif original_content:
            return f"retuiteó una publicación: 「{original_content}」"
        elif original_author:
            return f"retuiteó una publicación de {original_author}"
        return "retuiteó una publicación"
    
    def _describe_quote_post(self) -> str:
        """Cita una publicación: incluye el contenido original, la información del autor y el comentario de la cita."""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"citó la publicación de {original_author}: 「{original_content}」"
        elif original_content:
            base = f"citó una publicación: 「{original_content}」"
        elif original_author:
            base = f"citó una publicación de {original_author}"
        else:
            base = "citó una publicación"
        
        if quote_content:
            base += f" y comentó: 「{quote_content}」"
        return base
    
    def _describe_follow(self) -> str:
        """Sigue a un usuario: incluye el nombre del usuario seguido."""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"siguió al usuario「{target_user_name}」"
        return "siguió a un usuario"
    
    def _describe_create_comment(self) -> str:
        """Publica un comentario: incluye el contenido del comentario y la información de la publicación comentada."""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"en la publicación「{post_content}」de {post_author} comentó: 「{content}」"
            elif post_content:
                return f"en la publicación「{post_content}」comentó: 「{content}」"
            elif post_author:
                return f"en la publicación de {post_author} comentó: 「{content}」"
            return f"comentó: 「{content}」"
        return "publicó un comentario"
    
    def _describe_like_comment(self) -> str:
        """Le da like a un comentario: incluye el contenido del comentario y la información del autor."""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"le dio like al comentario de {comment_author}: 「{comment_content}」"
        elif comment_content:
            return f"le dio like a un comentario: 「{comment_content}」"
        elif comment_author:
            return f"le dio like al comentario de {comment_author}"
        return "le dio like a un comentario"
    
    def _describe_dislike_comment(self) -> str:
        """Le da dislike a un comentario: incluye el contenido del comentario y la información del autor."""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"le dio dislike al comentario de {comment_author}: 「{comment_content}」"
        elif comment_content:
            return f"le dio dislike a un comentario: 「{comment_content}」"
        elif comment_author:
            return f"le dio dislike al comentario de {comment_author}"
        return "le dio dislike a un comentario"
    
    def _describe_search(self) -> str:
        """Busca publicaciones: incluye las palabras clave de la búsqueda."""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"buscó「{query}」" if query else "realizó una búsqueda"
    
    def _describe_search_user(self) -> str:
        """Busca usuarios: incluye las palabras clave de la búsqueda."""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"buscó al usuario「{query}」" if query else "buscó a un usuario"
    
    def _describe_mute(self) -> str:
        """Silencia a un usuario: incluye el nombre del usuario silenciado."""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"silenció al usuario「{target_user_name}」"
        return "silenció a un usuario"
    
    def _describe_generic(self) -> str:
        # Para tipos de acción desconocidos, genera una descripción genérica
        return f"ejecutó la acción {self.action_type}"


class ZepGraphMemoryUpdater:
    """
    Actualizador de memoria del grafo Zep
    
    Monitorea el archivo de registro de acciones simuladas y actualiza en tiempo real las nuevas actividades del agente al grafo Zep.
    Agrupa por plataforma y envía por lotes a Zep cada BATCH_SIZE actividades acumuladas.
    
    Todas las acciones significativas se actualizarán a Zep, y action_args incluirá información de contexto completa:
    - Contenido original de las publicaciones likeadas/dislikeadas
    - Contenido original de las publicaciones retuiteadas/citadas
    - Nombre de usuario seguido/silenciado
    - Contenido original de los comentarios likeados/dislikeados
    """
    
    # Tamaño del lote (cuántas actividades acumular por plataforma antes de enviar)
    BATCH_SIZE = 5
    
    # Mapeo de nombres de plataforma (para visualización en consola)
    PLATFORM_DISPLAY_NAMES = {
        'twitter': 'Mundo 1',
        'reddit': 'Mundo 2',
    }
    
    # Intervalo de envío (segundos) para evitar solicitudes demasiado frecuentes
    SEND_INTERVAL = 0.5
    
    # Configuración de reintentos
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # segundos
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        Inicializa el actualizador
        
        Args:
            graph_id: ID del grafo Zep
            api_key: Zep API Key (opcional, se lee de la configuración por defecto)
        """
        self.graph_id = graph_id
        self.api_key = api_key or Config.ZEP_API_KEY
        
        if not self.api_key:
            raise ValueError("ZEP_API_KEY no configurado")
        
        self.client = Zep(api_key=self.api_key)
        
        # Cola de actividades
        self._activity_queue: Queue = Queue()
        
        # Búfer de actividades agrupadas por plataforma (cada plataforma acumula hasta BATCH_SIZE antes de enviar)
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # Control flags
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._total_activities = 0  # Actual number of activities added to the queue
        self._total_sent = 0        # Número de lotes enviados exitosamente a Zep
        self._total_items_sent = 0  # Número de actividades enviadas exitosamente a Zep
        self._failed_count = 0      # Número de lotes enviados con error
        self._skipped_count = 0     # Número de actividades omitidas (DO_NOTHING)
        
        logger.info(f"ZepGraphMemoryUpdater inicializado: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def _get_platform_display_name(self, platform: str) -> str:
        """Obtiene el nombre de visualización de la plataforma"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """Inicia el hilo de trabajo en segundo plano"""
        if self._running:
            return

        # Capture locale before spawning background thread
        current_locale = get_locale()

        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(current_locale,),
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater comenzó: graph_id={self.graph_id}")
    
    def stop(self):
        """Detiene el hilo de trabajo en segundo plano"""
        self._running = False
        
        # Envía las actividades restantes
        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(f"ZepGraphMemoryUpdater 已停止: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        Agrega una actividad del agente a la cola
        
        Todas las acciones significativas se agregarán a la cola, incluyendo:
        - CREATE_POST (publicar)
        - CREATE_COMMENT (comentar)
        - QUOTE_POST (citar publicación)
        - SEARCH_POSTS (buscar publicaciones)
        - SEARCH_USER (buscar usuarios)
        - LIKE_POST/DISLIKE_POST (me gusta/no me gusta publicaciones)
        - REPOST (retuitear)
        - FOLLOW (seguir)
        - MUTE (silenciar)
        - LIKE_COMMENT/DISLIKE_COMMENT (me gusta/no me gusta comentarios)
        
        action_args incluirá información de contexto completa (como el contenido original de las publicaciones, nombres de usuario, etc.).
        
        Args:
            activity: Registro de actividad del agente
        """
        # Saltar actividades de tipo DO_NOTHING
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"Agregada actividad a la cola de Zep: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        Agrega actividad desde datos de diccionario
        
        Args:
            data: Datos del diccionario解析 de actions.jsonl
            platform: Nombre de la plataforma (twitter/reddit)
        """
        # Saltar entradas de tipo event_type
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self, locale: str = 'zh'):
        """Bucle de trabajo en segundo plano - Envía actividades a Zep en lotes por plataforma"""
        set_locale(locale)
        while self._running or not self._activity_queue.empty():
            try:
                # Intenta obtener actividad de la cola (timeout de 1 segundo)
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # Agregar actividad al búfer de la plataforma correspondiente
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # Verificar si la plataforma ha alcanzado el tamaño del lote
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # Liberar el bloqueo antes de enviar
                            self._send_batch_activities(batch, platform)
                            # Intervalo de envío para evitar solicitudes demasiado frecuentes
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f"Excepción en el bucle de trabajo: {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Envía actividades en lotes al grafo Zep (combinadas en un solo texto)
        
        Args:
            activities: Lista de actividades del agente
            platform: Nombre de la plataforma
        """
        if not activities:
            return
        
        # Combina múltiples actividades en un solo texto, separadas por saltos de línea
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)
        
        # Envío con reintentos
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f"Envío exitoso de lote de {len(activities)} actividades de {display_name} al grafo {self.graph_id}")
                logger.debug(f"Vista previa del contenido del lote: {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Envío fallido de lote a Zep (intento {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Envío fallido de lote a Zep, reintentado {self.MAX_RETRIES} veces: {e}")
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """Envía las actividades restantes en la cola y el búfer"""
        # Primero procesa las actividades restantes en la cola, agregándolas al búfer
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # Luego envía las actividades restantes en el búfer de cada plataforma (incluso si son menos de BATCH_SIZE)
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"Envío de {len(buffer)} actividades restantes de la plataforma {display_name}")
                    self._send_batch_activities(buffer, platform)
            # Vacía todos los búferes
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene información estadística"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # Total de actividades agregadas a la cola
            "batches_sent": self._total_sent,            # Número de lotes enviados exitosamente
            "items_sent": self._total_items_sent,        # Número de actividades enviadas exitosamente
            "failed_count": self._failed_count,          # Número de lotes enviados con error
            "skipped_count": self._skipped_count,        # Número de actividades omitidas (DO_NOTHING)
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # Tamaño del búfer por plataforma
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """
    Administra múltiples actualizadores de memoria de grafos Zep para simulaciones
    
    Cada simulación puede tener su propia instancia de actualizador
    """
    
    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """
        Crea un actualizador de memoria de grafo Zep para una simulación
        
        Args:
            simulation_id: ID de la simulación
            graph_id: ID del grafo Zep
            
        Returns:
            ZepGraphMemoryUpdater实例
        """
        with cls._lock:
            # Si ya existe, detiene el anterior
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"Creado actualizador de memoria de grafo: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """Obtiene el actualizador de la simulación"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """Detiene y elimina el actualizador de la simulación"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"Detenido actualizador de memoria de grafo: simulation_id={simulation_id}")
    
    # Bandera para evitar llamadas repetidas a stop_all
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """Detiene todos los actualizadores"""
        # Evita llamadas repetidas
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"Detener actualizador fallido: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("Detenidos todos los actualizadores de memoria de grafo")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Obtiene estadísticas de todos los actualizadores"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }
