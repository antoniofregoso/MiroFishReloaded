"""
OASIS Agent ProfileGenerador
Convierte las entidades del grafo Zep al formato de Perfil de Agente requerido por la plataforma de simulación OASIS.

Optimizaciones y mejoras:
1. Mejora la información de los nodos mediante la función de búsqueda de Zep.
2. Optimiza la generación de palabras clave para crear perfiles de usuario altamente detallados.
3. Diferencia entre entidades individuales y entidades de grupo abstractas.
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_language_instruction, get_locale, set_locale, t
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile Estructuras de datos"""
    # Campos generales
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # Campos opcionales - estilo Reddit
    karma: int = 1000
    
    # Campos opcionales - estilo Twitter
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # Información adicional del perfil
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    vals2: Optional[str] = None
    ocean: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # Información de la entidad de origen
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Convertir al formato de la plataforma Reddit"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # El campo requerido por la biblioteca OASIS es username (sin guion bajo)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # Agregar información adicional del perfil (si existe)
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.vals2:
            profile["vals2"] = self.vals2
        if self.ocean:
            profile["ocean"] = self.ocean
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """Convertir al formato de la plataforma de Twitter"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # El campo requerido por la biblioteca OASIS es username (sin guion bajo)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # Agregar información adicional del perfil
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.vals2:
            profile["vals2"] = self.vals2
        if self.ocean:
            profile["ocean"] = self.ocean
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a formato de diccionario completo"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "vals2": self.vals2,
            "ocean": self.ocean,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile Generador
    
    Convierte las entidades del grafo Zep al formato de Perfil de Agente requerido por la plataforma de simulación OASIS
    
    Optimizaciones y mejoras:
    1. Llama a la función de búsqueda del grafo Zep para obtener contexto más rico
    2. Genera perfiles de usuario muy detallados (incluyendo información básica, experiencia profesional, rasgos de personalidad, comportamiento en redes sociales, etc.)
    3. Diferencia entre entidades individuales y entidades de grupo abstractas
    """
    
    # Lista de tipos de MBTI
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]

    VALS2_TYPES = [
        "Strivers",
        "Achievers",
        "Experiencers",
        "Makers",
        "Thinkers",
        "Believers",
        "Strugglers",
        "Survivors"
    ]

    OCEAN_TYPES = [
        "Openness",
        "Conscientiousness",
        "Extraversion",
        "Agreeableness",
        "Neuroticism"
    ]
    
    # Lista de países comunes
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # Tipos de entidades individuales (requieren generación de perfiles específicos)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # Tipos de entidades grupales/organizacionales (requieren generación de perfiles representativos)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # Cliente Zep para recuperar contexto rico
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self.graph_id = graph_id
        
        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"Cliente Zep inicializado fallido: {e}")
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        Desde Zep entidad generar OASIS Agent Profile
        
        Args:
            entity: Nodo de entidad Zep
            user_id: ID de usuario (para OASIS)
            use_llm: Si usar LLM para generar perfil detallado
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # Información básica
        name = entity.name
        user_name = self._generate_username(name)
        
        # Construir información de contexto
        context = self._build_entity_context(entity)
        
        if use_llm:
            # Usar LLM para generar perfil detallado
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # Usar reglas para generar perfil básico
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            vals2=profile_data.get("vals2"),
            ocean=profile_data.get("ocean"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """Generar nombre de usuario"""
        # Eliminar caracteres especiales, convertir a minúsculas
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # Agregar sufijo aleatorio para evitar duplicados
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Usar la función de búsqueda híbrida del grafo Zep para obtener información rica relacionada con la entidad
        
        Zep no tiene una interfaz de búsqueda híbrida incorporada, por lo que es necesario buscar edges y nodes por separado y luego combinar los resultados.
        Se utilizan solicitudes paralelas para buscar simultáneamente, mejorando la eficiencia.
        
        Args:
            entity: Nodo de entidad
            
        Returns:
            Diccionario que contiene facts, node_summaries y context
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # Debe tener graph_id para realizar la búsqueda
        if not self.graph_id:
            logger.debug(f"Saltar la recuperación de Zep: graph_id no está configurado")
            return results
        
        comprehensive_query = t('progress.zepSearchQuery', name=entity_name)
        
        def search_edges():
            """Buscar aristas (hechos/relaciones) - con mecanismo de reintento"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep边搜索第 {attempt + 1} 次失败: {str(e)[:80]}, 重试中...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep边搜索在 {max_retries} 次尝试后仍失败: {e}")
            return None
        
        def search_nodes():
            """Buscar nodos (resúmenes de entidades) - con mecanismo de reintento"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep节点搜索第 {attempt + 1} 次失败: {str(e)[:80]}, 重试中...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep节点搜索在 {max_retries} 次尝试后仍失败: {e}")
            return None
        
        try:
            # Ejecutar búsquedas de edges y nodes en paralelo
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)
                
                # Obtener resultados
                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)
            
            # Procesar resultados de búsqueda de edges
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            # Procesar resultados de búsqueda de nodos
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"相关实体: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # Construir contexto integral
            context_parts = []
            if results["facts"]:
                context_parts.append("Información de hechos:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Entidades relacionadas:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"Zep检索 híbrida completada: {entity_name}, obtenido {len(results['facts'])} hechos, {len(results['node_summaries'])} nodos relacionados")
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"Zep检索 tiempo agotado ({entity_name})")
        except Exception as e:
            logger.warning(f"Zep检索 fallida ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Construir información de contexto completa de la entidad
        
        Incluye:
        1. Información de aristas de la entidad (hechos)
        2. Información detallada de nodos relacionados
        3. Información rica recuperada mediante búsqueda híbrida de Zep
        """
        context_parts = []
        
        # 1. Agregar información de atributos de la entidad
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### 实体属性\n" + "\n".join(attrs))
        
        # 2. Agregar información de aristas (hechos/relaciones)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # Sin límite de cantidad
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (Entidad relacionada)")
                    else:
                        relationships.append(f"- (Entidad relacionada) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### Hechos y relaciones relacionados\n" + "\n".join(relationships))
        
        # 3. Agregar información detallada de nodos relacionados
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # Sin límite de cantidad
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # Filtrar etiquetas predeterminadas
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### Información de entidades relacionadas\n" + "\n".join(related_info))
        
        # 4. Usar búsqueda híbrida de Zep para obtener información más rica
        zep_results = self._search_zep_for_entity(entity)
        
        if zep_results.get("facts"):
            # Deduplicación: excluir hechos ya existentes
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Información de hechos recuperada por Zep\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if zep_results.get("node_summaries"):
            context_parts.append("### Información de nodos relacionados recuperada por Zep\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """¿Es una entidad de tipo individual?"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """¿Es una entidad de tipo grupo/organización?"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        Usar LLM para generar un perfil muy detallado
        
        Diferenciar según el tipo de entidad:
        - Entidades individuales: generar configuración de personaje específica
        - Entidades grupales/organizacionales: generar configuración de cuenta representativa
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # Intentar generar varias veces hasta tener éxito o alcanzar el número máximo de reintentos
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Reducir la temperatura en cada reintento
                    # No establecer max_tokens para permitir que el LLM se exprese libremente
                )
                
                content = response.choices[0].message.content
                
                # Verificar si está truncado (finish_reason no es 'stop')
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"La salida del LLM está truncada (intento {attempt+1}), intentando reparar...")
                    content = self._fix_truncated_json(content)
                
                # Intentar analizar JSON
                try:
                    result = json.loads(content)
                    
                    # Verificar campos obligatorios
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name}是一个{entity_type}。"
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"Fallo al analizar JSON (intento {attempt+1}): {str(je)[:80]}")
                    
                    # Intentar reparar JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"Fallo al llamar al LLM (intento {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # Exponencial backoff
        
        logger.warning(f"Fallo al generar perfil con LLM ({max_attempts} intentos): {last_error}, usando generación basada en reglas")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Reparar JSON truncado (salida truncada por límite de max_tokens)"""
        import re
        
        # Si el JSON está truncado, intenta cerrarlo
        content = content.strip()
        
        # Calcular paréntesis no cerrados
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Verificar si hay cadenas no cerradas
        # Verificación simple: si el último carácter después de las comillas no es una coma o un corchete de cierre, puede estar truncado
        if content and content[-1] not in '",}]':
            # Intentar cerrar la cadena
            content += '"'
        
        # Cerrar corchetes
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Intento de reparar JSON dañado"""
        import re
        
        # 1. Primero intenta reparar el caso truncado
        content = self._fix_truncated_json(content)
        
        # 2. Intentar extraer la parte JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. Manejar el problema de los saltos de línea en las cadenas
            # Encuentra todos los valores de cadena y reemplaza los caracteres de nueva línea.
            def fix_string_newlines(match):
                s = match.group(0)
                # Reemplaza los caracteres de nueva línea reales dentro de la cadena por espacios
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Reemplaza espacios en blanco excesivos
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # Coincide con los valores de cadena JSON
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. Intentar analizar
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. Si todavía falla, intenta una reparación más agresiva
                try:
                    # Elimina todos los caracteres de control
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Reemplaza todos los espacios en blanco consecutivos
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. Intenta extraer información parcial del contenido
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # Puede estar truncado
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name}是一个{entity_type}。")
        
        # Si se extrajo contenido significativo, márcalo como reparado
        if bio_match or persona_match:
            logger.info(f"Se extrajo información parcial del JSON dañado")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Fallo total, devuelve la estructura base
        logger.warning(f"Fallo al reparar JSON, devuelve la estructura base")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name}是一个{entity_type}。"
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """Obtener prompt del sistema"""
        base_prompt = "Eres un experto en generación de perfiles de usuarios de redes sociales. Genera perfiles detallados y realistas para la simulación de opinión pública, restaurando al máximo la situación real existente. Debes devolver un formato JSON válido, y todos los valores de cadena no deben contener saltos de línea sin escapar."
        return f"{base_prompt}\n\n{get_language_instruction()}"
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Construir prompt detallado de perfil de usuario para entidad individual"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "无额外上下文"
        
        return f"""Para la entidad, genera un perfil detallado de usuario de red social, restaurando al máximo la situación real existente.

Nombre de la entidad: {entity_name}
Tipo de entidad: {entity_type}
Resumen de la entidad: {entity_summary}
Atributos de la entidad: {attrs_str}

Información de contexto:
{context_str}

Por favor, genera JSON que contenga los siguientes campos:

1. bio: Breve descripción de la red social, 200 caracteres
2. persona: Descripción detallada del perfil (2000 caracteres de texto puro), debe incluir:
   - Información básica (edad, ocupación, educación, ubicación)
   - Antecedentes del personaje (experiencias importantes, relación con el evento, relaciones sociales)
   - Características de personalidad (tipo MBTI, personalidad central, estilo de expresión emocional)
   - Comportamiento en redes sociales (frecuencia de publicación, preferencias de contenido, estilo de interacción, características lingüísticas)
   - Puntos de vista (actitud hacia el tema, contenido que puede ser provocado/emocionado)
   - Características únicas (frases favoritas, experiencias especiales, pasatiempos)
   - Recuerdos personales (parte importante de la personalidad, debe presentar la relación de este individuo con el evento y sus acciones y reacciones existentes en el evento)
3. age: Edad (debe ser un número entero)
4. gender: Género, debe ser en inglés: "male" o "female"
5. mbti: Tipo MBTI (como INTJ, ENFP, etc.)
6. vals2: Valores y estilos de vida (como Strivers, Achievers, etc.)
7. ocean: Personalidad (como Openness, Conscientiousness, etc.)
8. country: País (usar chino, como "中国")
9. profession: Profesión
10. interested_topics: Array de temas de interés

Importante:
- Todos los valores de campo deben ser cadenas o números, no uses caracteres de nueva línea
- persona debe ser un párrafo de texto continuo
- {get_language_instruction()} (el campo gender debe estar en inglés male/female)
- El contenido debe ser consistente con la información de la entidad
- age debe ser un entero válido, gender debe ser "male" o "female"
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Construir prompt detallado de perfil de usuario para entidad grupal/organizacional"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "无额外上下文"
        
        return f"""Para la entidad grupal/organizacional, genera un perfil detallado de cuenta de red social, restaurando al máximo la situación real existente.

