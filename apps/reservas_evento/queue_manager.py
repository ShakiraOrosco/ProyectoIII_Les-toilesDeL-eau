# ========================================
# ARCHIVO: apps/reservas_evento/queue_manager.py
# Sistema de Teoría de Colas con BATCHING para Reservas de Eventos
# ========================================
import threading
import queue
import time
from datetime import datetime
from django.db import transaction, connection
from django.db.utils import OperationalError
from django.utils import timezone
from .models import ReservasEvento
from apps.servicios_evento.models import ServiciosEvento
from apps.servicios_adicionales.models import ServiciosAdicionales
from apps.reservas_gen.models import ReservasGen

class EventoRequest:
    """Clase que representa una solicitud de reserva de evento en la cola"""
    
    def __init__(self, datos_evento, datos_cliente, servicios_ids, empleado, administrador):
        self.datos_evento = datos_evento
        self.datos_cliente = datos_cliente
        self.servicios_ids = servicios_ids
        self.empleado = empleado
        self.administrador = administrador
        self.prioridad = self.calcular_prioridad()
        self.timestamp = datetime.now()
        self.resultado = None
        self.evento = threading.Event()
        
        # Convertir fechas/horas a datetime aware
        self.fecha = self._convertir_fecha(datos_evento['fecha'])
        self.hora_ini = self._convertir_hora(datos_evento['hora_ini'])
        self.hora_fin = self._convertir_hora(datos_evento['hora_fin'])
    
    def _convertir_fecha(self, fecha):
        """Convierte string a date"""
        if isinstance(fecha, str):
            return datetime.strptime(fecha, '%Y-%m-%d').date()
        return fecha
    
    def _convertir_hora(self, hora):
        """Convierte string a datetime aware"""
        if isinstance(hora, str):
            hora_dt = datetime.fromisoformat(hora.replace('Z', '+00:00'))
        else:
            hora_dt = hora
        
        if timezone.is_naive(hora_dt):
            hora_dt = timezone.make_aware(hora_dt, timezone.get_current_timezone())
        
        return hora_dt
    
    def calcular_prioridad(self):
        """
        Calcula la prioridad según:
        1. Cantidad de personas (mayor = más prioridad)
        2. Duración del evento en horas (mayor = más prioridad)
        3. Cantidad de servicios adicionales (mayor = más prioridad)
        
        Valores MÁS ALTOS = MAYOR PRIORIDAD
        """
        cant_personas = self.datos_evento['cant_personas']
        
        # Calcular duración en horas
        hora_ini_temp = self._convertir_hora(self.datos_evento['hora_ini'])
        hora_fin_temp = self._convertir_hora(self.datos_evento['hora_fin'])
        duracion_horas = (hora_fin_temp - hora_ini_temp).total_seconds() / 3600
        
        cant_servicios = len(self.servicios_ids)
        
        # Fórmula de prioridad: personas * 100 + horas * 50 + servicios * 20
        prioridad = (cant_personas * 100) + (duracion_horas * 50) + (cant_servicios * 20)
        
        return prioridad
    
    def tiene_conflicto_servicios(self, otra_request):
        """
        Verifica si hay conflicto de servicios y horarios con otra solicitud
        """
        # Primero verificar si son el mismo día
        if self.fecha != otra_request.fecha:
            return False
        
        # Verificar si comparten servicios
        servicios_comunes = set(self.servicios_ids) & set(otra_request.servicios_ids)
        if not servicios_comunes:
            return False
        
        # Verificar solapamiento de horarios
        if self.hora_ini < otra_request.hora_fin and self.hora_fin > otra_request.hora_ini:
            return True
        
        return False
    
    def __lt__(self, other):
        """Comparador: Mayor prioridad = se procesa primero"""
        if self.prioridad != other.prioridad:
            return self.prioridad > other.prioridad
        return self.timestamp < other.timestamp


