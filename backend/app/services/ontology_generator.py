"""
Servicio de generación de ontología
Interfaz 1: Analizar el contenido del documento y generar definiciones de tipos de entidades y relaciones adecuadas para la simulación social
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient
from ..utils.locale import get_language_instruction

logger = logging.getLogger(__name__)


def _to_pascal_case(name: str) -> str:
    """Convierte cualquier formato de nombre a PascalCase (ej. 'works_for' -> 'WorksFor', 'person' -> 'Person')"""
    # Divide por caracteres no alfanuméricos
    parts = re.split(r'[^a-zA-Z0-9]+', name)
    # Luego divide por límites de camelCase (ej. 'camelCase' -> ['camel', 'Case'])
    words = []
    for part in parts:
        words.extend(re.sub(r'([a-z])([A-Z])', r'\1_\2', part).split('_'))
    # Cada palabra con la primera letra en mayúscula, filtra las cadenas vacías
    result = ''.join(word.capitalize() for word in words if word)
    return result if result else 'Unknown'


# Mensajes del sistema generados por la ontología
ONTOLOGY_SYSTEM_PROMPT = """Eres un experto profesional en diseño de ontologías de grafos de conocimiento. Tu tarea es analizar el contenido del documento proporcionado y los requisitos de simulación, y diseñar tipos de entidades y relaciones adecuados para la **simulación de opinión pública en redes sociales**.

**Importante: Debes generar datos en formato JSON válido y no debes generar ningún otro contenido.**

## Contexto de la tarea principal

Estamos construyendo un **sistema de simulación de opinión pública en redes sociales**. En este sistema:
- Cada entidad es una "cuenta" o "sujeto" que puede hablar, interactuar y difundir información en las redes sociales
- Las entidades se influirán mutuamente, reenviarán, comentarán y responderán entre sí
- Necesitamos simular las reacciones de todas las partes y las rutas de propagación de la información en los eventos de opinión pública

Por lo tanto, **las entidades deben ser sujetos reales que existen en el mundo real y pueden hablar e interactuar en las redes sociales**:

**Pueden ser**：
- Individuos específicos (figuras públicas, partes involucradas, líderes de opinión, académicos, personas comunes)
- Empresas y corporaciones (incluidas sus cuentas oficiales)
- Organizaciones (universidades, asociaciones, ONG, sindicatos, etc.)
- Agencias gubernamentales y organismos reguladores
- Instituciones mediáticas (periódicos, estaciones de televisión, medios independientes, sitios web)
- Plataformas de redes sociales en sí mismas
- Representantes de grupos específicos (como asociaciones de exalumnos, grupos de fans, grupos de defensa, etc.)

**No pueden ser**：
- Conceptos abstractos (como "opinión pública", "emoción", "tendencia")
- Temas/asuntos (como "integridad académica", "reforma educativa")
- Puntos de vista/actitudes (como "partidarios", "opositores")

## Formato de salida

Por favor, genera datos en formato JSON con la siguiente estructura:

```json
{
    "entity_types": [
        {
            "name": "Nombre del tipo de entidad (PascalCase en inglés)",
            "description": "Descripción breve (en inglés, no más de 100 caracteres)",
            "attributes": [
                {
                    "name": "Nombre del atributo (snake_case en inglés)",
                    "type": "text",
                    "description": "Descripción del atributo"
                }
            ],
            "examples": ["Ejemplo de entidad 1", "Ejemplo de entidad 2"]
        }
    ],
    "edge_types": [
        {
            "name": "Nombre del tipo de relación (UPPER_SNAKE_CASE en inglés)",
            "description": "Descripción breve (en inglés, no más de 100 caracteres)",
            "source_targets": [
                {"source": "Tipo de entidad de origen", "target": "Tipo de entidad de destino"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Breve análisis del contenido del texto"
}
```

## Guía de diseño (¡extremadamente importante!)

### 1. Diseño de tipos de entidades - ¡debe seguirse estrictamente!

**Requisito de cantidad: debe haber exactamente 10 tipos de entidades**

**Requisito de estructura jerárquica (debe incluir tipos específicos y tipos de cobertura)**:

Tus 10 tipos de entidades deben incluir la siguiente jerarquía:

A. **Tipos de cobertura (deben incluirse, colocados en los últimos 2 de la lista)**:
   - `Person`: Tipo de cobertura para cualquier individuo natural. Cuando una persona no pertenece a otro tipo de persona más específico, se clasifica en esta categoría.
   - `Organization`: Tipo de cobertura para cualquier organización. Cuando una organización no pertenece a otro tipo de organización más específico, se clasifica en esta categoría.

