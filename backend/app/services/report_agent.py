"""
Servicio de Agente de Reportes
Utiliza LangChain + Zep para generar informes de simulación con patrón ReACT

Funciones:
1. Genera informes basados en los requisitos de la simulación y la información del grafo Zep
2. Primero planifica la estructura del directorio y luego genera sección por sección
3. Cada sección utiliza el patrón ReACT de múltiples rondas de pensamiento y reflexión
4. Soporta el diálogo con el usuario, invocando herramientas de recuperación de forma autónoma durante la conversación
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..utils.locale import get_language_instruction, t
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Registrador de logs detallados del Agente de Reportes
    
    Genera un archivo agent_log.jsonl en la carpeta del informe, registrando cada acción detallada.
    Cada línea es un objeto JSON completo que incluye marca de tiempo, tipo de acción, contenido detallado, etc.
    """
    
    def __init__(self, report_id: str):
        """
        Inicializar el registrador de logs
        
        Args:
            report_id: ID del informe, utilizado para determinar la ruta del archivo de log
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Asegurar que el directorio del archivo de log exista"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Obtener el tiempo transcurrido desde el inicio (segundos)"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Registrar una entrada de log
        
        Args:
            action: Tipo de acción, como 'start', 'tool_call', 'llm_response', 'section_complete', etc.
            stage: Etapa actual, como 'planning', 'generating', 'completed'
            details: Diccionario de contenido detallado, sin truncar
            section_title: Título de la sección actual (opcional)
            section_index: Índice de la sección actual (opcional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # Append al archivo JSONL
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Registrar el inicio de la generación del informe"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": t('report.taskStarted')
            }
        )
    
    def log_planning_start(self):
        """Registrar el inicio de la planificación del esquema"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": t('report.planningStart')}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Registrar la información de contexto obtenida durante la planificación"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": t('report.fetchSimContext'),
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Registrar la finalización de la planificación del esquema"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": t('report.planningComplete'),
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Registrar el inicio de la generación de la sección"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": t('report.sectionStart', title=section_title)}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Registrar el pensamiento ReACT"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": t('report.reactThought', iteration=iteration)
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Registrar la llamada a la herramienta"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": t('report.toolCall', toolName=tool_name)
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Registrar el resultado de la llamada a la herramienta (contenido completo, sin truncar)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # 完整结果，不截断
                "result_length": len(result),
                "message": t('report.toolResult', toolName=tool_name)
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Registrar la respuesta del LLM (contenido completo, sin truncar)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # 完整响应，不截断
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": t('report.llmResponse', hasToolCalls=has_tool_calls, hasFinalAnswer=has_final_answer)
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Registrar el contenido de la sección (solo registra el contenido, no representa la finalización de toda la sección)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # 完整内容，不截断
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": t('report.sectionContentDone', title=section_title)
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Registrar la finalización de la generación de la sección

        El frontend debe escuchar este log para determinar si una sección está realmente completa y obtener el contenido completo
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": t('report.sectionComplete', title=section_title)
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Registrar la finalización del informe"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": t('report.reportComplete')
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Registrar error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": t('report.errorOccurred', error=error_message)
            }
        )


class ReportConsoleLogger:
    """
    Registrador de logs de consola del Agente de Reportes
    
    Escribe logs estilo consola (INFO, WARNING, etc.) en un archivo console_log.txt en la carpeta del informe.
    Estos logs son diferentes de agent_log.jsonl y son salida de consola en formato de texto plano.
    """
    
    def __init__(self, report_id: str):
        """
        Inicializar el registrador de logs de consola
        
        Args:
            report_id: ID del informe, utilizado para determinar la ruta del archivo de log
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Asegurar que el directorio del archivo de log exista"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Configurar el manejador de archivos para escribir logs en el archivo"""
        import logging
        
        # Crear manejador de archivos
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Usar el mismo formato conciso que la consola
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Agregar al logger relacionado con report_agent
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # 避免重复添加
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Cierre el procesador de archivos y elimínelo del registrador."""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Asegurar el cierre del procesador de archivos al salir"""
        self.close()


class ReportStatus(str, Enum):
    """Estado del informe"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Sección del informe"""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """Convertir a formato Markdown"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Esquema del informe"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Convertir a formato Markdown"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Informe completo"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Constantes de plantilla de prompt
# ═══════════════════════════════════════════════════════════════

# ── Descripción de la herramienta ──

TOOL_DESC_INSIGHT_FORGE = """\
【Búsqueda de información profunda - Herramienta de búsqueda potente】
Esta es nuestra potente función de búsqueda, especialmente diseñada para análisis en profundidad. Hará lo siguiente:
1. Desglosa automáticamente tu pregunta en múltiples subpreguntas
2. Busca información en el gráfico de simulación desde múltiples dimensiones
3. Integra los resultados de la búsqueda semántica, el análisis de entidades y el seguimiento de la cadena de relaciones
4. Devuelve el contenido de búsqueda más completo y profundo

【Escenarios de uso】
- Necesitas analizar en profundidad un tema específico
- Necesitas comprender los múltiples aspectos de un evento
- Necesitas obtener materiales ricos para respaldar los capítulos del informe

【Contenido devuelto】
- Texto original de hechos relevantes (se puede citar directamente)
- Perspicacia de entidades centrales
- Análisis de la cadena de relaciones"""

TOOL_DESC_PANORAMA_SEARCH = """\
【Búsqueda de amplitud - Obtener vista panorámica】
Esta herramienta se utiliza para obtener la vista panorámica completa de los resultados de la simulación, especialmente adecuada para comprender el proceso de evolución del evento. Hará lo siguiente:
1. Obtiene todos los nodos y relaciones relevantes
2. Diferencia los hechos actualmente válidos de los hechos históricos/expirados
3. Te ayuda a comprender cómo ha evolucionado la opinión pública

