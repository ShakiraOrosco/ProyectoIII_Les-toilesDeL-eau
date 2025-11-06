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

from django.db import transaction
from django.utils import timezone
from apps.servicios_evento.models import ServiciosEvento

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

    # --- 2️⃣ Validar y convertir datos del evento
    cant_personas = data.get('cant_personas')
    fecha = data.get('fecha')
    hora_ini = data.get('hora_ini')
    hora_fin = data.get('hora_fin')
    estado = data.get('estado', 'A')

    if not (cant_personas and fecha and hora_ini and hora_fin):
        return Response({'error': 'Faltan datos del evento'}, status=status.HTTP_400_BAD_REQUEST)

    # 🔥 CONVERSIÓN EXPLÍCITA A ENTERO
    try:
        cant_personas = int(cant_personas)
    except (ValueError, TypeError):
        return Response({
            'error': f'La cantidad de personas debe ser un número válido, recibido: {cant_personas}'
        }, status=status.HTTP_400_BAD_REQUEST)

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
        'cant_personas': cant_personas,  # Ya convertido a int
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

# 🔹 ACTUALIZAR UNA RESERVA DE EVENTO (PUT)
@api_view(['PUT'])
@permission_classes([AllowAny])
@csrf_exempt
def actualizar_reserva_evento(request, id_reserva):
    """
    Actualiza una reserva de evento existente, crea nuevo cliente si no existe
    Ejemplo: PUT /api/eventos/reservas/1/actualizar/
    """
    try:
        with transaction.atomic():
            reserva = get_object_or_404(ReservasEvento.objects.select_related(
                'reservas_gen',
                'datos_cliente'
            ), pk=id_reserva)
            
            data = request.data
            campos_actualizados = []
            servicios_actualizados = False
            cliente_creado = False
            nuevo_cliente = None
            
            # --- 1️⃣ VERIFICAR SI SE QUIERE CAMBIAR A UN NUEVO CLIENTE (por CI)
            if 'ci' in data:
                nuevo_ci = int(data['ci'])
                
                # Buscar si ya existe un cliente con ese CI
                cliente_existente = DatosCliente.objects.filter(ci=nuevo_ci).first()
                
                if cliente_existente:
                    # Si existe, usar ese cliente
                    if cliente_existente.id_datos_cliente != reserva.datos_cliente.id_datos_cliente:
                        reserva.datos_cliente = cliente_existente
                        campos_actualizados.append('cliente_cambiado')
                        campos_actualizados.append('datos_cliente')
                else:
                    # Si NO existe, crear nuevo cliente
                    campos_requeridos = ['nombre', 'app_paterno', 'telefono', 'email']
                    campos_faltantes = [campo for campo in campos_requeridos if campo not in data]
                    
                    if campos_faltantes:
                        return Response({
                            'error': 'Para crear un nuevo cliente, se requieren todos los datos',
                            'campos_faltantes': campos_faltantes,
                            'campos_requeridos': campos_requeridos
                        }, status=400)
                    
                    # Crear nuevo cliente
                    nuevo_cliente = DatosCliente.objects.create(
                        nombre=data['nombre'],
                        app_paterno=data['app_paterno'],
                        app_materno=data.get('app_materno', ''),
                        telefono=int(data['telefono']),
                        ci=nuevo_ci,
                        email=data['email']
                    )
                    
                    reserva.datos_cliente = nuevo_cliente
                    cliente_creado = True
                    campos_actualizados.append('cliente_creado')
                    campos_actualizados.append('datos_cliente')
            
            # --- 2️⃣ ACTUALIZAR DATOS DEL CLIENTE ACTUAL SI NO SE CAMBIÓ
            if 'ci' not in data or ('ci' in data and not cliente_creado and 'cliente_cambiado' not in campos_actualizados):
                datos_cliente = reserva.datos_cliente
                campos_cliente = ['nombre', 'app_paterno', 'app_materno', 'telefono', 'email']
                campos_cliente_actualizados = []
                
                for campo in campos_cliente:
                    if campo in data:
                        valor_anterior = getattr(datos_cliente, campo)
                        valor_nuevo = data[campo]
                        
                        # Validaciones específicas
                        if campo == 'telefono':
                            if not isinstance(valor_nuevo, int) and not str(valor_nuevo).isdigit():
                                return Response({
                                    'error': 'El teléfono debe ser un número válido',
                                    'valor_recibido': valor_nuevo
                                }, status=400)
                            valor_nuevo = int(valor_nuevo)
                        
                        elif campo == 'email':
                            if '@' not in str(valor_nuevo):
                                return Response({
                                    'error': 'El formato del email no es válido',
                                    'valor_recibido': valor_nuevo
                                }, status=400)
                        
                        # Solo actualizar si el valor realmente cambió
                        if str(valor_anterior) != str(valor_nuevo):
                            setattr(datos_cliente, campo, valor_nuevo)
                            campos_cliente_actualizados.append(campo)
                
                if campos_cliente_actualizados:
                    datos_cliente.save()
                    campos_actualizados.append('datos_cliente')
                    if campos_cliente_actualizados:
                        campos_actualizados.extend([f'cliente_{campo}' for campo in campos_cliente_actualizados])
            
            # --- 3️⃣ CAMPOS BÁSICOS DE LA RESERVA DE EVENTO
            campos_basicos = ['cant_personas', 'estado', 'check_in', 'check_out', 'fecha', 'hora_ini', 'hora_fin']
            
            fecha_cambio = False
            hora_cambio = False
            
            for campo in campos_basicos:
                if campo in data:
                    # Validaciones específicas por campo
                    if campo == 'cant_personas':
                        if not isinstance(data[campo], int) or data[campo] <= 0:
                            return Response({
                                'error': 'La cantidad de personas debe ser un número positivo',
                                'valor_recibido': data[campo]
                            }, status=400)
                    
                    elif campo == 'fecha':
                        try:
                            fecha_validada = datetime.strptime(data[campo], '%Y-%m-%d').date()
                            fecha_cambio = True
                        except ValueError:
                            return Response({
                                'error': f'Formato de fecha inválido. Use YYYY-MM-DD',
                                'valor_recibido': data[campo]
                            }, status=400)
                    
                    elif campo in ['hora_ini', 'hora_fin']:
                        try:
                            hora_dt = datetime.fromisoformat(data[campo].replace('Z', '+00:00'))
                            if timezone.is_naive(hora_dt):
                                hora_dt = timezone.make_aware(hora_dt, timezone.get_current_timezone())
                            
                            hora_cambio = True
                            
                            # Validar que hora_fin sea posterior a hora_ini
                            if campo == 'hora_fin' and 'hora_ini' in data:
                                hora_ini_dt = datetime.fromisoformat(data['hora_ini'].replace('Z', '+00:00'))
                                if timezone.is_naive(hora_ini_dt):
                                    hora_ini_dt = timezone.make_aware(hora_ini_dt, timezone.get_current_timezone())
                                
                                if hora_dt <= hora_ini_dt:
                                    return Response({
                                        'error': 'La hora de fin debe ser posterior a la hora de inicio',
                                        'hora_inicio': data['hora_ini'],
                                        'hora_fin': data[campo]
                                    }, status=400)
                        except ValueError:
                            return Response({
                                'error': f'Formato de hora inválido para {campo}',
                                'valor_recibido': data[campo]
                            }, status=400)
                    
                    elif campo == 'estado':
                        if data[campo] not in ['A', 'C', 'F', 'P']:
                            return Response({
                                'error': 'Estado inválido. Use A (Activa), P (Pendiente), C (Cancelada) o F (Finalizada)',
                                'estados_permitidos': ['A', 'P', 'C', 'F'],
                                'valor_recibido': data[campo]
                            }, status=400)
                    
                    valor_anterior = getattr(reserva, campo)
                    setattr(reserva, campo, data[campo])
                    
                    if str(valor_anterior) != str(data[campo]):
                        campos_actualizados.append(campo)
            
            # --- 4️⃣ VERIFICAR DISPONIBILIDAD DE SERVICIOS SI CAMBIÓ FECHA/HORA
            if fecha_cambio or hora_cambio:
                # Obtener los servicios actuales de la reserva
                servicios_actuales = ServiciosEvento.objects.filter(
                    reservas_evento=reserva
                ).values_list('servicios_adicionales_id', flat=True)
                
                # Verificar disponibilidad con las nuevas fechas/horas
                fecha_verificar = data.get('fecha', reserva.fecha)
                hora_ini_verificar = data.get('hora_ini', reserva.hora_ini)
                hora_fin_verificar = data.get('hora_fin', reserva.hora_fin)
                
                servicios_conflicto = []
                
                for servicio_id in servicios_actuales:
                    disponibilidad = verificar_disponibilidad_servicio(
                        servicio_id=servicio_id,
                        fecha=fecha_verificar,
                        hora_ini=hora_ini_verificar,
                        hora_fin=hora_fin_verificar,
                        excluir_reserva_id=id_reserva
                    )
                    
                    if not disponibilidad['disponible']:
                        try:
                            servicio = ServiciosAdicionales.objects.get(pk=servicio_id)
                            servicios_conflicto.append({
                                'id': servicio_id,
                                'nombre': servicio.nombre,
                                'conflictos': disponibilidad['conflictos']
                            })
                        except ServiciosAdicionales.DoesNotExist:
                            pass
                
                if servicios_conflicto:
                    return Response({
                        'error': 'Los servicios adicionales no están disponibles en el nuevo horario',
                        'servicios_conflicto': servicios_conflicto,
                        'sugerencia': 'Cambie el horario o quite los servicios conflictivos'
                    }, status=status.HTTP_409_CONFLICT)
            
            # --- 5️⃣ ACTUALIZAR SERVICIOS ADICIONALES
            if 'servicios_adicionales' in data:
                import json
                servicios_ids = data['servicios_adicionales']
                
                if isinstance(servicios_ids, str):
                    try:
                        servicios_ids = json.loads(servicios_ids)
                    except:
                        servicios_ids = []
                
                # Obtener servicios actuales
                servicios_actuales = set(ServiciosEvento.objects.filter(
                    reservas_evento=reserva
                ).values_list('servicios_adicionales_id', flat=True))
                
                servicios_nuevos = set(servicios_ids)
                
                # Verificar disponibilidad de NUEVOS servicios
                servicios_agregar = servicios_nuevos - servicios_actuales
                
                if servicios_agregar:
                    servicios_no_disponibles = []
                    
                    for servicio_id in servicios_agregar:
                        disponibilidad = verificar_disponibilidad_servicio(
                            servicio_id=servicio_id,
                            fecha=reserva.fecha,
                            hora_ini=reserva.hora_ini,
                            hora_fin=reserva.hora_fin,
                            excluir_reserva_id=id_reserva
                        )
                        
                        if not disponibilidad['disponible']:
                            try:
                                servicio = ServiciosAdicionales.objects.get(pk=servicio_id)
                                servicios_no_disponibles.append({
                                    'id': servicio_id,
                                    'nombre': servicio.nombre,
                                    'conflictos': disponibilidad['conflictos']
                                })
                            except ServiciosAdicionales.DoesNotExist:
                                pass
                    
                    if servicios_no_disponibles:
                        return Response({
                            'error': 'Algunos servicios no están disponibles',
                            'servicios_no_disponibles': servicios_no_disponibles
                        }, status=status.HTTP_409_CONFLICT)
                
                # Eliminar servicios que ya no están
                servicios_eliminar = servicios_actuales - servicios_nuevos
                if servicios_eliminar:
                    ServiciosEvento.objects.filter(
                        reservas_evento=reserva,
                        servicios_adicionales_id__in=servicios_eliminar
                    ).delete()
                
                # Agregar nuevos servicios
                for servicio_id in servicios_agregar:
                    try:
                        servicio = ServiciosAdicionales.objects.get(pk=servicio_id)
                        ServiciosEvento.objects.create(
                            reservas_evento=reserva,
                            servicios_adicionales=servicio
                        )
                    except ServiciosAdicionales.DoesNotExist:
                        pass
                
                if servicios_agregar or servicios_eliminar:
                    servicios_actualizados = True
                    campos_actualizados.append('servicios_adicionales')
            
            # --- 6️⃣ VERIFICAR SI HAY CAMBIOS
            if not campos_actualizados and not servicios_actualizados:
                return Response({
                    'error': 'No se proporcionaron campos válidos para actualizar',
                    'campos_permitidos': {
                        'cliente': ['nombre', 'app_paterno', 'app_materno', 'telefono', 'ci', 'email'],
                        'evento': ['cant_personas', 'estado', 'check_in', 'check_out', 'fecha', 'hora_ini', 'hora_fin'],
                        'servicios': ['servicios_adicionales']
                    }
                }, status=400)
            
            reserva.save()
            
            # --- 7️⃣ PREPARAR RESPUESTA
            respuesta = {
                'mensaje': 'Reserva de evento actualizada correctamente',
                'reserva_id': reserva.id_reservas_evento,
                'campos_actualizados': campos_actualizados,
                'estado_actual': get_estado_display_evento(reserva.estado)
            }
            
            if cliente_creado:
                respuesta['cliente_creado'] = True
                respuesta['nuevo_cliente_id'] = nuevo_cliente.id_datos_cliente
                respuesta['cliente_info'] = {
                    'nombre_completo': f"{nuevo_cliente.nombre} {nuevo_cliente.app_paterno} {nuevo_cliente.app_materno or ''}".strip(),
                    'ci': nuevo_cliente.ci,
                    'email': nuevo_cliente.email
                }
                respuesta['mensaje_cliente'] = 'Nuevo cliente creado exitosamente'
            
            elif 'cliente_cambiado' in campos_actualizados:
                respuesta['cliente_cambiado'] = True
                respuesta['nuevo_cliente_id'] = reserva.datos_cliente.id_datos_cliente
                respuesta['mensaje_cliente'] = 'Cliente cambiado exitosamente'
            
            if servicios_actualizados:
                servicios_finales = list(ServiciosEvento.objects.filter(
                    reservas_evento=reserva
                ).select_related('servicios_adicionales').values(
                    'servicios_adicionales_id',
                    'servicios_adicionales__nombre',
                    'servicios_adicionales__precio'
                ))
                respuesta['servicios_actuales'] = servicios_finales
                respuesta['total_servicios'] = len(servicios_finales)
            
            return Response(respuesta, status=status.HTTP_200_OK)
        
    except ReservasEvento.DoesNotExist:
        return Response({
            'error': 'Reserva de evento no encontrada',
            'reserva_id': id_reserva
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al actualizar la reserva de evento: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🔹 ELIMINACIÓN LÓGICA - CANCELAR RESERVA DE EVENTO (DELETE)
@api_view(['DELETE'])
@permission_classes([AllowAny])
def eliminar_reserva_evento(request, id_reserva):
    """
    Cancela una reserva de evento (eliminación lógica)
    Ejemplo: DELETE /api/eventos/reservas/1/eliminar/
    """
    try:
        reserva = get_object_or_404(ReservasEvento, pk=id_reserva)
        
        # Verificar si ya está cancelada
        if reserva.estado == 'C':
            return Response({
                'error': 'La reserva de evento ya está cancelada'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar si ya está finalizada
        if reserva.estado == 'F':
            return Response({
                'error': 'No se puede cancelar una reserva ya finalizada'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Cambiar estado a Cancelada (ELIMINACIÓN LÓGICA)
        estado_anterior = reserva.estado
        reserva.estado = 'C'
        reserva.save()
        
        # Los servicios adicionales quedan liberados automáticamente
        # porque la verificación de disponibilidad excluye reservas canceladas
        
        return Response({
            'mensaje': 'Reserva de evento cancelada correctamente',
            'reserva_id': reserva.id_reservas_evento,
            'estado_anterior': get_estado_display_evento(estado_anterior),
            'estado_actual': 'Cancelada',
            'nota': 'Los servicios adicionales han sido liberados automáticamente'
        }, status=status.HTTP_200_OK)
        
    except ReservasEvento.DoesNotExist:
        return Response({
            'error': 'Reserva de evento no encontrada'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al cancelar la reserva de evento: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🔹 OBTENER TODAS LAS RESERVAS DE EVENTOS (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def lista_reservas_evento(request):
    """
    Retorna todas las reservas de eventos con información completa
    Ejemplo: GET /api/eventos/reservas/
    """
    try:
        reservas = ReservasEvento.objects.select_related(
            'datos_cliente',
            'reservas_gen',
            'reservas_gen__administrador',
            'reservas_gen__empleado'
        ).prefetch_related('serviciosevento_set__servicios_adicionales').all().order_by('-id_reservas_evento')
        
        data = []
        for reserva in reservas:
            # Datos del cliente
            cliente_data = {
                'id_datos_cliente': reserva.datos_cliente.id_datos_cliente,
                'nombre': reserva.datos_cliente.nombre,
                'app_paterno': reserva.datos_cliente.app_paterno,
                'app_materno': reserva.datos_cliente.app_materno or '',
                'telefono': reserva.datos_cliente.telefono,
                'ci': reserva.datos_cliente.ci,
                'email': reserva.datos_cliente.email
            }
            
            # Verificar si tiene pago (manejo correcto de BinaryField)
            tiene_pago = False
            if reserva.reservas_gen.pago is not None and len(reserva.reservas_gen.pago) > 0:
                tiene_pago = True
            
            # Datos de reserva general
            reserva_gen_data = {
                'id_reservas_gen': reserva.reservas_gen.id_reservas_gen,
                'tipo': reserva.reservas_gen.tipo,
                'tiene_pago': tiene_pago,
                'administrador_id': reserva.reservas_gen.administrador.id_admi,
                'empleado_id': reserva.reservas_gen.empleado.id_empleado
            }
            
            # Servicios adicionales
            servicios = []
            # IMPORTANTE: Cambiar servicioseventos_set a serviciosevento_set (sin la 's' duplicada)
            for servicio_evento in reserva.serviciosevento_set.all():
                servicios.append({
                    'id': servicio_evento.servicios_adicionales.id_servicios_adicionales,
                    'nombre': servicio_evento.servicios_adicionales.nombre,
                    'descripcion': servicio_evento.servicios_adicionales.descripcion,
                    'precio': float(servicio_evento.servicios_adicionales.precio)
                })
            
            # Calcular duración del evento
            duracion_horas = 0
            if reserva.hora_ini and reserva.hora_fin:
                duracion_horas = (reserva.hora_fin - reserva.hora_ini).total_seconds() / 3600
            
            # Datos completos de la reserva
            reserva_data = {
                'id_reservas_evento': reserva.id_reservas_evento,
                'cant_personas': reserva.cant_personas,
                'fecha': str(reserva.fecha),
                'hora_ini': reserva.hora_ini.isoformat() if reserva.hora_ini else None,
                'hora_fin': reserva.hora_fin.isoformat() if reserva.hora_fin else None,
                'duracion_horas': round(duracion_horas, 2),
                'estado': reserva.estado,
                'estado_display': get_estado_display_evento(reserva.estado),
                'check_in': reserva.check_in.isoformat() if reserva.check_in else None,
                'check_out': reserva.check_out.isoformat() if reserva.check_out else None,
                'datos_cliente': cliente_data,
                'reservas_gen': reserva_gen_data,
                'servicios_adicionales': servicios,
                'total_servicios': len(servicios)
            }
            
            data.append(reserva_data)
        
        return Response({
            'count': len(data),
            'reservas': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error al obtener las reservas de eventos: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
# 🔹 OBTENER UNA RESERVA DE EVENTO ESPECÍFICA (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def detalle_reserva_evento(request, id_reserva):
    """
    Retorna los detalles de una reserva de evento específica
    Ejemplo: GET /api/eventos/reservas/1/
    """
    try:
        reserva = get_object_or_404(ReservasEvento.objects.select_related(
            'datos_cliente',
            'reservas_gen'
        ).prefetch_related('serviciosevento_set__servicios_adicionales'), pk=id_reserva)
        
        # Datos del cliente
        cliente_data = {
            'id_datos_cliente': reserva.datos_cliente.id_datos_cliente,
            'nombre': reserva.datos_cliente.nombre,
            'app_paterno': reserva.datos_cliente.app_paterno,
            'app_materno': reserva.datos_cliente.app_materno or '',
            'telefono': reserva.datos_cliente.telefono,
            'ci': reserva.datos_cliente.ci,
            'email': reserva.datos_cliente.email
        }
        tiene_pago = False
        if reserva.reservas_gen.pago is not None and len(reserva.reservas_gen.pago) > 0:
            tiene_pago = True
        # Datos de reserva general
        reserva_gen_data = {
            'id_reservas_gen': reserva.reservas_gen.id_reservas_gen,
            'tipo': reserva.reservas_gen.tipo,
            # Por esto:
            'tiene_pago': tiene_pago,
            'administrador_id': reserva.reservas_gen.administrador.id_admi,
            'empleado_id': reserva.reservas_gen.empleado.id_empleado
        }
        
        # Servicios adicionales
        servicios = []
        total_precio_servicios = 0
        for servicio_evento in reserva.serviciosevento_set.all():
            precio = float(servicio_evento.servicios_adicionales.precio)
            total_precio_servicios += precio
            servicios.append({
                'id': servicio_evento.servicios_adicionales.id_servicios_adicionales,
                'nombre': servicio_evento.servicios_adicionales.nombre,
                'descripcion': servicio_evento.servicios_adicionales.descripcion,
                'precio': precio,
                'tipo': servicio_evento.servicios_adicionales.tipo
            })
        
        # Calcular duración del evento
        duracion_horas = 0
        if reserva.hora_ini and reserva.hora_fin:
            duracion_horas = (reserva.hora_fin - reserva.hora_ini).total_seconds() / 3600
        
        # Datos completos de la reserva
        reserva_data = {
            'id_reservas_evento': reserva.id_reservas_evento,
            'cant_personas': reserva.cant_personas,
            'fecha': reserva.fecha,
            'hora_ini': reserva.hora_ini.isoformat() if reserva.hora_ini else None,
            'hora_fin': reserva.hora_fin.isoformat() if reserva.hora_fin else None,
            'duracion_horas': round(duracion_horas, 2),
            'estado': reserva.estado,
            'estado_display': get_estado_display_evento(reserva.estado),
            'check_in': reserva.check_in,
            'check_out': reserva.check_out,
            'datos_cliente': cliente_data,
            'reservas_gen': reserva_gen_data,
            'servicios_adicionales': servicios,
            'total_servicios': len(servicios),
            'total_precio_servicios': round(total_precio_servicios, 2)
        }
        
        return Response(reserva_data, status=status.HTTP_200_OK)
        
    except ReservasEvento.DoesNotExist:
        return Response({
            'error': 'Reserva de evento no encontrada'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al obtener la reserva de evento: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🔹 OBTENER RESERVAS DE EVENTOS POR ESTADO (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def reservas_evento_por_estado(request, estado):
    """
    Retorna reservas de eventos filtradas por estado
    Ejemplo: GET /api/eventos/reservas/estado/A/
    Estados: A=Activa, P=Pendiente, C=Cancelada, F=Finalizada
    """
    try:
        # Validar estado
        estados_validos = ['A', 'P', 'C', 'F']
        if estado not in estados_validos:
            return Response({
                'error': f'Estado no válido. Estados permitidos: {estados_validos}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        reservas = ReservasEvento.objects.select_related(
            'datos_cliente'
        ).filter(estado=estado).order_by('-fecha', '-hora_ini')
        
        data = []
        for reserva in reservas:
            # Calcular duración
            duracion_horas = 0
            if reserva.hora_ini and reserva.hora_fin:
                duracion_horas = (reserva.hora_fin - reserva.hora_ini).total_seconds() / 3600
            
            reserva_data = {
                'id_reservas_evento': reserva.id_reservas_evento,
                'cant_personas': reserva.cant_personas,
                'fecha': reserva.fecha,
                'hora_ini': reserva.hora_ini.isoformat() if reserva.hora_ini else None,
                'hora_fin': reserva.hora_fin.isoformat() if reserva.hora_fin else None,
                'duracion_horas': round(duracion_horas, 2),
                'estado': reserva.estado,
                'estado_display': get_estado_display_evento(reserva.estado),
                'cliente': f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}",
                'cliente_email': reserva.datos_cliente.email
            }
            data.append(reserva_data)
        
        return Response({
            'count': len(data),
            'estado': estado,
            'estado_display': get_estado_display_evento(estado),
            'reservas': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error al obtener reservas por estado: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🔹 OBTENER RESERVAS DE EVENTOS POR CLIENTE (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def reservas_evento_por_cliente(request, cliente_id):
    """
    Retorna todas las reservas de eventos de un cliente específico
    Ejemplo: GET /api/eventos/reservas/cliente/1/
    """
    try:
        cliente = get_object_or_404(DatosCliente, pk=cliente_id)
        
        reservas = ReservasEvento.objects.filter(
            datos_cliente=cliente
        ).order_by('-fecha', '-hora_ini')
        
        data = []
        for reserva in reservas:
            # Calcular duración
            duracion_horas = 0
            if reserva.hora_ini and reserva.hora_fin:
                duracion_horas = (reserva.hora_fin - reserva.hora_ini).total_seconds() / 3600
            
            # Contar servicios
            total_servicios = ServiciosEvento.objects.filter(reservas_evento=reserva).count()
            
            reserva_data = {
                'id_reservas_evento': reserva.id_reservas_evento,
                'cant_personas': reserva.cant_personas,
                'fecha': reserva.fecha,
                'hora_ini': reserva.hora_ini.isoformat() if reserva.hora_ini else None,
                'hora_fin': reserva.hora_fin.isoformat() if reserva.hora_fin else None,
                'duracion_horas': round(duracion_horas, 2),
                'estado': reserva.estado,
                'estado_display': get_estado_display_evento(reserva.estado),
                'total_servicios': total_servicios,
                'check_in': reserva.check_in,
                'check_out': reserva.check_out
            }
            data.append(reserva_data)
        
        return Response({
            'cliente': {
                'id': cliente.id_datos_cliente,
                'nombre_completo': f"{cliente.nombre} {cliente.app_paterno} {cliente.app_materno or ''}".strip(),
                'telefono': cliente.telefono,
                'email': cliente.email,
                'ci': cliente.ci
            },
            'total_reservas': len(data),
            'reservas': data
        }, status=status.HTTP_200_OK)
        
    except DatosCliente.DoesNotExist:
        return Response({
            'error': 'Cliente no encontrado'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al obtener reservas del cliente: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==============================================
# 🔹 FUNCIONES AUXILIARES
# ==============================================

def get_estado_display_evento(estado):
    """Convierte código de estado a texto legible para eventos"""
    estados = {
        'A': 'Activa',
        'P': 'Pendiente',
        'C': 'Cancelada', 
        'F': 'Finalizada'
    }
    return estados.get(estado, 'Desconocido')