B. **Tipos específicos (8个，Diseño basado en el contenido del texto.）**：
   - Diseñar tipos de letra más específicos para los caracteres principales que aparecen en el texto.
   - Por ejemplo: si el texto involucra un evento académico, puede haber `Student`, `Professor`, `University`
   - Por ejemplo: si el texto involucra un evento comercial, puede haber `Company`, `CEO`, `Employee`

**¿Por qué se necesitan tipos de cobertura?**：
- El texto contendrá varios personajes, como "profesor de escuela primaria y secundaria", "persona promedio", "algún internauta"
- Si no hay un tipo de coincidencia especial, deben clasificarse en `Person`
- De manera similar, las organizaciones pequeñas y los grupos temporales deben clasificarse en `Organization`

**Principios de diseño de tipos específicos**：
- Identificar los tipos de caracteres que aparecen con frecuencia o son clave en el texto
- Cada tipo específico debe tener límites claros para evitar superposiciones
- description debe explicar claramente la diferencia entre este tipo y el tipo de cobertura

### 2. Diseño de tipos de relaciones

- Cantidad: 6-10个
- Las relaciones deben reflejar las conexiones reales en la interacción de las redes sociales
- Asegurar que los source_targets de las relaciones cubran los tipos de entidades definidos

### 3. Diseño de atributos

- Cada tipo de entidad 1-3 atributos clave
- **Nota**: Los nombres de los atributos no pueden usar `name`, `uuid`, `group_id`, `created_at`, `summary` (estos son palabras reservadas del sistema)
- Se recomienda usar: `full_name`, `title`, `role`, `position`, `location`, `description`等

## Ejemplos de tipos de entidades

**Tipos de personas (específicos)**：
- Student: Estudiante
- Professor: Profesor/Académico
- Journalist: Periodista
- Celebrity: Estrella/Influencer
- Executive: Ejecutivo
- Official: Funcionario gubernamental
- Lawyer: Abogado
- Doctor: Doctor

**Tipos de personas (cobertura)**：
- Person: Cualquier individuo natural (se usa cuando no pertenece a otro tipo de persona más específico)

**Tipos de organizaciones (específicos)**：
- University: Universidad
- Company: Empresa
- GovernmentAgency: Agencia gubernamental
- MediaOutlet: Medio de comunicación
- Hospital: Hospital
- School: Escuela primaria y secundaria
- NGO: ONG

**Tipos de organizaciones (cobertura)**：
- Organization: Cualquier organización (se usa cuando no pertenece a otro tipo de organización más específico)

## Referencia de tipos de relaciones

- WORKS_FOR: Trabaja en
- STUDIES_AT: Estudia en
- AFFILIATED_WITH: Afiliado a
- REPRESENTS: Representa
- REGULATES: Regula
- REPORTS_ON: Reporta sobre
- COMMENTS_ON: Comenta sobre
- RESPONDS_TO: Responde a
- SUPPORTS: Apoya
- OPPOSES: Se opone a
- COLLABORATES_WITH: Colabora con
- COMPETES_WITH: Compite con
"""


class OntologyGenerator:
    """
    Generador de ontología
    Analiza el contenido del texto y genera definiciones de tipos de entidades y relaciones
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generar definición de ontología
        
        Args:
            document_texts: Lista de textos de documentos
            simulation_requirement: Descripción del requisito de simulación
            additional_context: Contexto adicional
            
        Returns:
            Definición de ontología (entity_types, edge_types, etc.)
        """
        # Construir mensaje de usuario
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        lang_instruction = get_language_instruction()
        system_prompt = f"{ONTOLOGY_SYSTEM_PROMPT}\n\n{lang_instruction}\nIMPORTANT: Entity type names MUST be in English PascalCase (e.g., 'PersonEntity', 'MediaOrganization'). Relationship type names MUST be in English UPPER_SNAKE_CASE (e.g., 'WORKS_FOR'). Attribute names MUST be in English snake_case. Only description fields and analysis_summary should use the specified language above."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Llamar al LLM
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )
        
        # Validación y post-procesamiento
        result = self._validate_and_process(result)
        
        return result
    
    # Longitud máxima de texto para el LLM (50,000 caracteres)
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Construir mensaje de usuario"""
        
        # Combinar textos
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)
        
        # Si el texto excede 50,000 caracteres, truncar (solo afecta el contenido enviado al LLM, no la construcción del grafo)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(El texto original contiene {original_length} caracteres, se han truncado los primeros {self.MAX_TEXT_LENGTH_FOR_LLM} caracteres para el análisis de la ontología)...
        
        message = f"""## Requisito de simulación

{simulation_requirement}

## Contenido del documento

{combined_text}
"""
        
        if additional_context:
            message += f"""
## Contexto adicional

{additional_context}
"""
        
        message += """
Por favor, según el contenido anterior, diseña tipos de entidades y tipos de relaciones adecuados para la simulación de opinión pública.

**Reglas que deben cumplirse**：
1. Debe producir exactamente 10 tipos de entidades
2. Los últimos 2 deben ser tipos de cobertura: Person (cobertura de individuos) y Organization (cobertura de organizaciones)
3. Los primeros 8 son tipos específicos diseñados según el contenido del texto
4. Todos los tipos de entidades deben ser sujetos reales que puedan emitir voces en el mundo real, no conceptos abstractos
5. Los nombres de los atributos no pueden usar palabras reservadas como name, uuid, group_id, etc., use full_name, org_name, etc. en su lugar
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validar y post-procesar resultado"""
        
        # Asegurar que los campos necesarios existan
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # Validar tipos de entidades
        # Registrar el mapeo de nombres originales a PascalCase para corregir referencias source_targets en edges posteriores
        entity_name_map = {}
        for entity in result["entity_types"]:
            # Forzar la conversión del nombre de la entidad a PascalCase (requerido por la API de Zep)
            if "name" in entity:
                original_name = entity["name"]
                entity["name"] = _to_pascal_case(original_name)
                if entity["name"] != original_name:
                    logger.warning(f"Entity type name '{original_name}' auto-converted to '{entity['name']}'")
                entity_name_map[original_name] = entity["name"]
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # Asegurar que description no exceda 100 caracteres
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."
        
        # Validar tipos de relaciones
        for edge in result["edge_types"]:
            # 强制将 edge name 转为 SCREAMING_SNAKE_CASE（Zep API 要求）
            if "name" in edge:
                original_name = edge["name"]
                edge["name"] = original_name.upper()
                if edge["name"] != original_name:
                    logger.warning(f"Edge type name '{original_name}' auto-converted to '{edge['name']}'")
            # Corregir las referencias de nombres de entidades en source_targets para que coincidan con PascalCase
            for st in edge.get("source_targets", []):
                if st.get("source") in entity_name_map:
                    st["source"] = entity_name_map[st["source"]]
                if st.get("target") in entity_name_map:
                    st["target"] = entity_name_map[st["target"]]
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Restricción de la API de Zep: máximo 10 tipos de entidades personalizados, máximo 10 tipos de relaciones personalizados
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10

        # Eliminar duplicados: eliminar duplicados por nombre, conservar la primera aparición
        seen_names = set()
        deduped = []
        for entity in result["entity_types"]:
            name = entity.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                deduped.append(entity)
            elif name in seen_names:
                logger.warning(f"Duplicate entity type '{name}' removed during validation")
        result["entity_types"] = deduped

        # Definición de tipo cúspide
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # Verificar si ya existen tipos de cobertura
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # Tipos de cobertura que necesitan ser agregados
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # Si la adición excede 10, se deben eliminar algunos tipos existentes
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # Calcular cuántos eliminar
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # Eliminar desde el final (conservar los tipos específicos más importantes al principio)
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # Agregar tipos de cobertura
            result["entity_types"].extend(fallbacks_to_add)
        
        # Asegurar finalmente que no exceda el límite (programación defensiva)
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        Convertir la definición de ontología a código Python (similar a ontology.py)
        
        Args:
            ontology: Definición de ontología
            
        Returns:
            Código Python en formato string
        """
        code_lines = [
            '"""',
            'Definiciones de tipos de entidades personalizados',
            'Generado automáticamente por MiroFish para simulación de opinión pública',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== Definiciones de tipos de entidades ==============',
            '',
        ]
        
        # Generar tipos de entidades
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== Definiciones de tipos de relaciones ==============')
        code_lines.append('')
        
        # Generar tipos de relaciones
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # Convertir a nombre de clase PascalCase
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # Generar diccionario de tipos
        code_lines.append('# ============== Configuración de tipos ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # Generar mapeo source_targets de relaciones
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)