【Escenarios de uso】
- Necesitas comprender la línea de tiempo completa de desarrollo del evento
- Necesitas comparar los cambios de opinión pública en diferentes etapas
- Necesitas obtener información completa sobre entidades y relaciones

【Contenido devuelto】
- Hechos actualmente válidos (resultados más recientes de la simulación)
- Hechos históricos/expirados (registro de evolución)
- Todas las entidades involucradas"""

TOOL_DESC_QUICK_SEARCH = """\
【Búsqueda simple - Recuperación rápida】
Herramienta de recuperación rápida ligera, adecuada para consultas de información simples y directas.

【Escenarios de uso】
- Necesitas encontrar rápidamente información específica
- Necesitas verificar un hecho
- Recuperación de información simple

【Contenido devuelto】
- Lista de hechos más relevantes para la consulta"""

TOOL_DESC_INTERVIEW_AGENTS = """\
【Entrevista profunda - Entrevista real con agentes (doble plataforma)】
¡Llama a la API de entrevista del entorno de simulación OASIS para entrevistar a los agentes de simulación en ejecución!
Esto no es una simulación LLM, sino que llama a la interfaz de entrevista real para obtener las respuestas originales de los agentes de simulación.
Por defecto, entrevista simultáneamente en las plataformas Twitter y Reddit para obtener puntos de vista más completos.

Flujo de funciones:
1. Lee automáticamente el archivo de configuración de personajes para comprender a todos los agentes de simulación
2. Selecciona inteligentemente los agentes más relevantes para el tema de la entrevista (como estudiantes, medios, funcionarios, etc.)
3. Genera automáticamente preguntas de entrevista
4. Llama a la interfaz /api/simulation/interview/batch para realizar entrevistas reales en ambas plataformas
5. Integra todos los resultados de la entrevista para proporcionar análisis desde múltiples perspectivas

【Escenarios de uso】
- Necesitas comprender la perspectiva de diferentes roles sobre el evento (¿qué piensan los estudiantes? ¿qué piensa la prensa? ¿qué dice el gobierno?)
- Necesitas recopilar opiniones y posiciones de múltiples partes
- Necesitas obtener las respuestas reales de los agentes de simulación (provenientes del entorno de simulación OASIS)
- Quieres que el informe sea más vívido e incluya "transcripciones de entrevistas"

【Contenido devuelto】
- Información de identidad del agente entrevistado
- Respuestas de entrevista de cada agente en ambas plataformas (Twitter y Reddit)
- Citas clave (se pueden citar directamente)
- Resumen de la entrevista y comparación de puntos de vista

【Importante】¡Se requiere que el entorno de simulación OASIS esté en ejecución para usar esta función!"""

# ── 大纲规划 prompt ──

PLAN_SYSTEM_PROMPT = """\
Eres un experto en la redacción de "Informes de predicción futura", con una "perspectiva de Dios" sobre el mundo simulado: puedes observar el comportamiento, las palabras y las interacciones de cada agente en la simulación.

【Concepto central】
Hemos construido un mundo simulado y le hemos inyectado "requisitos de simulación" específicos como variables. El resultado de la evolución del mundo simulado es una predicción de lo que podría suceder en el futuro. Lo que estás observando no son "datos experimentales", sino una "previsualización del futuro".

【Tu tarea】
Redacta un "Informe de predicción futura" que responda a las siguientes preguntas:
1. ¿Qué sucedió en el futuro bajo las condiciones que establecimos?
2. ¿Cómo reaccionaron y actuaron los diferentes tipos de agentes (multitudes)?
3. ¿Qué tendencias futuras y riesgos dignos de mención revela esta simulación?

【Posicionamiento del informe】
- ✅ Este es un informe de predicción futura basado en simulaciones, que revela "qué pasaría si así fuera"
- ✅ Se centra en los resultados de la predicción: dirección del evento, reacciones de la multitud, fenómenos emergentes, riesgos potenciales
- ✅ Las palabras y acciones de los agentes en el mundo simulado son predicciones del comportamiento futuro de la multitud
- ❌ No es un análisis de la situación actual del mundo real
- ❌ No es una revisión general de la opinión pública

【Restricción en el número de capítulos】
- Mínimo 2 capítulos, máximo 5 capítulos
- No se requieren subcapítulos, cada capítulo debe redactar contenido completo directamente
- El contenido debe ser conciso, centrado en los hallazgos de predicción clave
- La estructura de capítulos será diseñada por ti según los resultados de la predicción

Por favor, genera el esquema del informe en formato JSON, con el siguiente formato:
{
    "title": "Título del informe",
    "summary": "Resumen del informe (una frase que resuma los hallazgos clave de la predicción)",
    "sections": [
        {
            "title": "Título del capítulo",
            "description": "Descripción del contenido del capítulo"
        }
    ]
}

¡Nota: El array sections debe tener un mínimo de 2 y un máximo de 5 elementos!"""

PLAN_USER_PROMPT_TEMPLATE = """\
【Configuración del escenario de predicción】
Variables que inyectamos en el mundo simulado (requisitos de simulación): {simulation_requirement}

【Tamaño del mundo simulado】
- Número de entidades que participan en la simulación: {total_nodes}
- Número de relaciones generadas entre entidades: {total_edges}
- Distribución de tipos de entidades: {entity_types}
- Número de agentes activos: {total_entities}

【Muestras de hechos futuros predichos】
{related_facts_json}

Por favor,审视 este futuro previsualizado desde una "perspectiva de Dios":
1. ¿Qué estado presentó el futuro bajo las condiciones que establecimos?
2. ¿Cómo reaccionaron y actuaron los diferentes tipos de personas (agentes)?
3. ¿Qué tendencias futuras dignas de mención revela esta simulación?

Según los resultados de la predicción, diseña la estructura de capítulos más adecuada.

