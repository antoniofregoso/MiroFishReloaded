"""
Servicio de lectura y filtrado de entidades Zep
Lee nodos del grafo Zep y filtra los que cumplen con los tipos de entidades predefinidos
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_entity_reader')

# 用于泛型返回类型
T = TypeVar('T')


@dataclass
class EntityNode:
    """Estructura de datos del nodo de entidad"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # 相关的边信息
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # 相关的其他节点信息
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """Obtener el tipo de entidad (excluyendo la etiqueta predeterminada Entity)"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Conjunto de entidades filtradas"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Servicio de lectura y filtrado de entidades Zep
    
    Funciones principales:
    1. Lee todos los nodos del grafo Zep
    2. Filtra los nodos que cumplen con los tipos de entidades predefinidos (Labels no son solo Entity)
    3. Obtiene información de aristas y nodos relacionados para cada entidad
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY 未配置")
        
        self.client = Zep(api_key=self.api_key)
    
    def _call_with_retry(
        self, 
        func: Callable[[], T], 
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        Llamada a la API de Zep con mecanismo de reintentos
        
        Args:
            func: Función a ejecutar (lambda o callable sin argumentos)
            operation_name: Nombre de la operación, utilizado para el registro
            max_retries: Número máximo de reintentos (por defecto 3, es decir, máximo 3 intentos)
            initial_delay: Retraso inicial en segundos
            
        Returns:
            Resultado de la llamada a la API
        """
        last_exception = None
        delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} 第 {attempt + 1} 次尝试失败: {str(e)[:100]}, "
                        f"{delay:.1f}秒后重试..."
                    )
                    time.sleep(delay)
                    delay *= 2  # 指数退避
                else:
                    logger.error(f"Zep {operation_name} 在 {max_retries} 次尝试后仍失败: {str(e)}")
        
        raise last_exception
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Obtener todos los nodos del grafo (obtención por páginas)

        Args:
            graph_id: ID del grafo

        Returns:
            Lista de nodos
        """
        logger.info(f"Obteniendo todos los nodos del grafo {graph_id}...")

        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(f"Se han obtenido {len(nodes_data)} nodos en total")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Obtener todas las aristas del grafo (obtención por páginas)

        Args:
            graph_id: ID del grafo

        Returns:
            Lista de aristas
        """
        logger.info(f"Obteniendo todas las aristas del grafo {graph_id}...")

        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(f"Se han obtenido {len(edges_data)} aristas en total")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        Obtener todas las aristas relacionadas con un nodo específico (con mecanismo de reintentos)
        
        Args:
            node_uuid: UUID del nodo
            
        Returns:
            Lista de aristas
        """
        try:
            # Usar el mecanismo de reintentos para llamar a la API de Zep
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"Obtener aristas del nodo (node={node_uuid[:8]}...)"
            )
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"Fallo al obtener las aristas del nodo {node_uuid}: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        Filtrar nodos que cumplen con los tipos de entidades predefinidos
        
        Lógica de filtrado:
        - Si el nodo tiene solo una etiqueta "Entity", significa que no cumple con nuestros tipos de entidades predefinidos, se omite
        - Si el nodo tiene etiquetas además de "Entity" y "Node", significa que cumple con los tipos de entidades predefinidos, se conserva
        
        Args:
            graph_id: ID del grafo
            defined_entity_types: Lista de tipos de entidades predefinidos (opcional, si se proporciona, solo se conservarán estos tipos)
            enrich_with_edges: Si se debe obtener información de aristas relacionadas para cada entidad
            
        Returns:
            FilteredEntities: Conjunto de entidades filtradas
        """
        logger.info(f"Comenzando a filtrar entidades del grafo {graph_id}...")
        
        # Obtener todos los nodos
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # Obtener todas las aristas (para búsqueda de relaciones posterior)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # Construir un mapa de UUID de nodo a datos de nodo
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # Filtrar entidades que cumplen con las condiciones
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # Lógica de filtrado: Labels debe contener etiquetas además de "Entity" y "Node"
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            if not custom_labels:
                # Solo etiquetas predeterminadas, omitir
                continue
            
            # Si se especifican tipos predefinidos, verificar si coinciden
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # Crear objeto de nodo de entidad
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # Obtener aristas y nodos relacionados
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                # Obtener información básica de los nodos relacionados
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(f"Filtrado completado: Total de nodos {total_count}, "
                   f"Entidades que cumplen las condiciones {len(filtered_entities)}, "
                   f"Tipos de entidades: {entity_types_found}")
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        Obtener una entidad individual y su contexto completo (aristas y nodos relacionados, con mecanismo de reintentos)
        
        Args:
            graph_id: ID del grafo
            entity_uuid: UUID de la entidad
            
        Returns:
            EntityNode o None
        """
        try:
            # Usar el mecanismo de reintentos para obtener el nodo
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"Obtener detalles del nodo (uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # Obtener las aristas del nodo
            edges = self.get_node_edges(entity_uuid)
            
            # Obtener todos los nodos para búsqueda de relaciones
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # Procesar aristas y nodos relacionados
            related_edges = []
            related_node_uuids = set()
            
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])
            
            # Obtener información de los nodos relacionados
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })
            
            return EntityNode(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"获取实体 {entity_uuid} 失败: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        Obtener todas las entidades de un tipo específico
        
        Args:
            graph_id: ID del grafo
            entity_type: Tipo de entidad (como "Student", "PublicFigure", etc.)
            enrich_with_edges: Si se debe obtener información de aristas relacionadas
            
        Returns:
            Lista de entidades
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities


