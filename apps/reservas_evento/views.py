from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from datetime import datetime
from django.db.models import Q
from .models import ReservasEvento
from apps.reservas_gen.models import ReservasGen
from apps.datos_cliente.models import DatosCliente
from apps.servicios_evento.models import ServiciosEvento
from apps.servicios_adicionales.models import ServiciosAdicionales
from apps.administrador.models import Administrador
from apps.empleado.models import Empleado
from .serializers import ReservasEventoSerializer, ServiciosAdicionalesSerializer
from .queue_manager import gestor_cola_eventos
from django.utils import timezone


# 🔹 Función auxiliar para verificar si hay conflicto de horarios
def verificar_disponibilidad_servicio(servicio_id, fecha, hora_ini, hora_fin, excluir_reserva_id=None):
    # Convertir strings a datetime si es necesario
    if isinstance(hora_ini, str):
        hora_ini = datetime.fromisoformat(hora_ini.replace('Z', '+00:00'))
    if isinstance(hora_fin, str):
        hora_fin = datetime.fromisoformat(hora_fin.replace('Z', '+00:00'))
    if isinstance(fecha, str):
        fecha = datetime.strptime(fecha, '%Y-%m-%d').date()

    # ⚡ Hacer aware si son naive
    if timezone.is_naive(hora_ini):
        hora_ini = timezone.make_aware(hora_ini, timezone.get_current_timezone())
    if timezone.is_naive(hora_fin):
        hora_fin = timezone.make_aware(hora_fin, timezone.get_current_timezone())

    # Buscar todas las reservas de este servicio en la misma fecha
    reservas_con_servicio = ServiciosEvento.objects.filter(
        servicios_adicionales_id=servicio_id,
        reservas_evento__fecha=fecha,
        reservas_evento__estado__in=['A', 'P']
    ).select_related('reservas_evento')

    if excluir_reserva_id:
        reservas_con_servicio = reservas_con_servicio.exclude(
            reservas_evento__id_reservas_evento=excluir_reserva_id
        )

    conflictos = []

    for servicio_evento in reservas_con_servicio:
        reserva = servicio_evento.reservas_evento

        # ⚡ Hacer aware de las horas de la BD si son naive (por si acaso)
        if timezone.is_naive(reserva.hora_ini):
            reserva.hora_ini = timezone.make_aware(reserva.hora_ini, timezone.get_current_timezone())
        if timezone.is_naive(reserva.hora_fin):
            reserva.hora_fin = timezone.make_aware(reserva.hora_fin, timezone.get_current_timezone())

        # Verificar solapamiento
        if hora_ini < reserva.hora_fin and hora_fin > reserva.hora_ini:
            conflictos.append({
                'id_reserva': reserva.id_reservas_evento,
                'hora_ini': reserva.hora_ini.isoformat(),
                'hora_fin': reserva.hora_fin.isoformat(),
                'fecha': str(reserva.fecha)
            })

    return {
        'disponible': len(conflictos) == 0,
        'conflictos': conflictos
    }


# 🔹 Obtener horarios ocupados de todos los servicios adicionales
@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_horarios_ocupados(request):
    """
    Retorna todos los horarios ocupados de cada servicio adicional.
    
    Query params opcionales:
    - servicio_id: Filtrar por un servicio específico
    - fecha_inicio: Filtrar desde una fecha (YYYY-MM-DD)
    - fecha_fin: Filtrar hasta una fecha (YYYY-MM-DD)
    
    Ejemplo: GET /api/horarios-ocupados/?servicio_id=1&fecha_inicio=2025-10-20
    """
    servicio_id = request.GET.get('servicio_id')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    
    # Construir filtros
    filtros = Q(reservas_evento__estado__in=['A', 'P'])
    
    if servicio_id:
        filtros &= Q(servicios_adicionales_id=servicio_id)
    
    if fecha_inicio:
        filtros &= Q(reservas_evento__fecha__gte=fecha_inicio)
    
    if fecha_fin:
        filtros &= Q(reservas_evento__fecha__lte=fecha_fin)
    
    # Obtener todas las reservas con servicios adicionales
    servicios_ocupados = ServiciosEvento.objects.filter(filtros).select_related(
        'servicios_adicionales',
        'reservas_evento'
    ).order_by('reservas_evento__fecha', 'reservas_evento__hora_ini')
    
    # Organizar datos por servicio
    resultado = {}
    
    for servicio_evento in servicios_ocupados:
        servicio = servicio_evento.servicios_adicionales
        reserva = servicio_evento.reservas_evento
        
        servicio_key = str(servicio.id_servicios_adicionales)
        
        if servicio_key not in resultado:
            resultado[servicio_key] = {
                'id_servicio': servicio.id_servicios_adicionales,
                'nombre_servicio': servicio.nombre,
                'horarios_ocupados': []
            }
        
        resultado[servicio_key]['horarios_ocupados'].append({
            'id_reserva': reserva.id_reservas_evento,
            'fecha': str(reserva.fecha),
            'hora_ini': reserva.hora_ini.isoformat(),
            'hora_fin': reserva.hora_fin.isoformat(),
            'cant_personas': reserva.cant_personas
        })
    
    return Response({
        'servicios': list(resultado.values())
    }, status=status.HTTP_200_OK)