【Recordatorio】El número de capítulos del informe: mínimo 2, máximo 5, el contenido debe ser conciso y centrarse en los hallazgos clave de la predicción."""

# ── Generación de capítulos prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
Eres un experto en la redacción de "Informes de predicción futura", redactando actualmente un capítulo del informe.

Título del informe: {report_title}
Resumen del informe: {report_summary}
Escenario de predicción (requisitos de simulación): {simulation_requirement}

Capítulo actual a redactar: {section_title}

═══════════════════════════════════════════════════════════════
【Concepto central】
═══════════════════════════════════════════════════════════════

El mundo simulado es una previsualización del futuro. Inyectamos condiciones específicas (requisitos de simulación) en el mundo simulado,
y las palabras y acciones de los agentes en la simulación son predicciones del comportamiento futuro de la multitud.

Tu tarea es:
- Revelar qué sucedió en el futuro bajo las condiciones establecidas
- Predecir cómo reaccionaron y actuaron los diferentes tipos de personas (agentes)
- Descubrir tendencias futuras, riesgos y oportunidades dignos de mención

❌ No escribas un análisis de la situación actual del mundo real
✅ Céntrate en "qué pasaría si así fuera" - los resultados de la simulación son el futuro predicho

═══════════════════════════════════════════════════════════════
【Regla más importante - Debe cumplirse】
═══════════════════════════════════════════════════════════════

1. 【Debe usar herramientas para observar el mundo simulado】
   - Estás observando una previsualización del futuro desde una "perspectiva de Dios"
   - Todo el contenido debe provenir de eventos y acciones/palabras de los agentes que ocurrieron en el mundo simulado
   - Está prohibido usar tu propio conocimiento para escribir el contenido del informe
   - Cada capítulo debe llamar a la herramienta al menos 3 veces (máximo 5 veces) para observar el mundo simulado, lo que representa el futuro

2. 【Debe citar las acciones y palabras originales de los agentes】
   - Las acciones y palabras de los agentes son predicciones del comportamiento futuro de la multitud
   - Usa el formato de cita en el informe para mostrar estas predicciones, por ejemplo:
     > "Cierto tipo de personas dirá: contenido original..."
   - Estas citas son la evidencia central de la predicción simulada

3. 【Consistencia de idioma - El contenido de la cita debe traducirse al idioma del informe】
   - El contenido devuelto por la herramienta puede contener expresiones diferentes al idioma del informe
   - El informe debe escribirse completamente en el idioma especificado por el usuario
   - Cuando cites contenido devuelto por la herramienta en otro idioma, debes traducirlo al idioma del informe antes de escribirlo
   - La traducción debe mantener el significado original y asegurar una expresión natural y fluida
   - Esta regla se aplica tanto al texto principal como al contenido dentro de los bloques de cita (> formato)

4. 【Presentación fiel de los resultados de la predicción】
   - El contenido del informe debe reflejar los resultados de la simulación que representan el futuro
   - No añadas información que no existe en la simulación
   - Si alguna información es insuficiente, indícalo tal cual

═══════════════════════════════════════════════════════════════
【⚠️ Formato - ¡Extremadamente importante!】
═══════════════════════════════════════════════════════════════

【Un capítulo = unidad mínima de contenido】
- Cada capítulo es la unidad de división más pequeña del informe
- ❌ Está prohibido usar cualquier título Markdown (como #, ##, ###, ####, etc.) dentro del capítulo
- ❌ Está prohibido añadir el título principal del capítulo al inicio del contenido
- ✅ El título del capítulo es añadido automáticamente por el sistema, tú solo necesitas escribir contenido de texto puro
- ✅ Usa **negrita**, separación de párrafos, citas, listas para organizar el contenido, pero no uses títulos

【Ejemplo correcto】
```
Este capítulo analiza la situación de propagación de la opinión pública del evento. A través de un análisis profundo de los datos simulados, descubrimos que...

**Fase inicial de explosión**

Weibo, como primera escena de la opinión pública, asumió la función central de lanzamiento de información:

> "Weibo contribuyó con el 68% de las primeras voces..."

**Fase de amplificación emocional**

La plataforma Douyin amplificó aún más la influencia del evento:

- Fuerte impacto visual
- Alta resonancia emocional
```

【Ejemplo incorrecto】
```
## Resumen ejecutivo          ← ¡Error! No añadas ningún título
### 1. Fase inicial     ← ¡Error! No uses ### para dividir subsecciones
#### 1.1 Análisis detallado   ← ¡Error! No uses #### para subdivisiones

Este capítulo analiza...
```

═══════════════════════════════════════════════════════════════
【Herramientas de búsqueda disponibles】（cada capítulo llama 3-5 veces）
═══════════════════════════════════════════════════════════════

{tools_description}

【Sugerencias de uso de herramientas - Por favor, mezcla diferentes herramientas, no uses solo una】
- insight_forge: Análisis profundo de insights, descompone automáticamente problemas y recupera hechos y relaciones desde múltiples dimensiones
- panorama_search: Búsqueda panorámica amplia, comprende la visión general del evento, la línea de tiempo y el proceso de evolución
- quick_search: Verificación rápida de un punto de información específico
- interview_agents: Entrevistar a agentes simulados para obtener perspectivas en primera persona y reacciones reales de diferentes roles

═══════════════════════════════════════════════════════════════
【Flujo de trabajo】
═══════════════════════════════════════════════════════════════

Cada respuesta solo puede hacer una de las siguientes dos cosas（no puedes hacer ambas al mismo tiempo）：

Opción A - Llamar a una herramienta:
Muestra tu pensamiento y luego llama a una herramienta con el siguiente formato:
<tool_call>
{{"name": "nombre de la herramienta", "parameters": {{"nombre del parámetro": "valor del parámetro"}}}}
</tool_call>
El sistema ejecutará la herramienta y te devolverá el resultado. No necesitas ni puedes escribir tú mismo el resultado de la herramienta.

Opción B - Escribir el contenido final:
Cuando hayas obtenido suficiente información a través de las herramientas, comienza a escribir el contenido del capítulo con "Final Answer:".

⚠️ Estrictamente prohibido:
- Está prohibido incluir tanto llamadas a herramientas como Final Answer en la misma respuesta
- Está prohibido inventar resultados de herramientas (Observation), todos los resultados de herramientas son inyectados por el sistema
- Cada respuesta puede llamar a una herramienta como máximo

═══════════════════════════════════════════════════════════════
【Requisitos de contenido del capítulo】
═══════════════════════════════════════════════════════════════

1. El contenido debe basarse en los datos simulados recuperados por las herramientas
2. Cita abundantemente el texto original para mostrar el efecto de la simulación
3. Usa formato Markdown（pero está prohibido usar títulos）：
   - Usa **texto en negrita** para marcar puntos clave（reemplaza los subtítulos）
   - Usa listas（- o 1.2.3.）para organizar los puntos principales
   - Usa líneas vacías para separar diferentes párrafos
   - ❌ Está prohibido usar cualquier sintaxis de título como #, ##, ###, ####
4. 【Formato de cita - Debe estar en un párrafo separado】
   Las citas deben estar en párrafos separados con una línea vacía antes y después, no deben mezclarse con otros párrafos:

   ✅ Formato correcto:
   ```
   La respuesta de la escuela fue considerada carente de sustancia.

   > "El patrón de respuesta de la escuela parecía rígido y lento en el entorno cambiante de las redes sociales."

   Esta evaluación reflejó la insatisfacción general del público.
   ```

   ❌ Formato incorrecto:
   ```
   La respuesta de la escuela fue considerada carente de sustancia.> "El patrón de respuesta de la escuela..." Esta evaluación reflejó...
   ```
5. Mantén la coherencia lógica con otros capítulos
6. 【Evita repeticiones】Lee cuidadosamente el contenido de los capítulos completados a continuación y no describas la misma información repetidamente
7. 【Énfasis nuevamente】¡No añadas ningún título! Usa **negrita** para reemplazar los subtítulos"""

