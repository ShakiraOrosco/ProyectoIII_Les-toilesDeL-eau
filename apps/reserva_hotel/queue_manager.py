# ========================================
# ARCHIVO: apps/reserva_hotel/queue_manager.py
# Sistema de Teoría de Colas con BATCHING (espera competencia)
# ========================================
import threading
import queue
import time
from datetime import datetime
from django.db import transaction, connection
from django.db.utils import OperationalError
from .models import ReservaHotel
from apps.habitacion.models import Habitacion
from apps.reservas_gen.models import ReservasGen

class ReservaRequest:
    """Clase que representa una solicitud de reserva en la cola"""
    
    def __init__(self, datos_reserva, datos_cliente, habitacion_id, empleado, administrador):
        self.datos_reserva = datos_reserva
        self.datos_cliente = datos_cliente
        self.habitacion_id = habitacion_id
        self.empleado = empleado
        self.administrador = administrador
        self.prioridad = self.calcular_prioridad()
        self.timestamp = datetime.now()
        self.resultado = None
        self.evento = threading.Event()
        
        # Convertir fechas a objetos datetime.date para comparaciones
        self.fecha_ini_dt = datetime.strptime(self.datos_reserva['fecha_ini'], '%Y-%m-%d').date()
        self.fecha_fin_dt = datetime.strptime(self.datos_reserva['fecha_fin'], '%Y-%m-%d').date()
    
    def calcular_prioridad(self):
        """
        Calcula la prioridad de la reserva según:
        1. Duración de estadía (mayor = más prioridad)
        2. Cantidad de personas (mayor = más prioridad)
        
        Valores MÁS ALTOS = MAYOR PRIORIDAD
        """
        fecha_ini = datetime.strptime(self.datos_reserva['fecha_ini'], '%Y-%m-%d')
        fecha_fin = datetime.strptime(self.datos_reserva['fecha_fin'], '%Y-%m-%d')
        duracion = (fecha_fin - fecha_ini).days
        cant_personas = int(self.datos_reserva['cant_personas'])
        
        prioridad = duracion * 100 + cant_personas
        return prioridad
    
    def tiene_conflicto_fechas(self, otra_request):
        """Verifica si hay solapamiento de fechas"""
        return (self.fecha_ini_dt < otra_request.fecha_fin_dt and 
                self.fecha_fin_dt > otra_request.fecha_ini_dt)
    
    def __lt__(self, other):
        """Comparador: Mayor prioridad = se procesa primero"""
        if self.prioridad != other.prioridad:
            return self.prioridad > other.prioridad
        return self.timestamp < other.timestamp