# 🔹 Verificar disponibilidad de servicios antes de reservar
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def verificar_disponibilidad(request):
    """
    Verifica si uno o varios servicios están disponibles en la fecha/hora especificada.
    
    Body JSON:
    {
        "servicios_ids": [1, 2, 3],
        "fecha": "2025-10-25",
        "hora_ini": "2025-10-25T14:00:00",
        "hora_fin": "2025-10-25T18:00:00"
    }
    """
    data = request.data
    
    servicios_ids = data.get('servicios_ids', [])
    fecha = data.get('fecha')
    hora_ini = data.get('hora_ini')
    hora_fin = data.get('hora_fin')
    
    if not (fecha and hora_ini and hora_fin):
        return Response({
            'error': 'Faltan datos: fecha, hora_ini, hora_fin son requeridos'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not servicios_ids:
        return Response({
            'disponible': True,
            'mensaje': 'No se seleccionaron servicios adicionales'
        }, status=status.HTTP_200_OK)
    
    # Verificar cada servicio
    servicios_no_disponibles = []
    
    for servicio_id in servicios_ids:
        resultado = verificar_disponibilidad_servicio(
            servicio_id=servicio_id,
            fecha=fecha,
            hora_ini=hora_ini,
            hora_fin=hora_fin
        )
        
        if not resultado['disponible']:
            try:
                servicio = ServiciosAdicionales.objects.get(pk=servicio_id)
                servicios_no_disponibles.append({
                    'id_servicio': servicio_id,
                    'nombre_servicio': servicio.nombre,
                    'conflictos': resultado['conflictos']
                })
            except ServiciosAdicionales.DoesNotExist:
                pass
    
    if servicios_no_disponibles:
        return Response({
            'disponible': False,
            'mensaje': 'Algunos servicios no están disponibles en el horario seleccionado',
            'servicios_no_disponibles': servicios_no_disponibles
        }, status=status.HTTP_200_OK)
    
    return Response({
        'disponible': True,
        'mensaje': 'Todos los servicios están disponibles'
    }, status=status.HTTP_200_OK)


# 🔹 Registrar una reserva de evento CON SISTEMA DE COLA DE PRIORIDAD
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def registrar_reserva_evento(request):
    """
    Registra una reserva de evento usando el sistema de cola de prioridad.
    
    La prioridad se calcula según:
    - Cantidad de personas (mayor = más prioridad)
    - Duración del evento (mayor = más prioridad)
    - Cantidad de servicios adicionales (mayor = más prioridad)
    """
    import json
    data = request.data

    # --- 1️⃣ Validar y obtener/crear datos del cliente
    nombre = data.get('nombre')
    app_paterno = data.get('app_paterno')
    app_materno = data.get('app_materno')
    telefono = data.get('telefono')
    ci = data.get('ci')
    email = data.get('email')

    if not (nombre and telefono and ci and email):
        return Response({'error': 'Faltan datos del cliente'}, status=status.HTTP_400_BAD_REQUEST)

    cliente_existente = DatosCliente.objects.filter(
        nombre=nombre,
        app_paterno=app_paterno,
        app_materno=app_materno,
        telefono=telefono,
        ci=ci,
        email=email
    ).first()

    if cliente_existente:
        datos_cliente = cliente_existente
    else:
        datos_cliente = DatosCliente.objects.create(
            nombre=nombre,
            app_paterno=app_paterno,
            app_materno=app_materno,
            telefono=telefono,
            ci=ci,
            email=email
        )

    # --- 2️⃣ Validar datos del evento
    cant_personas = data.get('cant_personas')
    fecha = data.get('fecha')
    hora_ini = data.get('hora_ini')
    hora_fin = data.get('hora_fin')
    estado = data.get('estado', 'A')

    if not (cant_personas and fecha and hora_ini and hora_fin):
        return Response({'error': 'Faltan datos del evento'}, status=status.HTTP_400_BAD_REQUEST)

    # Validar formato de fechas
    try:
        fecha_dt = datetime.strptime(fecha, '%Y-%m-%d').date()
        hora_ini_dt = datetime.fromisoformat(hora_ini.replace('Z', '+00:00'))
        hora_fin_dt = datetime.fromisoformat(hora_fin.replace('Z', '+00:00'))
        
        # Validar que hora_fin sea posterior a hora_ini
        if hora_fin_dt <= hora_ini_dt:
            return Response({'error': 'La hora de fin debe ser posterior a la hora de inicio'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': f'Error al procesar fechas: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    # --- 3️⃣ Procesar servicios adicionales
    servicios_ids = data.get('servicios_adicionales', [])
    if isinstance(servicios_ids, str):
        try:
            servicios_ids = json.loads(servicios_ids)
        except Exception:
            servicios_ids = []

    # --- 4️⃣ Obtener empleado y administrador
    empleado = Empleado.objects.first()
    administrador = Administrador.objects.first()

    if not empleado or not administrador:
        return Response({
            'error': 'No existen registros de empleado o administrador en la base de datos'
        }, status=status.HTTP_400_BAD_REQUEST)

    # --- 5️⃣ Agregar la reserva a la cola de prioridad
    datos_evento = {
        'cant_personas': cant_personas,
        'fecha': fecha,
        'hora_ini': hora_ini,
        'hora_fin': hora_fin,
        'estado': estado
    }
    
    request_reserva = gestor_cola_eventos.agregar_reserva(
        datos_evento=datos_evento,
        datos_cliente=datos_cliente,
        servicios_ids=servicios_ids,
        empleado=empleado,
        administrador=administrador
    )
    
    # --- 6️⃣ Esperar el resultado (timeout de 10 segundos)
    procesado = request_reserva.evento.wait(timeout=10)
    
    if not procesado:
        return Response({
            'error': 'Timeout procesando la reserva. Intente nuevamente.'
        }, status=status.HTTP_408_REQUEST_TIMEOUT)
    
    # --- 7️⃣ Retornar el resultado
    resultado = request_reserva.resultado
    
    if resultado['success']:
        serializer = ReservasEventoSerializer(resultado['reserva'])
        
        # Calcular duración del evento
        duracion_horas = (hora_fin_dt - hora_ini_dt).total_seconds() / 3600
        
        return Response({
            'mensaje': 'Reserva de evento creada correctamente',
            'reserva': serializer.data,
            'cliente_id': resultado['datos_cliente'].id_datos_cliente,
            'reserva_gen_id': resultado['reserva_gen'].id_reservas_gen,
            'servicios_agregados': resultado['servicios_agregados'],
            'info_prioridad': {
                'duracion_horas': duracion_horas,
                'cant_personas': cant_personas,
                'cant_servicios': len(servicios_ids),
                'prioridad_calculada': request_reserva.prioridad,
                'mensaje_competencia': resultado.get('info_competencia', {}).get('mensaje', '')
            }
        }, status=status.HTTP_201_CREATED)
    else:
        status_code = status.HTTP_409_CONFLICT if resultado['codigo'] == 'RECHAZADO_POR_PRIORIDAD' else status.HTTP_400_BAD_REQUEST
        return Response({
            'error': resultado['error'],
            'codigo': resultado['codigo'],
            'info_debug': resultado.get('info_debug', {}),
            'detalle': resultado.get('detalle', {})
        }, status=status_code)


# 🔹 Obtener estadísticas de la cola de eventos
@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_estadisticas_cola(request):
    """
    Retorna estadísticas del sistema de cola de prioridad para eventos.
    
    Ejemplo: GET /api/eventos/estadisticas-cola/
    """
    estadisticas = gestor_cola_eventos.obtener_estadisticas()
    return Response(estadisticas, status=status.HTTP_200_OK)


# 🔹 Listar servicios adicionales activos (para los checkboxes)
@api_view(['GET'])
@permission_classes([AllowAny])
def listar_servicios_adicionales_evento(request):
    """
    Retorna todos los servicios adicionales activos (estado='A').
    Ejemplo: GET /api/servicios-adicionales/
    """
    servicios = ServiciosAdicionales.objects.filter(estado='A').values(
        'id_servicios_adicionales',
        'nombre',
        'descripcion',
        'precio',
        'tipo'
    )
    
    if not servicios:
        return Response(
            {'error': 'No existen servicios adicionales activos'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    return Response(list(servicios), status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def subir_comprobante(request, id_reserva_gen):
    """
    Permite subir un comprobante de pago (archivo binario) asociado a una reserva general.
    Espera un campo 'pago' en el formulario (multipart/form-data).
    """
    try:
        reserva_gen = ReservasGen.objects.get(pk=id_reserva_gen)
    except ReservasGen.DoesNotExist:
        return Response({'error': 'Reserva general no encontrada'}, status=status.HTTP_404_NOT_FOUND)
    
    archivo_pago = request.FILES.get('pago')
    if not archivo_pago:
        return Response({'error': 'No se envió ningún archivo'}, status=status.HTTP_400_BAD_REQUEST)
    
    reserva_gen.pago = archivo_pago.read()
    reserva_gen.save()
    
    return Response({
        'mensaje': 'Comprobante de pago subido correctamente',
        'reserva_gen_id': reserva_gen.id_reservas_gen
    }, status=status.HTTP_200_OK)