SECTION_USER_PROMPT_TEMPLATE = """\
Contenido de los capítulos completados（por favor, léelo cuidadosamente para evitar repeticiones）：
{previous_content}

═══════════════════════════════════════════════════════════════
【Tarea actual】Escribir el capítulo: {section_title}
═══════════════════════════════════════════════════════════════

【Recordatorio importante】
1. Lee cuidadosamente el contenido de los capítulos completados arriba para evitar repetir la misma información
2. Debes llamar a una herramienta para obtener datos simulados antes de comenzar
3. Mezcla y usa diferentes herramientas, no uses solo una
4. El contenido del informe debe basarse en los resultados de la búsqueda, no uses tu propio conocimiento

【⚠️ Advertencia de formato - Debe cumplirse】
- ❌ No escribas ningún título（#、##、###、#### no están permitidos）
- ❌ No escribas "{section_title}" como encabezado
- ✅ El título del capítulo se añadirá automáticamente por el sistema
- ✅ Escribe directamente el cuerpo del texto, usa **negrita** para reemplazar los subtítulos

Por favor, comienza:
1. Primero piensa（Thought）qué información necesita este capítulo
2. Luego llama a una herramienta（Action）para obtener datos simulados
3. Después de recopilar suficiente información, emite Final Answer（solo texto, sin ningún título）"""

# ── Plantilla de mensaje dentro del ciclo ReACT ──

REACT_OBSERVATION_TEMPLATE = """\
Observation（Resultado de la búsqueda）:

═══ Herramienta {tool_name} devolvió ═══
{result}

═══════════════════════════════════════════════════════════════
Se han llamado a {tool_calls_count}/{max_tool_calls} herramientas（usadas: {used_tools_str}）{unused_hint}
- Si la información es suficiente: emite el contenido del capítulo comenzando con "Final Answer:"（debe citar el texto original de arriba）
- Si se necesita más información: llama a una herramienta para continuar la búsqueda
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "【注意】Solo has llamado a {tool_calls_count} herramientas, se necesitan al menos {min_tool_calls}。"
    "Por favor, llama a más herramientas para obtener más datos simulados y luego emite Final Answer。{unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Solo se han llamado a {tool_calls_count} herramientas, se necesitan al menos {min_tool_calls}。"
    "Por favor, llama a una herramienta para obtener datos simulados。{unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "El número de llamadas a herramientas ha alcanzado el límite（{tool_calls_count}/{max_tool_calls}），no se pueden llamar a más herramientas。"
    'Por favor, emite el contenido del capítulo comenzando con "Final Answer:" basado en la información obtenida。'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 No has usado: {unused_list} todavía, se recomienda probar diferentes herramientas para obtener información desde múltiples perspectivas"

REACT_FORCE_FINAL_MSG = "Se ha alcanzado el límite de llamadas a herramientas, por favor emite directamente Final Answer: y genera el contenido del capítulo。"

# ── Plantilla de mensaje de chat ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
Eres un asistente de simulación y predicción conciso y eficiente。

【Contexto】
Condición de simulación: {simulation_requirement}

【Informe de análisis generado】
{report_content}

【Reglas】
1. Prioriza responder basándote en el contenido del informe anterior
2. Responde directamente a la pregunta, evita explicaciones largas y tediosas
3. Solo llama a herramientas para recuperar más datos cuando el contenido del informe no sea suficiente
4. Las respuestas deben ser concisas, claras y organizadas

【Herramientas disponibles】（solo úsalas cuando sea necesario，máximo 1-2 llamadas）
{tools_description}

【Formato de llamada a herramienta】
<tool_call>
{{"name": "nombre de la herramienta", "parameters": {{"nombre del parámetro": "valor del parámetro"}}}}
</tool_call>

【Estilo de respuesta】
- Conciso y directo, sin explicaciones largas
- Usa el formato > para citar contenido clave
- Prioriza dar la conclusión y luego explicar la razón"""