class ColaReservasHotel:
    """
    Gestor de cola de prioridad con BATCHING
    Espera un tiempo para acumular solicitudes antes de procesarlas
    """
    _instance = None
    _lock = threading.Lock()
    
    # ⏱️ TIEMPO DE ESPERA para acumular solicitudes concurrentes (en segundos)
    TIEMPO_BATCHING = 2.0  # Espera 2 segundos para acumular solicitudes
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._inicializar()
        return cls._instance
    
    def _inicializar(self):
        """Inicializa la cola y el worker thread"""
        self.cola = queue.PriorityQueue()
        self.procesando = {}  # {habitacion_id: [lista de requests]}
        self.worker_activo = True
        self.worker_thread = threading.Thread(target=self._procesar_cola, daemon=True)
        self.worker_thread.start()
        print(f"🔄 Cola de reservas iniciada con batching de {self.TIEMPO_BATCHING}s")
    
    def agregar_reserva(self, datos_reserva, datos_cliente, habitacion_id, empleado, administrador):
        """
        Agrega una nueva solicitud de reserva a la cola
        Returns:
            ReservaRequest: objeto con el resultado de la reserva
        """
        request = ReservaRequest(datos_reserva, datos_cliente, habitacion_id, empleado, administrador)
        
        # Agregar marca de tiempo de procesamiento (ahora + tiempo de batching)
        request.tiempo_procesamiento = time.time() + self.TIEMPO_BATCHING
        
        self.cola.put(request)
        
        with self._lock:
            if habitacion_id not in self.procesando:
                self.procesando[habitacion_id] = []
            self.procesando[habitacion_id].append(request)
        
        print(f"📥 Solicitud agregada - Hab:{habitacion_id}, Prioridad:{request.prioridad}, Procesamiento en {self.TIEMPO_BATCHING}s")
        
        return request
    
    def _cerrar_conexion_vieja(self):
        """Cierra la conexión de base de datos si está inactiva"""
        try:
            if connection.connection is not None:
                if not connection.is_usable():
                    connection.close()
        except OperationalError:
            connection.close()
    
    def _procesar_cola(self):
        """Worker thread que procesa las reservas de la cola CON BATCHING"""
        while self.worker_activo:
            try:
                self._cerrar_conexion_vieja()
                
                # Obtener la reserva de mayor prioridad
                request = self.cola.get(timeout=1)
                
                # ⏱️ ESPERAR hasta el tiempo de procesamiento (batching)
                tiempo_actual = time.time()
                if tiempo_actual < request.tiempo_procesamiento:
                    tiempo_espera = request.tiempo_procesamiento - tiempo_actual
                    print(f"⏳ Esperando {tiempo_espera:.2f}s para procesar solicitud con prioridad {request.prioridad}")
                    time.sleep(tiempo_espera)
                
                # Procesar la reserva con análisis de conflictos
                self._procesar_reserva_inteligente(request)
                
                self.cola.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Error procesando reserva: {str(e)}")
                import traceback
                traceback.print_exc()
            finally:
                try:
                    connection.close()
                except:
                    pass
    
    def _procesar_reserva_inteligente(self, request):
        """
        Procesa solicitud verificando conflictos con solicitudes pendientes
        GANA la solicitud con MAYOR valor de prioridad
        """
        habitacion_id = request.habitacion_id
        
        try:
            self._cerrar_conexion_vieja()
            
            # 1️⃣ Obtener TODAS las solicitudes pendientes con conflicto de fechas
            solicitudes_conflictivas = []
            with self._lock:
                if habitacion_id in self.procesando:
                    for req in self.procesando[habitacion_id]:
                        if req != request and req.resultado is None:
                            if request.tiene_conflicto_fechas(req):
                                solicitudes_conflictivas.append(req)
            
            print(f"🔍 Procesando solicitud Prioridad:{request.prioridad} - {len(solicitudes_conflictivas)} conflictos encontrados")
            
            # 2️⃣ Verificar si es la de MAYOR prioridad
            es_mayor_prioridad = True
            solicitud_con_mayor_prioridad = None
            
            for req_conflictiva in solicitudes_conflictivas:
                if req_conflictiva.prioridad > request.prioridad:
                    es_mayor_prioridad = False
                    solicitud_con_mayor_prioridad = req_conflictiva
                    print(f"❌ Encontrada mayor prioridad: {req_conflictiva.prioridad} > {request.prioridad}")
                    break
                elif req_conflictiva.prioridad == request.prioridad:
                    if req_conflictiva.timestamp < request.timestamp:
                        es_mayor_prioridad = False
                        solicitud_con_mayor_prioridad = req_conflictiva
                        print(f"⚖️ Misma prioridad, gana por timestamp (FIFO)")
                        break
            
            # 3️⃣ Si NO es la de mayor prioridad, rechazar
            if not es_mayor_prioridad:
                request.resultado = {
                    'success': False,
                    'error': f'La habitacion no se encuentra disponible para las fechas solicitadas.',
                    'codigo': 'RECHAZADO_POR_PRIORIDAD',
                    'info_debug': {
                        'solicitudes_conflictivas': len(solicitudes_conflictivas),
                        'tu_prioridad': request.prioridad,
                        'prioridad_ganadora': solicitud_con_mayor_prioridad.prioridad if solicitud_con_mayor_prioridad else None,
                        'mensaje': f'Tu prioridad: {request.prioridad}. Otra solicitud tiene prioridad {solicitud_con_mayor_prioridad.prioridad if solicitud_con_mayor_prioridad else "N/A"}.'
                    }
                }
                print(f"🚫 La habitacion no se encuentra disponible para las fechas solicitadas.")
                request.evento.set()
                self._limpiar_request(habitacion_id, request)
                return
            
            # 4️⃣ Si ES la de mayor prioridad, intentar procesar
            print(f"✅ Solicitud tiene mayor prioridad, procesando...")
            
            with transaction.atomic():
                habitacion = Habitacion.objects.select_for_update().get(pk=habitacion_id)
                
                fecha_ini = request.datos_reserva['fecha_ini']
                fecha_fin = request.datos_reserva['fecha_fin']
                
                # Verificar conflictos con reservas CONFIRMADAS en BD
                conflictos_bd = ReservaHotel.objects.filter(
                    habitacion=habitacion,
                    estado__in=['A', 'ACTIVA', 'CONFIRMADA', 'P']
                ).filter(
                    fecha_ini__lt=request.fecha_fin_dt,
                    fecha_fin__gt=request.fecha_ini_dt
                ).exists()
                
                if conflictos_bd:
                    request.resultado = {
                        'success': False,
                        'error': 'La habitación ya tiene una reserva confirmada para esas fechas',
                        'codigo': 'HABITACION_RESERVADA'
                    }
                    print(f"⚠️ Conflicto con reserva existente en BD")
                else:
                    # ✅ CREAR LA RESERVA
                    reservas_gen = ReservasGen.objects.create(
                        tipo='H',
                        pago=None,
                        administrador=request.administrador,
                        empleado=request.empleado
                    )
                    
                    reserva = ReservaHotel.objects.create(
                        cant_personas=request.datos_reserva['cant_personas'],
                        amoblado=request.datos_reserva['amoblado'],
                        baño_priv=request.datos_reserva['baño_priv'],
                        fecha_ini=fecha_ini,
                        fecha_fin=fecha_fin,
                        estado=request.datos_reserva.get('estado', 'A'),
                        reservas_gen=reservas_gen,
                        datos_cliente=request.datos_cliente,
                        habitacion=habitacion
                    )
                    
                    habitacion.estado = 'OCUPADA'
                    habitacion.save()
                    
                    request.resultado = {
                        'success': True,
                        'reserva': reserva,
                        'reserva_gen': reservas_gen,
                        'habitacion': habitacion,
                        'datos_cliente': request.datos_cliente,
                        'info_competencia': {
                            'solicitudes_rechazadas': len(solicitudes_conflictivas),
                            'prioridad_ganadora': request.prioridad,
                            'mensaje': f'✅ Reserva aceptada por mayor prioridad (valor: {request.prioridad})'
                        }
                    }
                    
                    print(f"🎉 Reserva creada exitosamente - Prioridad: {request.prioridad}")
                    
                    # 5️⃣ Rechazar solicitudes conflictivas
                    self._rechazar_solicitudes_conflictivas_especificas(
                        habitacion_id, 
                        request.fecha_ini_dt, 
                        request.fecha_fin_dt, 
                        request
                    )
        
        except Exception as e:
            request.resultado = {
                'success': False,
                'error': f'Error al procesar la reserva: {str(e)}',
                'codigo': 'ERROR_PROCESAMIENTO'
            }
            print(f"💥 Error: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            request.evento.set()
            self._limpiar_request(habitacion_id, request)
            try:
                connection.close()
            except:
                pass
    
    def _rechazar_solicitudes_conflictivas_especificas(self, habitacion_id, fecha_ini, fecha_fin, request_aceptado):
        """Rechaza solicitudes con conflicto de fechas"""
        with self._lock:
            if habitacion_id in self.procesando:
                for req in self.procesando[habitacion_id]:
                    if req != request_aceptado and req.resultado is None:
                        if (req.fecha_ini_dt < fecha_fin and req.fecha_fin_dt > fecha_ini):
                            req.resultado = {
                                'success': False,
                                'error': f'La habitacion no se encuentra disponible para las fechas solicitadas.',
                                'codigo': 'RECHAZADO_POR_PRIORIDAD',
                                'detalle': {
                                    'prioridad_ganadora': request_aceptado.prioridad,
                                    'prioridad_perdedora': req.prioridad,
                                    'diferencia_prioridad': request_aceptado.prioridad - req.prioridad
                                }
                            }
                            print(f"🚫La habitacion no se encuentra disponible para las fechas solicitadas.")
                            req.evento.set()
    
    def _limpiar_request(self, habitacion_id, request):
        """Limpia un request de la lista de procesamiento"""
        with self._lock:
            if habitacion_id in self.procesando:
                if request in self.procesando[habitacion_id]:
                    self.procesando[habitacion_id].remove(request)
                if not self.procesando[habitacion_id]:
                    del self.procesando[habitacion_id]
    
    def detener(self):
        """Detiene el worker thread"""
        self.worker_activo = False
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
    
    def obtener_estadisticas(self):
        """Retorna estadísticas de la cola"""
        with self._lock:
            return {
                'tamaño_cola': self.cola.qsize(),
                'habitaciones_en_proceso': len(self.procesando),
                'total_solicitudes_pendientes': sum(len(reqs) for reqs in self.procesando.values()),
                'tiempo_batching': self.TIEMPO_BATCHING
            }


# Instancia global del gestor de cola
gestor_cola = ColaReservasHotel()