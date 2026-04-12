"""
Módulo de comunicación IPC simulada

Se utiliza para la comunicación entre procesos entre el backend de Flask y el script simulado.
Implementa un patrón simple de comando/respuesta a través del sistema de archivos:
1. Flask escribe los comandos en el directorio `commands/`.
2. El script simulado consulta el directorio de comandos, ejecuta los comandos y escribe las respuestas en el directorio `responses/`.
3. Flask consulta el directorio `responses/` para obtener los resultados.
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger('mirofish.simulation_ipc')


class CommandType(str, Enum):
    """Tipo de comando"""
    INTERVIEW = "interview"           # Entrevista a un solo agente
    BATCH_INTERVIEW = "batch_interview"  # Entrevista por lotes
    CLOSE_ENV = "close_env"           # Cerrar entorno


class CommandStatus(str, Enum):
    """Estado del comando"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """Comando IPC"""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """Respuesta IPC"""
    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """
    Cliente IPC simulado (utilizado por el lado de Flask)
    
    Se utiliza para enviar comandos al proceso simulado y esperar respuestas.
    """
    
    def __init__(self, simulation_dir: str):
        """
        Inicializar el cliente IPC
        
        Args:
            simulation_dir: Directorio de datos de simulación
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        
        # 确保目录存在
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
    
    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """
        Enviar comando y esperar respuesta
        
        Args:
            command_type: Tipo de comando
            args: Argumentos del comando
            timeout: Tiempo de espera (segundos)
            poll_interval: Intervalo de sondeo (segundos)
            
        Returns:
            IPCResponse
            
        Raises:
            TimeoutError: Tiempo de espera de respuesta excedido
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )
        
        # Escribir el archivo de comando
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        with open(command_file, 'w', encoding='utf-8') as f:
            json.dump(command.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Enviando comando IPC: {command_type.value}, command_id={command_id}")
        
        # Esperar respuesta
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response_data = json.load(f)
                    response = IPCResponse.from_dict(response_data)
                    
                    # Limpiar archivos de comando y respuesta
                    try:
                        os.remove(command_file)
                        os.remove(response_file)
                    except OSError:
                        pass
                    
                    logger.info(f"Respuesta IPC recibida: command_id={command_id}, status={response.status.value}")
                    return response
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Error al analizar la respuesta: {e}")
            
            time.sleep(poll_interval)
        
        # Tiempo de espera excedido
        logger.error(f"Tiempo de espera de respuesta IPC excedido: command_id={command_id}")
        
        # Limpiar archivo de comando
        try:
            os.remove(command_file)
        except OSError:
            pass
        
        raise TimeoutError(f"Tiempo de espera de respuesta de comando excedido ({timeout} segundos)")
    
    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> IPCResponse:
        """
        Enviar comando de entrevista a un solo agente
        
        Args:
            agent_id: ID del agente
            prompt: Pregunta de la entrevista
            platform: Plataforma especificada (opcional)
                - "twitter": Solo entrevista a la plataforma Twitter
                - "reddit": Solo entrevista a la plataforma Reddit  
                - None: En simulación de doble plataforma, entrevista a ambas plataformas simultáneamente; en simulación de plataforma única, entrevista a esa plataforma
            timeout: Tiempo de espera
            
        Returns:
            IPCResponse，el campo result contiene los resultados de la entrevista
        """
        args = {
            "agent_id": agent_id,
            "prompt": prompt
        }
        if platform:
            args["platform"] = platform
            
        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )
    
    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """
        Enviar comando de entrevista por lotes
        
        Args:
            interviews: Lista de entrevistas, cada elemento incluye {"agent_id": int, "prompt": str, "platform": str(opcional)}
            platform: Plataforma predeterminada (opcional, será sobrescrita por la plataforma de cada elemento de entrevista)
                - "twitter": Solo entrevista a la plataforma Twitter
                - "reddit": Solo entrevista a la plataforma Reddit
                - None: En simulación de doble plataforma, cada agente entrevista a ambas plataformas simultáneamente
            timeout: Tiempo de espera
            
        Returns:
            IPCResponse，el campo result contiene los resultados de todas las entrevistas
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform
            
        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )
    
    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """
        Enviar comando de cierre de entorno
        
        Args:
            timeout: Tiempo de espera
            
        Returns:
            IPCResponse
        """
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )
    
    def check_env_alive(self) -> bool:
        """
        Verificar si el entorno de simulación está activo
        
        Se determina comprobando el archivo env_status.json
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return False
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return status.get("status") == "alive"
        except (json.JSONDecodeError, OSError):
            return False


class SimulationIPCServer:
    """
    Servidor IPC simulado (utilizado por el script de simulación)
    
    Sondea el directorio de comandos, ejecuta comandos y devuelve respuestas
    """
    
    def __init__(self, simulation_dir: str):
        """
        Inicializar el servidor IPC
        
        Args:
            simulation_dir: Directorio de datos de simulación
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        
        # Asegurar que los directorios existan
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
        
        # Estado del entorno
        self._running = False
    
    def start(self):
        """Marcar el servidor como en ejecución"""
        self._running = True
        self._update_env_status("alive")
    
    def stop(self):
        """Marcar el servidor como detenido"""
        self._running = False
        self._update_env_status("stopped")
    
    def _update_env_status(self, status: str):
        """Actualizar el archivo de estado del entorno"""
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def poll_commands(self) -> Optional[IPCCommand]:
        """
        Sondea el directorio de comandos y devuelve el primer comando pendiente de procesamiento
        
        Returns:
            IPCCommand o None
        """
        if not os.path.exists(self.commands_dir):
            return None
        
        # 按时间排序获取命令文件
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))
        
        command_files.sort(key=lambda x: x[1])
        
        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return IPCCommand.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Error al leer el archivo de comando: {filepath}, {e}")
                continue
        
        return None
    
    def send_response(self, response: IPCResponse):
        """
        Enviar respuesta
        
        Args:
            response: Respuesta IPC
        """
        response_file = os.path.join(self.responses_dir, f"{response.command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Eliminar el archivo de comando
        command_file = os.path.join(self.commands_dir, f"{response.command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass
    
    def send_success(self, command_id: str, result: Dict[str, Any]):
        """Enviar respuesta de éxito"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))
    
    def send_error(self, command_id: str, error: str):
        """Enviar respuesta de error"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