CHAT_OBSERVATION_SUFFIX = "\n\nPor favor, responde la pregunta de forma concisa。"


# ═══════════════════════════════════════════════════════════════
# Clase ReportAgent
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Agente de generación de informes de simulación

    Utiliza el modo ReACT（Razonamiento + Actuación）:
    1. Fase de planificación：Analiza los requisitos de simulación y planifica la estructura del directorio del informe
    2. Fase de generación：Genera contenido capítulo por capítulo, cada capítulo puede llamar a herramientas varias veces para obtener información
    3. Fase de reflexión：Verifica la integridad y precisión del contenido
    """
    
    # Máximo de llamadas a herramientas（por capítulo）
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # Máximo de rondas de reflexión
    
    # Máximo de llamadas a herramientas（por chat）
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        Inicializa el Report Agent
        
        Args:
            graph_id: ID del grafo
            simulation_id: ID de la simulación
            simulation_requirement: Descripción del requisito de simulación
            llm_client: Cliente LLM（opcional）
            zep_tools: Servicio de herramientas Zep（opcional）
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        
        # Definición de herramientas
        self.tools = self._define_tools()
        
        # Registrador de informes（se inicializa en generate_report）
        self.report_logger: Optional[ReportLogger] = None
        # Registrador de consola（se inicializa en generate_report）
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(t('report.agentInitDone', graphId=graph_id, simulationId=simulation_id))
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Definición de herramientas disponibles"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "El tema o pregunta que quieres analizar en profundidad",
                    "report_context": "Contexto del capítulo actual del informe（opcional，ayuda a generar subpreguntas más precisas）"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Consulta de búsqueda，utilizada para ordenación por relevancia",
                    "include_expired": "¿Incluye contenido expirado/histórico?（por defecto True）"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Consulta de búsqueda",
                    "limit": "Número de resultados a devolver（opcional，por defecto 10）"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Tema de la entrevista o descripción de la necesidad（ej：'Comprender la opinión de los estudiantes sobre el incidente del formaldehído en el dormitorio'）",
                    "max_agents": "Número máximo de agentes a entrevistar（opcional，por defecto 5，máximo 10）"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Ejecuta la llamada a la herramienta
        
        Args:
            tool_name: Nombre de la herramienta
            parameters: Parámetros de la herramienta
            report_context: Contexto del informe（para InsightForge）
            
        Returns:
            Resultado de la ejecución de la herramienta（formato de texto）
        """
        logger.info(t('report.executingTool', toolName=tool_name, params=parameters))
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Búsqueda amplia - Obtener visión general
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Búsqueda simple - Recuperación rápida
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Entrevista en profundidad - Llamar a la API de entrevistas OASIS real para obtener las respuestas de los agentes simulados（plataforma dual）
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== Herramientas antiguas de compatibilidad hacia atrás（redirección interna a nuevas herramientas） ==========
            
            elif tool_name == "search_graph":
                # Redirección a quick_search
                logger.info(t('report.redirectToQuickSearch'))
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Redirección a insight_forge，porque es más potente
                logger.info(t('report.redirectToInsightForge'))
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Herramienta desconocida: {tool_name}。Por favor, utiliza una de las siguientes herramientas: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(t('report.toolExecFailed', toolName=tool_name, error=str(e)))
            return f"La ejecución de la herramienta falló: {str(e)}"
    
    # Conjunto de nombres de herramientas válidos，para verificación al analizar JSON desnudo de respaldo
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Analiza las llamadas a herramientas desde la respuesta del LLM

        Formatos admitidos（por prioridad）：
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. JSON desnudo（la respuesta completa o una sola línea es un JSON de llamada a herramienta）
        """
        tool_calls = []

        # Formato 1: Estilo XML（formato estándar）
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Formato 2: Respaldo - El LLM genera directamente JSON desnudo（sin etiquetas <tool_call>）
        # Solo se intenta cuando el formato 1 no coincide，para evitar la coincidencia errónea de JSON en el cuerpo
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # La respuesta puede contener texto de pensamiento + JSON desnudo，intenta extraer el último objeto JSON
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Verifica si el JSON analizado es una llamada a herramienta válida"""
        # Admite los dos nombres de clave {"name": ..., "parameters": ...} y {"tool": ..., "params": ...}
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Unificar los nombres de clave a name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """Genera el texto de descripción de la herramienta"""
        desc_parts = ["Herramientas disponibles:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  参数: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Planificación del esquema del informe
        
        Utiliza LLM para analizar los requisitos de simulación y planificar la estructura del directorio del informe
        
        Args:
            progress_callback: Función de devolución de llamada de progreso
            
        Returns:
            ReportOutline: Esquema del informe
        """
        logger.info(t('report.startPlanningOutline'))
        
        if progress_callback:
            progress_callback("planning", 0, t('progress.analyzingRequirements'))
        
        # Primero obtener el contexto de simulación
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, t('progress.generatingOutline'))
        
        system_prompt = f"{PLAN_SYSTEM_PROMPT}\n\n{get_language_instruction()}"
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, t('progress.parsingOutline'))
            
            # 解析大纲
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "模拟分析报告"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, t('progress.outlinePlanComplete'))
            
            logger.info(t('report.outlinePlanDone', count=len(sections)))
            return outline
            
        except Exception as e:
            logger.error(t('report.outlinePlanFailed', error=str(e)))
            # Devolver el esquema predeterminado（3 capítulos，como fallback）
            return ReportOutline(
                title="Informe de predicción futura",
                summary="Análisis de tendencias futuras y riesgos basado en predicciones de simulación",
                sections=[
                    ReportSection(title="Escenarios de predicción y hallazgos clave"),
                    ReportSection(title="Análisis de predicción del comportamiento de la multitud"),
                    ReportSection(title="Perspectivas de tendencias y consejos de riesgo")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Genera el contenido de una sección individual utilizando el patrón ReACT
        
        Ciclo ReACT：
        1. Thought（Pensamiento）- Analiza qué información se necesita
        2. Action（Acción）- Llama a herramientas para obtener información
        3. Observation（Observación）- Analiza los resultados devueltos por la herramienta
        4. Repite hasta que la información sea suficiente o alcance el número máximo de veces
        5. Final Answer（Respuesta final）- Genera el contenido de la sección
        
        Args:
            section: Sección a generar
            outline: Esquema completo
            previous_sections: Contenido de las secciones anteriores（para mantener la coherencia）
            progress_callback: Devolución de llamada de progreso
            section_index: Índice de la sección（para registro de logs）
            
        Returns:
            Contenido de la sección（formato Markdown）
        """
        logger.info(t('report.reactGenerateSection', title=section.title))
        
        # Registro de log de inicio de sección
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )
        system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"

        # Construir prompt de usuario - cada sección completada transmite un máximo de 4000 caracteres
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Cada sección tiene un máximo de 4000 caracteres
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "（Esta es la primera sección）"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Ciclo ReACT
        tool_calls_count = 0
        max_iterations = 5  # Número máximo de iteraciones
        min_tool_calls = 3  # Número mínimo de llamadas a herramientas
        conflict_retries = 0  # Número de reintentos consecutivos de conflicto entre llamadas a herramientas y Final Answer
        used_tools = set()  # Registro de nombres de herramientas utilizadas
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # Contexto del informe, utilizado para la generación de subproblemas de InsightForge
        report_context = f"Título de la sección: {section.title}\nRequisito de simulación: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    t('progress.deepSearchAndWrite', current=tool_calls_count, max=self.MAX_TOOL_CALLS_PER_SECTION)
                )
            
            # Llamar a LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Verificar si la respuesta de LLM es None（excepción de API o contenido vacío）
            if response is None:
                logger.warning(t('report.sectionIterNone', title=section.title, iteration=iteration + 1))
                # Si todavía hay iteraciones, agregar mensaje y reintentar
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "（Respuesta vacía）"})
                    messages.append({"role": "user", "content": "请继续生成内容。"})
                    continue
                # La última iteración también devuelve None, sale del ciclo y entra en el cierre forzado
                break

            logger.debug(f"Respuesta de LLM: {response[:200]}...")

            # Analizar una vez, reutilizar el resultado
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Manejo de conflictos: LLM genera llamadas a herramientas y Final Answer al mismo tiempo ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    t('report.sectionConflict', title=section.title, iteration=iteration+1, conflictCount=conflict_retries)
                )

                if conflict_retries <= 2:
                    # Las primeras dos veces: descartar la respuesta actual y pedir a LLM que responda nuevamente
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "【Error de formato】Has incluido llamadas a herramientas y Final Answer en la misma respuesta, lo cual no está permitido。\n"
                            "Cada respuesta solo puede hacer una de las siguientes dos cosas:\n"
                            "- Llamar a una herramienta（输出一个 <tool_call> 块，不要写 Final Answer）\n"
                            "- 输出最终内容（以 'Final Answer:' 开头，不要包含 <tool_call>）\n"
                            "Por favor, responde de nuevo, haciendo solo una de estas cosas。"
                        ),
                    })
                    continue
                else:
                    # Tercera vez: tratamiento de degradación, truncado a la primera llamada a herramienta, ejecución forzada
                    logger.warning(
                        t('report.sectionConflictDowngrade', title=section.title, conflictCount=conflict_retries)
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Registrar el log de respuesta de LLM
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── 情况1：LLM 输出了 Final Answer ──
            if has_final_answer:
                # 工具调用次数不足，拒绝并要求继续调工具
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"（这些工具还未使用，推荐用一下他们: {', '.join(unused_tools)}）" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # 正常结束
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(t('report.sectionGenDone', title=section.title, count=tool_calls_count))

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Caso 2: LLM intenta llamar a una herramienta ──
            if has_tool_calls:
                # Límite de herramientas agotado → informar claramente, solicitar Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Solo ejecutar la primera llamada a herramienta
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(t('report.multiToolOnlyFirst', total=len(tool_calls), toolName=call['name']))

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Construir pista de herramientas no utilizadas
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Caso 3: No hay llamadas a herramientas ni Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Número insuficiente de llamadas a herramientas, recomendar herramientas no utilizadas
                unused_tools = all_tools - used_tools
                unused_hint = f"（这些工具还未使用，推荐用一下他们: {', '.join(unused_tools)}）" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # 工具调用已足够，LLM 输出了内容但没带 "Final Answer:" 前缀
            # 直接将这段内容作为最终答案，不再空转
            logger.info(t('report.sectionNoPrefix', title=section.title, count=tool_calls_count))
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # 达到最大迭代次数，强制生成内容
        logger.warning(t('report.sectionMaxIter', title=section.title))
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Verificar si la respuesta de LLM es None durante el cierre forzado
        if response is None:
            logger.error(t('report.sectionForceFailed', title=section.title))
            final_answer = t('report.sectionGenFailedContent')
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Registrar el log de contenido de la sección completado
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generar informe completo（salida en tiempo real por capítulos）
        
        Cada capítulo se guarda en una carpeta inmediatamente después de su generación, sin esperar a que se complete todo el informe.
        Estructura de archivos:
        reports/{report_id}/
            meta.json       - Metadatos del informe
            outline.json    - Esquema del informe
            progress.json   - Progreso de generación
            section_01.md   - Capítulo 1
            section_02.md   - Capítulo 2
            ...
            full_report.md  - Informe completo
        
        Args:
            progress_callback: Función de devolución de llamada de progreso (stage, progress, message)
            report_id: ID del informe (opcional, se generará automáticamente si no se proporciona)
            
        Returns:
            Report: Informe completo
        """
        import uuid
        
        # Si no se proporciona report_id, se generará automáticamente
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # Lista de títulos de secciones completadas (para seguimiento del progreso)
        completed_section_titles = []
        
        try:
            # Inicialización: crear la carpeta del informe y guardar el estado inicial
            ReportManager._ensure_report_folder(report_id)
            
            # Inicializar el registrador de logs (log estructurado agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Inicializar el registrador de logs de consola (console_log.txt)
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, t('progress.initReport'),
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Fase 1: Planificar el esquema
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, t('progress.startPlanningOutline'),
                completed_sections=[]
            )
            
            # Registrar el log de inicio de planificación
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, t('progress.startPlanningOutline'))
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # Registrar el log de planificación completado
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # Guardar el esquema en el archivo
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, t('progress.outlineDone', count=len(outline.sections)),
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(t('report.outlineSavedToFile', reportId=report_id))
            
            # Fase 2: Generación por capítulos (guardado por capítulos)
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # Guardar contenido para contexto
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # Actualizar el progreso
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    t('progress.generatingSection', title=section.title, current=section_num, total=total_sections),
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )

                if progress_callback:
                    progress_callback(
                        "generating",
                        base_progress,
                        t('progress.generatingSection', title=section.title, current=section_num, total=total_sections)
                    )
                
                # Generar el contenido del capítulo principal
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Guardar el capítulo
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Registrar el log de capítulo completado
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(t('report.sectionSaved', reportId=report_id, sectionNum=f"{section_num:02d}"))
                
                # Actualizar el progreso
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    t('progress.sectionDone', title=section.title),
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Fase 3: Ensamblar el informe completo
            if progress_callback:
                progress_callback("generating", 95, t('progress.assemblingReport'))
            
            ReportManager.update_progress(
                report_id, "generating", 95, t('progress.assemblingReport'),
                completed_sections=completed_section_titles
            )
            
            # Usar ReportManager para ensamblar el informe completo
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Calcular el tiempo total transcurrido
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # Registrar el log de informe completado
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Guardar el informe final
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, t('progress.reportComplete'),
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, t('progress.reportComplete'))
            
            logger.info(t('report.reportGenDone', reportId=report_id))
            
            # Cerrar el registrador de logs de consola
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(t('report.reportGenFailed', error=str(e)))
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # Registrar el log de error
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # Guardar el estado de fallo
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, t('progress.reportFailed', error=str(e)),
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignorar errores de guardado
            
            # Cerrar el registrador de logs de consola
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Hablando con el agente de informes
        
        En el diálogo, el agente puede llamar de forma autónoma a la herramienta de recuperación para responder preguntas
        
        Args:
            message: Mensajes de usuario
            chat_history: Historial de chat
            
        Returns:
            {
                "response": "Respuesta del agente",
                "tool_calls": [Lista de herramientas llamadas],
                "sources": [Fuentes de información]
            }
        """
        logger.info(t('report.agentChat', message=message[:50]))
        
        chat_history = chat_history or []
        
        # Obtener el contenido del informe generado
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limitar la longitud del informe para evitar un contexto demasiado largo
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [El contenido del informe ha sido truncado] ..."
        except Exception as e:
            logger.warning(t('report.fetchReportFailed', error=e))
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "（暂无报告）",
            tools_description=self._get_tools_description(),
        )
        system_prompt = f"{system_prompt}\n\n{get_language_instruction()}"

        # Construir mensajes
        messages = [{"role": "system", "content": system_prompt}]
        
        # Agregar historial de chat
        for h in chat_history[-10:]:  # Limitar la longitud del historial
            messages.append(h)
        
        # Agregar mensaje de usuario
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # Bucle ReACT (versión simplificada)
        tool_calls_made = []
        max_iterations = 2  # Reducir el número de iteraciones
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Analizar las llamadas a herramientas
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # Sin llamadas a herramientas, devolver la respuesta directamente
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Ejecutar llamadas a herramientas (limitar la cantidad)
            tool_results = []
            for call in tool_calls[:1]:  # Ejecutar como máximo 1 llamada a herramienta por ronda
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limitar la longitud del resultado
                })
                tool_calls_made.append(call)
            
            # Agregar el resultado a los mensajes
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']}结果]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Alcanzar el número máximo de iteraciones para obtener la respuesta final
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Limpiar la respuesta
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Gestor de informes
    
    Responsable del almacenamiento y recuperación persistentes de informes
    
    Estructura de archivos (salida por capítulos):
    reports/
      {report_id}/
        meta.json          - 元信息 y estado del informe
        outline.json       - Esquema del informe
        progress.json      - Progreso de generación
        section_01.md      - Capítulo 1
        section_02.md      - Capítulo 2
        ...
        full_report.md     - Informe completo
    """
    
    # Directorio de almacenamiento de informes
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Asegurar que el directorio raíz del informe existe"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Obtener la ruta de la carpeta del informe"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Asegurar que la carpeta del informe existe y devolver la ruta"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Obtener la ruta del archivo de metadatos del informe"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Obtener la ruta del archivo Markdown del informe completo"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Obtener la ruta del archivo de esquema"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Obtener la ruta del archivo de progreso"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Obtener la ruta del archivo Markdown de la sección"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Obtener la ruta del archivo de registro del agente"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Obtener la ruta del archivo de registro de la consola"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Obtener el contenido del registro de la consola
        
        Este es el registro de salida de la consola durante el proceso de generación del informe
        (INFO, WARNING, etc.), diferente del registro estructurado agent_log.jsonl.
        
        Args:
            report_id: ID del informe
            from_line: Desde qué línea comenzar a leer (para obtención incremental, 0 significa desde el principio)
            
        Returns:
            {
                "logs": [Lista de líneas de registro],
                "total_lines": Número total de líneas,
                "from_line": Línea de inicio,
                "has_more": Si hay más registros
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Conservar la línea de registro original, eliminar el carácter de nueva línea final
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Se ha leído hasta el final
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Obtener el registro completo de la consola (obtener todo de una vez)
        
        Args:
            report_id: ID del informe
            
        Returns:
            Lista de líneas de registro
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Obtener el contenido del registro del agente
        
        Args:
            report_id: ID del informe
            from_line: Desde qué línea comenzar a leer (para obtención incremental, 0 significa desde el principio)
            
        Returns:
            {
                "logs": [Lista de entradas de registro],
                "total_lines": Número total de líneas,
                "from_line": Línea de inicio,
                "has_more": Si hay más registros
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # 跳过解析失败的行
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # 已读取到末尾
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Obtener el registro completo del agente (para obtener todo de una vez)
        
        Args:
            report_id: ID del informe
            
        Returns:
            Lista de entradas de registro
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Guardar el esquema del informe
        
        Se llama inmediatamente después de completar la fase de planificación
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(t('report.outlineSaved', reportId=report_id))
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Guardar una sola sección
        
        Se llama inmediatamente después de completar cada sección para lograr la salida por secciones
        
        Args:
            report_id: ID del informe
            section_index: Índice de la sección (comenzando desde 1)
            section: Objeto de la sección
            
        Returns:
            Ruta del archivo guardado
        """
        cls._ensure_report_folder(report_id)

        # Construir el contenido Markdown de la sección - limpiar títulos duplicados que puedan existir
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # 保存文件
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(t('report.sectionFileSaved', reportId=report_id, fileSuffix=file_suffix))
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Limpiar el contenido de la sección
        
        1. Eliminar las líneas de título Markdown que se repiten al principio del contenido con el título de la sección
        2. Convertir todos los títulos de nivel ### y inferiores a texto en negrita
        
        Args:
            content: Contenido original
            section_title: Título de la sección
            
        Returns:
            Contenido limpio
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Verificar si es una línea de título Markdown
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Verificar si es un título que se repite con el título de la sección (saltar duplicados dentro de las primeras 5 líneas)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Convertir todos los títulos de nivel (###, ##, ###, ####, etc.) a negrita
                # Porque el título de la sección es agregado por el sistema, el contenido no debe tener ningún título
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Agregar línea vacía
                continue
            
            # Si la línea anterior fue un título omitido y la línea actual está vacía, también omitirla
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Eliminar las líneas vacías iniciales
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Eliminar las líneas divisorias iniciales
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # También eliminar las líneas vacías después de la línea divisoria
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Actualizar el progreso de generación del informe
        
        El frontend puede obtener el progreso en tiempo real leyendo progress.json
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Obtener el progreso de generación del informe"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Obtener la lista de capítulos generados
        
        Devolver la información de todos los archivos de capítulo guardados
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Extraer el índice de la sección del nombre del archivo
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Ensamblar el informe completo
        
        Ensamblar el informe completo a partir de los archivos de capítulo guardados y realizar la limpieza de títulos
        """
        folder = cls._get_report_folder(report_id)
        
        # Construir la cabecera del informe
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # Leer todos los archivos de capítulo en orden
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # Post-procesamiento: limpiar el problema de título de todo el informe
        md_content = cls._post_process_report(md_content, outline)
        
        # Guardar el informe completo
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(t('report.fullReportAssembled', reportId=report_id))
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Procesamiento posterior del contenido del informe
        
        1. Eliminar títulos duplicados
        2. Conservar el título principal del informe (#) y los títulos de los capítulos (##), eliminar otros niveles de títulos (###, ####, etc.)
        3. Limpiar líneas en blanco y separadores adicionales
        
        Args:
            content: Contenido del informe original
            outline: Esquema del informe
            
        Returns:
            Contenido procesado
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Recopilar todos los títulos de los capítulos en el esquema
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Verificar si es una línea de título
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Verificar si es un título duplicado (el mismo contenido aparece en los últimos 5 títulos)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Saltar el título duplicado y las líneas en blanco posteriores
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Procesamiento por niveles de título:
                # - # (nivel=1) Solo保留 el título principal del informe
                # - ## (nivel=2) 保留 los títulos de los capítulos
                # - ### y niveles inferiores (nivel>=3) se convierten en texto en negrita
                
                if level == 1:
                    if title == outline.title:
                        # 保留 el título principal del informe
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Los títulos de los capítulos usan # incorrectamente, corrígelos a ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Los títulos de nivel 1 que no son capítulos se convierten en texto en negrita
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Conservar los títulos de los capítulos.
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Los títulos de nivel 2 que no son capítulos se convierten en texto en negrita
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### y niveles inferiores se convierten en texto en negrita
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Saltar la línea divisoria que sigue inmediatamente al título
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Solo mantén una línea en blanco después del título
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Limpiar múltiples líneas vacías consecutivas（保留最多2个）
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Guardar metadatos del informe y informe completo"""
        cls._ensure_report_folder(report.report_id)
        
        # Guardar metadatos JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Guardar esquema
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # Guardar informe Markdown completo
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(t('report.reportSaved', reportId=report.report_id))
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Obtener informe"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Compatibilidad con formatos antiguos: Verificar archivos almacenados directamente en el directorio reports
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 重建Report对象
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # Si markdown_content está vacío, intenta leer desde full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """根据模拟ID获取报告"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Nuevo formato: Carpeta
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Compatibilidad con formatos antiguos: Archivo JSON
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """Listar informes"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Nuevo formato: Carpeta
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Compatibilidad con formatos antiguos: Archivo JSON
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # Ordenar por fecha de creación descendente
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Eliminar informe（carpeta completa）"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # Nuevo formato: Eliminar la carpeta completa
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(t('report.reportFolderDeleted', reportId=report_id))
            return True
        
        # Compatibilidad con formatos antiguos: Eliminar archivos individuales
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