Nombre de la entidad: {entity_name}
Tipo de entidad: {entity_type}
Resumen de la entidad: {entity_summary}
Atributos de la entidad: {attrs_str}

Información de contexto:
{context_str}

Por favor, genera JSON que contenga los siguientes campos:

1. bio: Breve descripción de la cuenta oficial, 200 caracteres, profesional y apropiado
2. persona: Descripción detallada del perfil de la cuenta (2000 caracteres de texto puro), debe incluir:
   - Información básica de la organización (nombre oficial, naturaleza de la organización, antecedentes de establecimiento, funciones principales)
   - Posicionamiento de la cuenta (tipo de cuenta, público objetivo, funciones principales)
   - Estilo de expresión (características lingüísticas, expresiones comunes, temas prohibidos)
   - Características del contenido publicado (tipo de contenido, frecuencia de publicación, período de actividad)
   - Actitud de posición (posición oficial sobre temas centrales, método de manejo frente a controversias)
   - Instrucciones especiales (imagen del grupo representado, hábitos operativos)
   - Recuerdos institucionales (parte importante de la personalidad institucional, debe presentar la relación de esta institución con el evento y sus acciones y reacciones existentes en el evento)
3. age:El valor fijo es 30 (la antigüedad virtual de la cuenta institucional).）
4. gender: 固定填"other"（机构账号使用other表示非个人）
5. mbti: Tipo MBTI, utilizado para describir el estilo de la cuenta, como ISTJ representa conservador y riguroso
6. vals2: Valores y estilos de vida
7. ocean: Personalidad (como Openness, Conscientiousness, etc.)
8. country: País (usar chino, como "中国")
9. profession: Descripción de la función institucional
10. interested_topics: Array de temas de interés