class ColaReservasEvento:
    """
    Gestor de cola de prioridad con BATCHING para eventos
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
        self.procesando = {}  # {fecha: [lista de requests]}
        self.worker_activo = True
        self.worker_thread = threading.Thread(target=self._procesar_cola, daemon=True)
        self.worker_thread.start()
        print(f"🔄 Cola de reservas de eventos iniciada con batching de {self.TIEMPO_BATCHING}s")
    
    def agregar_reserva(self, datos_evento, datos_cliente, servicios_ids, empleado, administrador):
        """
        Agrega una nueva solicitud de reserva de evento a la cola
        Returns:
            EventoRequest: objeto con el resultado de la reserva
        """
        request = EventoRequest(datos_evento, datos_cliente, servicios_ids, empleado, administrador)
        
        # Agregar marca de tiempo de procesamiento (ahora + tiempo de batching)
        request.tiempo_procesamiento = time.time() + self.TIEMPO_BATCHING
        
        self.cola.put(request)
        
        fecha_key = str(request.fecha)
        with self._lock:
            if fecha_key not in self.procesando:
                self.procesando[fecha_key] = []
            self.procesando[fecha_key].append(request)
        
        print(f"📥 Solicitud evento agregada - Fecha:{fecha_key}, Prioridad:{request.prioridad:.2f}, Procesamiento en {self.TIEMPO_BATCHING}s")
        
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
                request = self.cola.get(timeout=2)
                
                # ⏱️ ESPERAR hasta el tiempo de procesamiento (batching)
                tiempo_actual = time.time()
                if tiempo_actual < request.tiempo_procesamiento:
                    tiempo_espera = request.tiempo_procesamiento - tiempo_actual
                    print(f"⏳ Esperando {tiempo_espera:.2f}s para procesar solicitud con prioridad {request.prioridad:.2f}")
                    time.sleep(tiempo_espera)
                
                # Procesar la reserva con análisis de conflictos
                self._procesar_reserva_inteligente(request)
                
                self.cola.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Error procesando reserva de evento: {str(e)}")
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
        fecha_key = str(request.fecha)
        
        try:
            self._cerrar_conexion_vieja()
            
            # 1️⃣ Obtener TODAS las solicitudes pendientes con conflicto de servicios/horarios
            solicitudes_conflictivas = []
            with self._lock:
                if fecha_key in self.procesando:
                    for req in self.procesando[fecha_key]:
                        if req != request and req.resultado is None:
                            if request.tiene_conflicto_servicios(req):
                                solicitudes_conflictivas.append(req)
            
            print(f"🔍 Procesando solicitud Prioridad:{request.prioridad:.2f} - {len(solicitudes_conflictivas)} conflictos encontrados")
            
            # 2️⃣ Verificar si es la de MAYOR prioridad
            es_mayor_prioridad = True
            solicitud_con_mayor_prioridad = None
            
            for req_conflictiva in solicitudes_conflictivas:
                if req_conflictiva.prioridad > request.prioridad:
                    es_mayor_prioridad = False
                    solicitud_con_mayor_prioridad = req_conflictiva
                    print(f"❌ Encontrada mayor prioridad: {req_conflictiva.prioridad:.2f} > {request.prioridad:.2f}")
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
                    'error': f'Hay otra solicitud con mayor prioridad para estos servicios/horarios',
                    'codigo': 'RECHAZADO_POR_PRIORIDAD',
                    'info_debug': {
                        'solicitudes_conflictivas': len(solicitudes_conflictivas),
                        'tu_prioridad': request.prioridad,
                        'prioridad_ganadora': solicitud_con_mayor_prioridad.prioridad if solicitud_con_mayor_prioridad else None,
                        'mensaje': f'Tu prioridad: {request.prioridad:.2f}. Otra solicitud tiene prioridad {solicitud_con_mayor_prioridad.prioridad:.2f if solicitud_con_mayor_prioridad else "N/A"}.'
                    }
                }
                print(f"🚫 Solicitud rechazada - Prioridad insuficiente")
                request.evento.set()
                self._limpiar_request(fecha_key, request)
                return
            
            # 4️⃣ Si ES la de mayor prioridad, verificar disponibilidad en BD
            print(f"✅ Solicitud tiene mayor prioridad, verificando disponibilidad...")
            
            # Verificar disponibilidad de cada servicio en BD
            servicios_no_disponibles = []
            for servicio_id in request.servicios_ids:
                conflictos_bd = ServiciosEvento.objects.filter(
                    servicios_adicionales_id=servicio_id,
                    reservas_evento__fecha=request.fecha,
                    reservas_evento__estado__in=['A', 'P']
                ).filter(
                    reservas_evento__hora_ini__lt=request.hora_fin,
                    reservas_evento__hora_fin__gt=request.hora_ini
                ).exists()
                
                if conflictos_bd:
                    try:
                        servicio = ServiciosAdicionales.objects.get(pk=servicio_id)
                        servicios_no_disponibles.append({
                            'id_servicio': servicio_id,
                            'nombre_servicio': servicio.nombre
                        })
                    except ServiciosAdicionales.DoesNotExist:
                        pass
            
            if servicios_no_disponibles:
                request.resultado = {
                    'success': False,
                    'error': 'Algunos servicios ya están reservados en el horario solicitado',
                    'codigo': 'SERVICIOS_NO_DISPONIBLES',
                    'servicios_no_disponibles': servicios_no_disponibles
                }
                print(f"⚠️ Conflicto con reservas existentes en BD")
                request.evento.set()
                self._limpiar_request(fecha_key, request)
                return
            
            # 5️⃣ CREAR LA RESERVA
            with transaction.atomic():
                # Crear reserva general
                reservas_gen = ReservasGen.objects.create(
                    tipo='E',
                    pago=None,
                    administrador=request.administrador,
                    empleado=request.empleado
                )
                
                # Crear reserva de evento
                reserva_evento = ReservasEvento.objects.create(
                    cant_personas=request.datos_evento['cant_personas'],
                    hora_ini=request.hora_ini,
                    hora_fin=request.hora_fin,
                    fecha=request.fecha,
                    estado=request.datos_evento.get('estado', 'A'),
                    reservas_gen=reservas_gen,
                    datos_cliente=request.datos_cliente
                )
                
                # Agregar servicios adicionales
                servicios_agregados = []
                for servicio_id in request.servicios_ids:
                    servicio = ServiciosAdicionales.objects.filter(pk=servicio_id, estado='A').first()
                    if servicio:
                        ServiciosEvento.objects.create(
                            reservas_evento=reserva_evento,
                            servicios_adicionales=servicio
                        )
                        servicios_agregados.append({
                            'id': servicio.id_servicios_adicionales,
                            'nombre': servicio.nombre
                        })
                
                request.resultado = {
                    'success': True,
                    'reserva': reserva_evento,
                    'reserva_gen': reservas_gen,
                    'datos_cliente': request.datos_cliente,
                    'servicios_agregados': servicios_agregados,
                    'info_competencia': {
                        'solicitudes_rechazadas': len(solicitudes_conflictivas),
                        'prioridad_ganadora': request.prioridad,
                        'mensaje': f'✅ Reserva aceptada por mayor prioridad (valor: {request.prioridad:.2f})'
                    }
                }
                
                print(f"🎉 Reserva de evento creada exitosamente - Prioridad: {request.prioridad:.2f}")
                
                # 6️⃣ Rechazar solicitudes conflictivas
                self._rechazar_solicitudes_conflictivas(fecha_key, request)
        
        except Exception as e:
            request.resultado = {
                'success': False,
                'error': f'El servicio no esta disponible en este horario.',
                'codigo': 'ERROR_PROCESAMIENTO'
            }
            print(f"El servicio no esta disponible en este horario.")
            import traceback
            traceback.print_exc()
        
        finally:
            request.evento.set()
            self._limpiar_request(fecha_key, request)
            try:
                connection.close()
            except:
                pass
    
    def _rechazar_solicitudes_conflictivas(self, fecha_key, request_aceptado):
        """Rechaza solicitudes con conflicto de servicios/horarios"""
        with self._lock:
            if fecha_key in self.procesando:
                for req in self.procesando[fecha_key]:
                    if req != request_aceptado and req.resultado is None:
                        if request_aceptado.tiene_conflicto_servicios(req):
                            req.resultado = {
                                'success': False,
                                'error': f'El servicio no esta disponible en este horario.',
                                'codigo': 'RECHAZADO_POR_PRIORIDAD',
                                'detalle': {
                                    'prioridad_ganadora': request_aceptado.prioridad,
                                    'prioridad_perdedora': req.prioridad,
                                    'diferencia_prioridad': request_aceptado.prioridad - req.prioridad
                                }
                            }
                            print(f"🚫 El servicio no esta disponible en este horario.")
                            req.evento.set()
    
    def _limpiar_request(self, fecha_key, request):
        """Limpia un request de la lista de procesamiento"""
        with self._lock:
            if fecha_key in self.procesando:
                if request in self.procesando[fecha_key]:
                    self.procesando[fecha_key].remove(request)
                if not self.procesando[fecha_key]:
                    del self.procesando[fecha_key]
    
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
                'fechas_en_proceso': len(self.procesando),
                'total_solicitudes_pendientes': sum(len(reqs) for reqs in self.procesando.values()),
                'tiempo_batching': self.TIEMPO_BATCHING
            }


# Instancia global del gestor de cola
gestor_cola_eventos = ColaReservasEvento()