Importante:
- Todos los valores de campo deben ser cadenas o números, no uses caracteres de nueva línea
- persona debe ser un párrafo de texto continuo
- {get_language_instruction()} (el campo gender debe estar en inglés "other")
- age debe ser el entero 30, gender debe ser la cadena "other"
- Las declaraciones de la cuenta institucional deben ser consistentes con su posicionamiento"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generar perfil básico basado en reglas"""
        
        # Generar diferentes perfiles según el tipo de entidad
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "vals2": random.choice(self.VALS2_TYPES),
                "ocean": random.choice(self.OCEAN_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "vals2": random.choice(self.VALS2_TYPES),
                "ocean": random.choice(self.OCEAN_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,  # Antigüedad virtual de la cuenta institucional
                "gender": "other",  # Las cuentas institucionales usan other
                "mbti": "ISTJ",  # Estilo de cuenta: riguroso y conservador
                "vals2": random.choice(self.VALS2_TYPES),
                "ocean": random.choice(self.OCEAN_TYPES),
                "country": "中国",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,  # Antigüedad virtual de la cuenta institucional
                "gender": "other",  # Las cuentas institucionales usan other
                "mbti": "ISTJ",  # Estilo de cuenta: riguroso y conservador
                "vals2": random.choice(self.VALS2_TYPES),
                "ocean": random.choice(self.OCEAN_TYPES),
                "country": "中国",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # Persona predeterminada
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "vals2": random.choice(self.VALS2_TYPES),
                "ocean": random.choice(self.OCEAN_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """Establecer ID del grafo para la recuperación de Zep"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        Generar perfiles de agente en lote a partir de entidades (soporta generación paralela)
        
        Args:
            entities: Lista de entidades
            use_llm: Si usar LLM para generar perfiles detallados
            progress_callback: Función de devolución de llamada de progreso (current, total, message)
            graph_id: ID del grafo, utilizado para la recuperación de Zep y obtener contexto más rico
            parallel_count: Número de generación paralela, por defecto 5
            realtime_output_path: Ruta del archivo de escritura en tiempo real (si se proporciona, se escribe una vez cada vez que se genera uno)
            output_platform: Formato de plataforma de salida ("reddit" o "twitter")
            
        Returns:
            Lista de Agent Profile
        """
        import concurrent.futures
        from threading import Lock
        
        # Establecer graph_id para la recuperación de Zep
        if graph_id:
            self.graph_id = graph_id
        
        total = len(entities)
        profiles = [None] * total  # Lista preasignada para mantener el orden
        completed_count = [0]  # Usar lista para permitir modificación en el closure
        lock = Lock()
        
        # Función auxiliar para guardar perfiles en tiempo real
        def save_profiles_realtime():
            """Guardar perfiles ya generados en el archivo en tiempo real"""
            if not realtime_output_path:
                return
            
            with lock:
                # Filtrar los perfiles ya generados
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return
                
                try:
                    if output_platform == "reddit":
                        # Reddit JSON 格式
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV 格式
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"实时保存 profiles 失败: {e}")
        
        # Capture locale before spawning thread pool workers
        current_locale = get_locale()

        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Función de trabajo para generar un solo perfil"""
            set_locale(current_locale)
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )
                
                # Salida en tiempo real del perfil generado a la consola y al registro
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(f"Error al generar el perfil para la entidad {entity.name}: {str(e)}")
                # Crear un perfil básico
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"Comenzar a generar {total} perfiles de agente en paralelo (número de hilos: {parallel_count})...")
        print(f"\n{'='*60}")
        print(f"Comenzar a generar perfiles de agente - Total {total} entidades, número de hilos: {parallel_count}")
        print(f"{'='*60}\n")
        
        # Usar el grupo de hilos para ejecutar en paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # Enviar todas las tareas
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }
            
            # Recolectar resultados
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # 实时写入文件
                    save_profiles_realtime()
                    
                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"Completado {current}/{total}: {entity.name} ({entity_type})"
                        )
                    
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} usando perfil de respaldo: {error}")
                    else:
                        logger.info(f"[{current}/{total}] Perfil generado exitosamente: {entity.name} ({entity_type})")
                        
                except Exception as e:
                    logger.error(f"Error al procesar la entidad {entity.name}: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # 实时写入文件（即使是备用人设）
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(f"¡Generación de perfiles completada! Total {len([p for p in profiles if p])} agentes generados")
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Salida en tiempo real del perfil generado a la consola (contenido completo, sin truncar)"""
        separator = "-" * 70
        
        # Construir contenido de salida completo (sin truncar)
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else '无'
        
        output_lines = [
            f"\n{separator}",
            t('progress.profileGenerated', name=entity_name, type=entity_type),
            f"{separator}",
            f"Nombre de usuario: {profile.user_name}",
            f"",
            f"【Introducción】",
            f"{profile.bio}",
            f"",
            f"【Perfil detallado】",
            f"{profile.persona}",
            f"",
            f"【Atributos básicos】",
            f"Edad: {profile.age} | Género: {profile.gender} | MBTI: {profile.mbti} | VALS2: {profile.vals2} | OCEAN: {profile.ocean}",
            f"Profesión: {profile.profession} | País: {profile.country}",
            f"Temas de interés: {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # Solo salida a la consola (evitar duplicación, el logger ya no emite contenido completo)
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        Guardar perfiles en el archivo (seleccionar el formato correcto según la plataforma)
        
        Requisitos de formato de la plataforma OASIS:
        - Twitter: formato CSV
        - Reddit: formato JSON
        
        Args:
            profiles: Lista de perfiles
            file_path: Ruta del archivo
            platform: Tipo de plataforma ("reddit" o "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Guardar perfiles de Twitter en formato CSV (cumple con los requisitos oficiales de OASIS)
        
        Campos CSV requeridos por OASIS Twitter:
        - user_id: ID de usuario (comenzando desde 0 según el orden CSV)
        - name: Nombre real del usuario
        - username: Nombre de usuario en el sistema
        - user_char: Descripción detallada del perfil (inyectada en el prompt del sistema LLM para guiar el comportamiento del agente)
        - description: Breve descripción pública (visible en la página de perfil)
        
        Diferencia entre user_char y description:
        - user_char: Uso interno, prompt del sistema LLM, determina cómo piensa y actúa el agente
        - description: Visualización externa, visible para otros usuarios
        """
        import csv
        
        # Asegúrese de que la extensión del archivo sea .csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Escribir encabezados requeridos por OASIS
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)
            
            # Escribir filas de datos
            for idx, profile in enumerate(profiles):
                # user_char:Diseño completo del personaje（bio + persona），Para las indicaciones del sistema LLM
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Procesar saltos de línea (reemplazar con espacios en CSV)
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')
                
                # description: Breve descripción, para visualización externa
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')
                
                row = [
                    idx,                    # user_id: ID de secuencia que comienza en 0
                    profile.name,           # name: Nombre real
                    profile.user_name,      # username: Nombre de usuario
                    user_char,              # user_char: Diseño completo del personaje（uso interno LLM）
                    description             # description: Breve descripción（visualización externa）
                ]
                writer.writerow(row)
        
        logger.info(f"Se han guardado {len(profiles)} perfiles de Twitter en {file_path} (formato CSV de OASIS)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        Estandarizar el campo gender al formato inglés requerido por OASIS
        
        OASIS requiere: male, female, other
        """
        if not gender:
            return "other"
        
        gender_lower = gender.lower().strip()
        
        # Mapeo de chino a inglés
        gender_map = {
            "男": "male",
            "女": "female",
            "机构": "other",
            "其他": "other",
            # Inglés existente
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Guardar perfiles de Reddit en formato JSON
        
        Utiliza el mismo formato que to_reddit_format() para asegurar que OASIS pueda leerlo correctamente.
        ¡Debe incluir el campo user_id, que es clave para que OASIS agent_graph.get_agent() coincida!
        
        Campos requeridos:
        - user_id: ID de usuario (entero, utilizado para coincidir con poster_agent_id en initial_posts)
        - username: Nombre de usuario
        - name: Nombre de visualización
        - bio: Biografía
        - persona: Diseño detallado del personaje
        - age: Edad (entero)
        - gender: "male", "female", o "other"
        - mbti: Tipo MBTI
        - vals2: Valores
        - ocean: OCEAN
        - country: País
        """
        data = []
        for idx, profile in enumerate(profiles):
            # Utiliza el mismo formato que to_reddit_format()
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # 关键：必须包含 user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} participa en debates sociales.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # Campos requeridos por OASIS - asegurar que todos tengan valores predeterminados
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "vals2": profile.vals2 if profile.vals2 else "Achievers",
                "ocean": profile.ocean if profile.ocean else "Openness",
                "country": profile.country if profile.country else "México",
            }
            
            # Campos opcionales
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Se han guardado {len(profiles)} perfiles de Reddit en {file_path} (formato JSON con campo user_id)")
    
    # Conservar el nombre del método antiguo como alias para mantener la compatibilidad con versiones anteriores
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Obsoleto] Por favor, utiliza el método save_profiles()"""
        logger.warning("save_profiles_to_json está obsoleto, por favor utiliza save_profiles")
        self.save_profiles(profiles, file_path, platform)

