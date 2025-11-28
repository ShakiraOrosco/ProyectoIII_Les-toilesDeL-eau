from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime, date
import re

from .models import ReservaHotel
from .seliralizers import ReservaHotelSerializer
from apps.datos_cliente.models import DatosCliente
from apps.habitacion.models import Habitacion
from apps.reservas_gen.models import ReservasGen
from apps.administrador.models import Administrador
from apps.empleado.models import Empleado
from apps.tarifa_hotel.models import TarifaHotel
from .queue_manager import gestor_cola

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q

from .models import ReservaHotel
from .seliralizers import ReservaHotelSerializer
from apps.datos_cliente.models import DatosCliente
from apps.habitacion.models import Habitacion
from apps.reservas_gen.models import ReservasGen
from apps.administrador.models import Administrador
from apps.empleado.models import Empleado
from apps.tarifa_hotel.models import TarifaHotel
from .queue_manager import gestor_cola

# 🔹 Registrar una reserva de hotel
@api_view(['POST'])
@permission_classes([AllowAny])
def registrar_reserva_hotel(request):
    """
    Registra una reserva usando el sistema de cola de prioridad
    """
    data = request.data
    
    # --- 1️⃣ Validar y obtener/crear datos del cliente
    nombre = data.get('nombre')
    app_paterno = data.get('app_paterno')
    app_materno = data.get('app_materno')
    telefono = data.get('telefono')
    ci = data.get('ci')
    email = data.get('email')
    
    if not (nombre and app_paterno and telefono and ci and email):
        return Response({'error': 'Faltan datos del cliente'}, status=400)
    
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
    
    # --- 2️⃣ Validar datos de la reserva
    cant_personas = data.get('cant_personas')
    amoblado = data.get('amoblado', 'N').upper()
    baño_priv = data.get('baño_priv', 'N').upper()
    fecha_ini = data.get('fecha_ini')
    fecha_fin = data.get('fecha_fin')
    estado = data.get('estado', 'A')
    
    if not (cant_personas and fecha_ini and fecha_fin):
        return Response({'error': 'Faltan datos de la reserva'}, status=400)
    
    # Validar formato de fechas
    try:
        from datetime import datetime
        fecha_ini_dt = datetime.strptime(fecha_ini, '%Y-%m-%d').date()
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        # Validar que fecha_fin sea posterior a fecha_ini
        if fecha_fin_dt <= fecha_ini_dt:
            return Response({'error': 'La fecha de fin debe ser posterior a la fecha de inicio'}, status=400)
            
    except ValueError:
        return Response({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}, status=400)
    
    # --- 3️⃣ Buscar habitación disponible SIN conflictos de fechas
    # Primero, obtener todas las habitaciones con las características solicitadas
    habitaciones_candidatas = Habitacion.objects.filter(
        ~Q(estado='MANTENIMIENTO'),   # cualquier estado menos mantenimiento
        amoblado=amoblado,
        baño_priv=baño_priv,
    )

    
    if not habitaciones_candidatas.exists():
        return Response({
            'error': 'No hay habitaciones disponibles con esas características'
        }, status=404)
    
    # Buscar una habitación sin conflictos de fechas
    habitacion = None
    for hab in habitaciones_candidatas:
        # Verificar si hay reservas que se solapen con las fechas solicitadas
        reservas_conflicto = ReservaHotel.objects.filter(
            habitacion=hab,
            estado__in=['A', 'P']  # Activas o Pendientes
        ).filter(
            # Condición de solapamiento de fechas:
            # Una reserva se solapa si:
            # - Su fecha_ini está entre nuestras fechas O
            # - Su fecha_fin está entre nuestras fechas O
            # - Nuestras fechas están completamente contenidas en la reserva existente
            Q(fecha_ini__lt=fecha_fin_dt, fecha_fin__gt=fecha_ini_dt)
        )
        
        if not reservas_conflicto.exists():
            habitacion = hab
            break
    
    if not habitacion:
        return Response({
            'error': 'No hay habitaciones disponibles con esas características en las fechas seleccionadas',
            'detalle': 'Todas las habitaciones que cumplen con los requisitos ya están reservadas en ese período'
        }, status=404)
    
    # --- 4️⃣ Obtener empleado y administrador
    empleado = Empleado.objects.first()
    administrador = Administrador.objects.first()
    
    if not empleado or not administrador:
        return Response({
            'error': 'No existen registros de empleado o administrador'
        }, status=400)
    
    # --- 5️⃣ Agregar la reserva a la cola de prioridad
    datos_reserva = {
        'cant_personas': cant_personas,
        'amoblado': amoblado,
        'baño_priv': baño_priv,
        'fecha_ini': fecha_ini,
        'fecha_fin': fecha_fin,
        'estado': estado
    }
    
    request_reserva = gestor_cola.agregar_reserva(
        datos_reserva=datos_reserva,
        datos_cliente=datos_cliente,
        habitacion_id=habitacion.id_habitacion,
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
        serializer = ReservaHotelSerializer(resultado['reserva'])
        return Response({
            'mensaje': 'Reserva creada correctamente',
            'reserva': serializer.data,
            'cliente_id': resultado['datos_cliente'].id_datos_cliente,
            'habitacion_id': resultado['habitacion'].id_habitacion,
            'reserva_gen_id': resultado['reserva_gen'].id_reservas_gen,
            'info_prioridad': {
                'duracion_dias': (fecha_fin_dt - fecha_ini_dt).days,
                'cant_personas': cant_personas,
                'prioridad_calculada': request_reserva.prioridad
            }
        }, status=status.HTTP_201_CREATED)
    else:
        status_code = status.HTTP_409_CONFLICT if resultado['codigo'] == 'RECHAZADO_POR_PRIORIDAD' else status.HTTP_400_BAD_REQUEST
        return Response({
            'error': resultado['error'],
            'codigo': resultado['codigo']
        }, status=status_code)




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

    # Verificamos si se envió el archivo
    archivo_pago = request.FILES.get('pago')
    if not archivo_pago:
        return Response({'error': 'No se envió ningún archivo'}, status=status.HTTP_400_BAD_REQUEST)

    # Leemos el contenido binario del archivo
    reserva_gen.pago = archivo_pago.read()
    reserva_gen.save()

    return Response({
        'mensaje': 'Comprobante de pago subido correctamente',
        'reserva_gen_id': reserva_gen.id_reservas_gen
    }, status=status.HTTP_200_OK)


#-- 🔹 Obtener tarifa de hotel según amoblado y baño privado
@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_tarifa_hotel(request):
    """
    Retorna todas las tarifas del hotel.
    Ejemplo: GET /api/reservaHotel/tarifa/
    """
    tarifas = TarifaHotel.objects.all().values(
        'id_tarifa_hotel',
        'nombre',
        'descripcion',
        'amoblado',
        'baño_priv',
        'precio_persona'
    )

    if not tarifas:
        return Response({'error': 'No existen tarifas registradas'}, status=status.HTTP_404_NOT_FOUND)

    return Response(list(tarifas), status=status.HTTP_200_OK)

# ==============================================
# 🔹 NUEVAS FUNCIONES GET, PUT, DELETE
# ==============================================

# 🔹 OBTENER TODAS LAS RESERVAS (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def lista_reservas_hotel(request):
    """
    Retorna todas las reservas de hotel con información completa
    Ejemplo: GET /api/reservaHotel/reservas/
    """
    try:
        reservas = ReservaHotel.objects.select_related(
            'datos_cliente',
            'habitacion',
            'reservas_gen'
        ).all().order_by('-id_reserva_hotel')  # Ordenar por ID descendente
        
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
            
            # Datos de la habitación
            habitacion_data = {
                'id_habitacion': reserva.habitacion.id_habitacion,
                'numero': reserva.habitacion.numero,
                'piso': reserva.habitacion.piso,
                'tipo': reserva.habitacion.tipo,
                'amoblado': reserva.habitacion.amoblado,
                'baño_priv': reserva.habitacion.baño_priv,
                'estado': reserva.habitacion.estado
            }
            
            # Datos de reserva general
            reserva_gen_data = {
                'id_reservas_gen': reserva.reservas_gen.id_reservas_gen,
                'tipo': reserva.reservas_gen.tipo,
                'tiene_pago': bool(reserva.reservas_gen.pago),
                'administrador_id': reserva.reservas_gen.administrador.id_admi,  # ✅ CORRECTO - usa id_admi
                'empleado_id': reserva.reservas_gen.empleado.id_empleado  # ✅ Esto depende de cómo se llame en Empleado
            }
            
            # Calcular días de estadía
            dias_estadia = 0
            if reserva.fecha_ini and reserva.fecha_fin:
                dias_estadia = (reserva.fecha_fin - reserva.fecha_ini).days
                if dias_estadia < 0:
                    dias_estadia = 0
            
            # Datos completos de la reserva
            reserva_data = {
                'id_reserva_hotel': reserva.id_reserva_hotel,
                'cant_personas': reserva.cant_personas,
                'amoblado': reserva.amoblado,
                'baño_priv': reserva.baño_priv,
                'fecha_ini': reserva.fecha_ini,
                'fecha_fin': reserva.fecha_fin,
                'dias_estadia': dias_estadia,
                'estado': reserva.estado,
                'estado_display': get_estado_display(reserva.estado),
                'check_in': reserva.check_in,
                'check_out': reserva.check_out,
                'datos_cliente': cliente_data,
                'habitacion': habitacion_data,
                'reservas_gen': reserva_gen_data,
                'fecha_creacion': reserva.reservas_gen.id_reservas_gen  # Como referencia temporal
            }
            
            data.append(reserva_data)
        
        return Response({
            'count': len(data),
            'reservas': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error al obtener las reservas: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 🔹 OBTENER UNA RESERVA ESPECÍFICA (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def detalle_reserva_hotel(request, id_reserva):
    """
    Retorna los detalles de una reserva específica
    Ejemplo: GET /api/reservaHotel/reservas/1/
    """
    try:
        reserva = get_object_or_404(ReservaHotel.objects.select_related(
            'datos_cliente',
            'habitacion',
            'reservas_gen'
        ), pk=id_reserva)
        
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
        
        # Datos de la habitación
        habitacion_data = {
            'id_habitacion': reserva.habitacion.id_habitacion,
            'numero': reserva.habitacion.numero,
            'piso': reserva.habitacion.piso,
            'tipo': reserva.habitacion.tipo,
            'amoblado': reserva.habitacion.amoblado,
            'baño_priv': reserva.habitacion.baño_priv,
            'estado': reserva.habitacion.estado
        }
        
        # Datos de reserva general
        reserva_gen_data = {
            'id_reservas_gen': reserva.reservas_gen.id_reservas_gen,
            'tipo': reserva.reservas_gen.tipo,
            'tiene_pago': bool(reserva.reservas_gen.pago),
            'administrador': reserva.reservas_gen.administrador.id_admi,
            'empleado_id': reserva.reservas_gen.empleado.id_empleado
        }
        
        # Calcular días de estadía
        dias_estadia = 0
        if reserva.fecha_ini and reserva.fecha_fin:
            dias_estadia = (reserva.fecha_fin - reserva.fecha_ini).days
            if dias_estadia < 0:
                dias_estadia = 0
        
        # Datos completos de la reserva
        reserva_data = {
            'id_reserva_hotel': reserva.id_reserva_hotel,
            'cant_personas': reserva.cant_personas,
            'amoblado': reserva.amoblado,
            'baño_priv': reserva.baño_priv,
            'fecha_ini': reserva.fecha_ini,
            'fecha_fin': reserva.fecha_fin,
            'dias_estadia': dias_estadia,
            'estado': reserva.estado,
            'estado_display': get_estado_display(reserva.estado),
            'check_in': reserva.check_in,
            'check_out': reserva.check_out,
            'datos_cliente': cliente_data,
            'habitacion': habitacion_data,
            'reservas_gen': reserva_gen_data
        }
        
        return Response(reserva_data, status=status.HTTP_200_OK)
        
    except ReservaHotel.DoesNotExist:
        return Response({
            'error': 'Reserva no encontrada'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al obtener la reserva: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 🔹 ACTUALIZAR UNA RESERVA (PUT) - CREA NUEVO CLIENTE SI NO EXISTE
# 🔹 ACTUALIZAR UNA RESERVA (PUT) - CON LÓGICA DE CONFLICTO DE FECHAS
@api_view(['PUT'])
@permission_classes([AllowAny])
@csrf_exempt
def actualizar_reserva_hotel(request, id_reserva):
    """
    Actualiza una reserva existente, crea nuevo cliente si no existe.
    Busca habitaciones que NO estén en MANTENIMIENTO y que NO tengan conflictos de fechas.
    Ejemplo: PUT /api/reservaHotel/reservas/1/actualizar/
    """
    try:
        with transaction.atomic():
            reserva = get_object_or_404(ReservaHotel.objects.select_related(
                'habitacion',
                'reservas_gen',
                'datos_cliente'
            ), pk=id_reserva)
            
            data = request.data
            campos_actualizados = []
            habitacion_cambiada = False
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
            
            # --- 3️⃣ OBTENER Y VALIDAR FECHAS (necesarias para verificar conflictos)
            fecha_ini_str = data.get('fecha_ini', str(reserva.fecha_ini))
            fecha_fin_str = data.get('fecha_fin', str(reserva.fecha_fin))
            
            try:
                fecha_ini_dt = datetime.strptime(fecha_ini_str, '%Y-%m-%d').date()
                fecha_fin_dt = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
                
                # Validar que fecha_fin sea posterior a fecha_ini
                if fecha_fin_dt <= fecha_ini_dt:
                    return Response({
                        'error': 'La fecha de fin debe ser posterior a la fecha de inicio',
                        'fecha_inicio': fecha_ini_str,
                        'fecha_fin': fecha_fin_str
                    }, status=400)
            except ValueError:
                return Response({
                    'error': 'Formato de fecha inválido. Use YYYY-MM-DD',
                    'valor_recibido': {'fecha_ini': fecha_ini_str, 'fecha_fin': fecha_fin_str}
                }, status=400)
            
            # --- 4️⃣ CAMPOS BÁSICOS DE LA RESERVA (excepto fechas, se manejan después)
            campos_basicos = ['cant_personas', 'estado', 'check_in', 'check_out']
            
            for campo in campos_basicos:
                if campo in data:
                    # Validaciones específicas por campo
                    if campo == 'cant_personas':
                        if not isinstance(data[campo], int) or data[campo] <= 0:
                            return Response({
                                'error': 'La cantidad de personas debe ser un número positivo',
                                'valor_recibido': data[campo]
                            }, status=400)
                    
                    elif campo == 'estado':
                        if data[campo] not in ['A', 'C', 'F']:
                            return Response({
                                'error': 'Estado inválido. Use A (Activa), C (Cancelada) o F (Finalizada)',
                                'estados_permitidos': ['A', 'C', 'F'],
                                'valor_recibido': data[campo]
                            }, status=400)
                        
                        # Si cambia de Cancelada a Activa, verificar conflictos
                        if data[campo] == 'A' and reserva.estado == 'C':
                            # Verificar conflictos de fechas antes de reactivar
                            reservas_conflicto = ReservaHotel.objects.filter(
                                habitacion=reserva.habitacion,
                                estado__in=['A', 'P']
                            ).exclude(
                                id_reserva_hotel=reserva.id_reserva_hotel
                            ).filter(
                                Q(fecha_ini__lt=fecha_fin_dt, fecha_fin__gt=fecha_ini_dt)
                            )
                            
                            if reservas_conflicto.exists():
                                return Response({
                                    'error': 'No se puede reactivar la reserva porque la habitación tiene conflictos de fechas con otras reservas',
                                    'habitacion_id': reserva.habitacion.id_habitacion,
                                    'reservas_conflicto': reservas_conflicto.count()
                                }, status=400)
                    
                    valor_anterior = getattr(reserva, campo)
                    setattr(reserva, campo, data[campo])
                    
                    if str(valor_anterior) != str(data[campo]):
                        campos_actualizados.append(campo)
            
            # --- 5️⃣ VERIFICAR SI CAMBIAN CARACTERÍSTICAS O FECHAS DE HABITACIÓN
            amoblado_actual = data.get('amoblado', reserva.amoblado).upper()
            baño_priv_actual = data.get('baño_priv', reserva.baño_priv).upper()
            
            caracteristicas_cambiaron = (amoblado_actual != reserva.amoblado or 
                                       baño_priv_actual != reserva.baño_priv)
            
            fechas_cambiaron = (fecha_ini_dt != reserva.fecha_ini or 
                              fecha_fin_dt != reserva.fecha_fin)
            
            # Si cambiaron características O fechas, buscar nueva habitación
            if caracteristicas_cambiaron or fechas_cambiaron:
                habitacion_anterior = reserva.habitacion
                
                # --- BUSCAR HABITACIÓN SIN CONFLICTOS (IGUAL QUE EN REGISTRAR) ---
                
                # Obtener todas las habitaciones candidatas (NO en mantenimiento)
                habitaciones_candidatas = Habitacion.objects.filter(
                    ~Q(estado='MANTENIMIENTO'),
                    amoblado=amoblado_actual,
                    baño_priv=baño_priv_actual,
                )
                
                if not habitaciones_candidatas.exists():
                    return Response({
                        'error': 'No hay habitaciones disponibles con esas características',
                        'caracteristicas_solicitadas': {
                            'amoblado': amoblado_actual,
                            'baño_priv': baño_priv_actual
                        }
                    }, status=404)
                
                # Buscar una habitación sin conflictos de fechas
                habitacion_nueva = None
                for hab in habitaciones_candidatas:
                    # Verificar si hay reservas que se solapen con las fechas solicitadas
                    # IMPORTANTE: Excluir la reserva actual de la búsqueda
                    reservas_conflicto = ReservaHotel.objects.filter(
                        habitacion=hab,
                        estado__in=['A', 'P']  # Activas o Pendientes
                    ).exclude(
                        id_reserva_hotel=reserva.id_reserva_hotel  # ✅ EXCLUIR RESERVA ACTUAL
                    ).filter(
                        # Condición de solapamiento de fechas
                        Q(fecha_ini__lt=fecha_fin_dt, fecha_fin__gt=fecha_ini_dt)
                    )
                    
                    if not reservas_conflicto.exists():
                        habitacion_nueva = hab
                        break
                
                if not habitacion_nueva:
                    return Response({
                        'error': 'No hay habitaciones disponibles con esas características en las fechas seleccionadas',
                        'detalle': 'Todas las habitaciones que cumplen con los requisitos ya están reservadas en ese período',
                        'caracteristicas_solicitadas': {
                            'amoblado': amoblado_actual,
                            'baño_priv': baño_priv_actual
                        },
                        'fechas_solicitadas': {
                            'fecha_ini': fecha_ini_str,
                            'fecha_fin': fecha_fin_str
                        }
                    }, status=404)
                
                # --- ACTUALIZAR HABITACIÓN ---
                
                # Si la habitación cambió, marcar el cambio
                if habitacion_nueva.id_habitacion != habitacion_anterior.id_habitacion:
                    habitacion_cambiada = True
                    campos_actualizados.append('habitacion')
                
                reserva.habitacion = habitacion_nueva
                reserva.amoblado = amoblado_actual
                reserva.baño_priv = baño_priv_actual
                
                if caracteristicas_cambiaron:
                    campos_actualizados.extend(['amoblado', 'baño_priv'])
            
            # --- 6️⃣ ACTUALIZAR FECHAS SI CAMBIARON
            if fechas_cambiaron:
                reserva.fecha_ini = fecha_ini_dt
                reserva.fecha_fin = fecha_fin_dt
                campos_actualizados.extend(['fecha_ini', 'fecha_fin'])
            
            # --- 7️⃣ VERIFICAR SI HAY CAMBIOS
            if not campos_actualizados and not habitacion_cambiada:
                return Response({
                    'error': 'No se proporcionaron campos válidos para actualizar',
                    'campos_permitidos': {
                        'cliente': ['nombre', 'app_paterno', 'app_materno', 'telefono', 'ci', 'email'],
                        'reserva': ['cant_personas', 'estado', 'check_in', 'check_out', 'fecha_ini', 'fecha_fin'],
                        'habitacion': ['amoblado', 'baño_priv']
                    }
                }, status=400)
            
            reserva.save()
            
            # --- 8️⃣ PREPARAR RESPUESTA
            respuesta = {
                'mensaje': 'Reserva actualizada correctamente',
                'reserva_id': reserva.id_reserva_hotel,
                'campos_actualizados': campos_actualizados,
                'estado_actual': get_estado_display(reserva.estado)
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
            
            if habitacion_cambiada:
                respuesta['habitacion_anterior'] = habitacion_anterior.id_habitacion
                respuesta['habitacion_nueva'] = reserva.habitacion.id_habitacion
                respuesta['mensaje_habitacion'] = 'Habitación cambiada exitosamente debido a cambio de características o fechas'
            
            if fechas_cambiaron:
                respuesta['fechas_actualizadas'] = {
                    'fecha_ini': str(reserva.fecha_ini),
                    'fecha_fin': str(reserva.fecha_fin),
                    'dias_estadia': (reserva.fecha_fin - reserva.fecha_ini).days
                }
            
            return Response(respuesta, status=status.HTTP_200_OK)
        
    except ReservaHotel.DoesNotExist:
        return Response({
            'error': 'Reserva no encontrada',
            'reserva_id': id_reserva
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al actualizar la reserva: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)   
     
# 🔹 ELIMINACIÓN LÓGICA - CANCELAR RESERVA (DELETE)
@api_view(['DELETE'])
@permission_classes([AllowAny])
def eliminar_reserva_hotel(request, id_reserva):
    try:
        reserva = get_object_or_404(ReservaHotel.objects.select_related(
            'habitacion'
        ), pk=id_reserva)
        
        # Verificar si ya está cancelada
        if reserva.estado == 'C':
            return Response({
                'error': 'La reserva ya está cancelada'
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
        
        # Liberar la habitación
        #habitacion = reserva.habitacion
        #habitacion.estado = 'DISPONIBLE'
        #habitacion.save()
        
        return Response({
            'mensaje': 'Reserva cancelada correctamente',
            'reserva_id': reserva.id_reserva_hotel,
            'estado_anterior': get_estado_display(estado_anterior),
            'estado_actual': 'Cancelada',
            #'habitacion_liberada': habitacion.id_habitacion,
            'habitacion_estado': 'DISPONIBLE'
        }, status=status.HTTP_200_OK)
        
    except ReservaHotel.DoesNotExist:
        return Response({
            'error': 'Reserva no encontrada'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al cancelar la reserva: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 🔹 OBTENER RESERVAS POR ESTADO (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def reservas_por_estado(request, estado):
    """
    Retorna reservas filtradas por estado
    Ejemplo: GET /api/reservaHotel/reservas/estado/A/
    Estados: A=Activa, C=Cancelada, F=Finalizada
    """
    try:
        # Validar estado
        estados_validos = ['A', 'C', 'F']
        if estado not in estados_validos:
            return Response({
                'error': f'Estado no válido. Estados permitidos: {estados_validos}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        reservas = ReservaHotel.objects.select_related(
            'datos_cliente',
            'habitacion',
            'reservas_gen'
        ).filter(estado=estado).order_by('-fecha_ini')
        
        data = []
        for reserva in reservas:
            # Calcular días de estadía
            dias_estadia = 0
            if reserva.fecha_ini and reserva.fecha_fin:
                dias_estadia = (reserva.fecha_fin - reserva.fecha_ini).days
                if dias_estadia < 0:
                    dias_estadia = 0
            
            reserva_data = {
                'id_reserva_hotel': reserva.id_reserva_hotel,
                'cant_personas': reserva.cant_personas,
                'fecha_ini': reserva.fecha_ini,
                'fecha_fin': reserva.fecha_fin,
                'dias_estadia': dias_estadia,
                'estado': reserva.estado,
                'estado_display': get_estado_display(reserva.estado),
                'cliente': f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}",
                'cliente_email': reserva.datos_cliente.email,
                'habitacion': reserva.habitacion.numero,
                'tipo_habitacion': f"{'Amoblado' if reserva.amoblado == 'S' else 'Básico'} + {'Baño privado' if reserva.baño_priv == 'S' else 'Baño compartido'}"
            }
            data.append(reserva_data)
        
        return Response({
            'count': len(data),
            'estado': estado,
            'estado_display': get_estado_display(estado),
            'reservas': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error al obtener reservas por estado: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 🔹 OBTENER RESERVAS POR CLIENTE (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def reservas_por_cliente(request, cliente_id):
    """
    Retorna todas las reservas de un cliente específico
    Ejemplo: GET /api/reservaHotel/reservas/cliente/1/
    """
    try:
        cliente = get_object_or_404(DatosCliente, pk=cliente_id)
        
        reservas = ReservaHotel.objects.select_related(
            'habitacion',
            'reservas_gen'
        ).filter(datos_cliente=cliente).order_by('-fecha_ini')
        
        data = []
        for reserva in reservas:
            # Calcular días de estadía
            dias_estadia = 0
            if reserva.fecha_ini and reserva.fecha_fin:
                dias_estadia = (reserva.fecha_fin - reserva.fecha_ini).days
                if dias_estadia < 0:
                    dias_estadia = 0
            
            reserva_data = {
                'id_reserva_hotel': reserva.id_reserva_hotel,
                'cant_personas': reserva.cant_personas,
                'fecha_ini': reserva.fecha_ini,
                'fecha_fin': reserva.fecha_fin,
                'dias_estadia': dias_estadia,
                'estado': reserva.estado,
                'estado_display': get_estado_display(reserva.estado),
                'habitacion': {
                    'numero': reserva.habitacion.numero,
                    'piso': reserva.habitacion.piso,
                    'tipo': reserva.habitacion.tipo
                },
                'tipo_reserva': f"{'Amoblado' if reserva.amoblado == 'S' else 'Básico'} + {'Baño privado' if reserva.baño_priv == 'S' else 'Baño compartido'}",
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

# 🔹 OBTENER HABITACIONES DISPONIBLES (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def habitaciones_disponibles(request):
    """
    Retorna todas las habitaciones disponibles
    Ejemplo: GET /api/reservaHotel/habitaciones/disponibles/
    """
    try:
        habitaciones = Habitacion.objects.filter(estado='DISPONIBLE').select_related('tarifa_hotel')
        
        data = []
        for h in habitaciones:
            data.append({
                'id_habitacion': h.id_habitacion,
                'numero': h.numero,
                'piso': h.piso,
                'tipo': h.tipo,
                'amoblado': h.amoblado,
                'baño_priv': h.baño_priv,
                'estado': h.estado,
                'tarifa_hotel': {
                    'id_tarifa_hotel': h.tarifa_hotel.id_tarifa_hotel,
                    'nombre': h.tarifa_hotel.nombre,
                    'descripcion': h.tarifa_hotel.descripcion,
                    'precio_persona': float(h.tarifa_hotel.precio_persona)
                }
            })
        
        return Response({
            'count': len(data),
            'habitaciones': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error al obtener habitaciones: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==============================================
# 🔹 FUNCIONES AUXILIARES
# ==============================================

def get_estado_display(estado):
    """Convierte código de estado a texto legible"""
    estados = {
        'A': 'Activa',
        'C': 'Cancelada', 
        'F': 'Finalizada'
    }
    return estados.get(estado, 'Desconocido')

# 🔹 REALIZAR CHECK-IN (POST)
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def realizar_check_in(request, id_reserva):
    """
    Registra el check-in de una reserva
    Ejemplo: POST /api/reservaHotel/reservas/1/check-in/
    """
    try:
        with transaction.atomic():
            reserva = get_object_or_404(ReservaHotel.objects.select_related(
                'habitacion',
                'datos_cliente'
            ), pk=id_reserva)

            print(f"🔍 Iniciando check-in para reserva {id_reserva}")  # Debug
            
            # --- VALIDACIONES ---
            
            # 1. Verificar que la reserva esté activa
            if reserva.estado != 'A':
                return Response({
                    'error': 'Solo se puede hacer check-in en reservas activas',
                    'estado_actual': get_estado_display(reserva.estado)
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. Verificar que no se haya hecho check-in previamente
            if reserva.check_in is not None:
                return Response({
                    'error': 'Esta reserva ya tiene un check-in registrado',
                    'fecha_check_in': reserva.check_in.strftime('%Y-%m-%d %H:%M:%S')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 3. Verificar que la fecha actual esté dentro del rango de la reserva
            fecha_actual = date.today()
            if fecha_actual < reserva.fecha_ini:
                return Response({
                    'error': 'No se puede hacer check-in antes de la fecha de inicio de la reserva',
                    'fecha_inicio_reserva': reserva.fecha_ini,
                    'fecha_actual': fecha_actual
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if fecha_actual > reserva.fecha_fin:
                return Response({
                    'error': 'La fecha de la reserva ya expiró',
                    'fecha_fin_reserva': reserva.fecha_fin,
                    'fecha_actual': fecha_actual
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # --- REGISTRAR CHECK-IN ---
            from django.utils import timezone
            import pytz

            # En realizar_check_in:
            tz_bolivia = pytz.timezone('America/La_Paz')
            hora_bolivia = timezone.now().astimezone(tz_bolivia)

            # Esto guardará la hora en UTC, pero basada en la hora actual de Bolivia
            reserva.check_in = datetime.now() - timezone.timedelta(hours=timezone.now().utcoffset().total_seconds() / 3600) + timezone.timedelta(hours= -4)
            reserva.save()

            # Al mostrar, convertir de nuevo a hora boliviana
            ##check_in_local = timezone.localtime(reserva.check_in)
            
            # Asegurar que la habitación esté marcada como OCUPADA
            if reserva.habitacion.estado != 'OCUPADA':
                reserva.habitacion.estado = 'OCUPADA'
                reserva.habitacion.save()
            
            return Response({
                'mensaje': 'Check-in realizado correctamente',
                'reserva_id': reserva.id_reserva_hotel,
                'check_in': reserva.check_in.strftime('%Y-%m-%d %H:%M:%S'),
                'cliente': f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}",
                'habitacion': reserva.habitacion.numero,
                'fecha_check_out_esperado': reserva.fecha_fin
            }, status=status.HTTP_200_OK)
            
    except ReservaHotel.DoesNotExist:
        return Response({
            'error': 'Reserva no encontrada'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al realizar check-in: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🔹 REALIZAR CHECK-OUT (POST)
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def realizar_check_out(request, id_reserva):
    """
    Registra el check-out de una reserva y finaliza la reserva
    Ejemplo: POST /api/reservaHotel/reservas/1/check-out/
    """
    try:
        with transaction.atomic():
            reserva = get_object_or_404(ReservaHotel.objects.select_related(
                'habitacion',
                'datos_cliente'
            ), pk=id_reserva)
            
            # --- VALIDACIONES ---
            
            # 1. Verificar que la reserva esté activa
            if reserva.estado != 'A':
                return Response({
                    'error': 'Solo se puede hacer check-out en reservas activas',
                    'estado_actual': get_estado_display(reserva.estado)
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. Verificar que se haya hecho check-in previamente
            if reserva.check_in is None:
                return Response({
                    'error': 'No se puede hacer check-out sin haber realizado check-in primero'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 3. Verificar que no se haya hecho check-out previamente
            if reserva.check_out is not None:
                return Response({
                    'error': 'Esta reserva ya tiene un check-out registrado',
                    'fecha_check_out': reserva.check_out.strftime('%Y-%m-%d %H:%M:%S')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # --- REGISTRAR CHECK-OUT ---
            from django.utils import timezone
            reserva.check_out = timezone.now()
            # Cambiar estado de la reserva a Finalizada
            reserva.estado = 'F'
            reserva.save()
            
            # Liberar la habitación
            reserva.habitacion.estado = 'DISPONIBLE'
            reserva.habitacion.save()
            
            # Calcular duración de la estadía
            duracion_estadia = reserva.check_out - reserva.check_in
            dias = duracion_estadia.days
            horas = duracion_estadia.seconds // 3600
            minutos = (duracion_estadia.seconds % 3600) // 60
            
            return Response({
                'mensaje': 'Check-out realizado correctamente',
                'reserva_id': reserva.id_reserva_hotel,
                'check_in': reserva.check_in.strftime('%Y-%m-%d %H:%M:%S'),
                'check_out': reserva.check_out.strftime('%Y-%m-%d %H:%M:%S'),
                'duracion_estadia': {
                    'dias': dias,
                    'horas': horas,
                    'minutos': minutos,
                    'texto': f"{dias} días, {horas} horas, {minutos} minutos"
                },
                'cliente': f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}",
                'habitacion': reserva.habitacion.numero,
                'estado_reserva': 'Finalizada',
                'estado_habitacion': 'DISPONIBLE'
            }, status=status.HTTP_200_OK)
            
    except ReservaHotel.DoesNotExist:
        return Response({
            'error': 'Reserva no encontrada'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al realizar check-out: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🔹 CANCELAR CHECK-IN (DELETE) - Por si se equivocaron
@api_view(['DELETE'])
@permission_classes([AllowAny])
@csrf_exempt
def cancelar_check_in(request, id_reserva):
    """
    Cancela un check-in registrado (solo si no hay check-out)
    Ejemplo: DELETE /api/reservaHotel/reservas/1/check-in/cancelar/
    """
    try:
        with transaction.atomic():
            reserva = get_object_or_404(ReservaHotel, pk=id_reserva)
            
            # Validaciones
            if reserva.check_in is None:
                return Response({
                    'error': 'Esta reserva no tiene check-in registrado'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if reserva.check_out is not None:
                return Response({
                    'error': 'No se puede cancelar el check-in porque ya existe un check-out'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Cancelar check-in
            check_in_anterior = reserva.check_in
            reserva.check_in = None
            reserva.save()
            
            return Response({
                'mensaje': 'Check-in cancelado correctamente',
                'reserva_id': reserva.id_reserva_hotel,
                'check_in_cancelado': check_in_anterior.strftime('%Y-%m-%d %H:%M:%S')
            }, status=status.HTTP_200_OK)
            
    except ReservaHotel.DoesNotExist:
        return Response({
            'error': 'Reserva no encontrada'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error al cancelar check-in: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🔹 OBTENER RESERVAS PENDIENTES DE CHECK-IN (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def reservas_pendientes_check_in(request):
    """
    Retorna reservas activas sin check-in que están dentro de su periodo
    Ejemplo: GET /api/reservaHotel/reservas/pendientes-check-in/
    """
    try:
        fecha_hoy = date.today()
        
        reservas = ReservaHotel.objects.select_related(
            'datos_cliente',
            'habitacion'
        ).filter(
            estado='A',
            check_in__isnull=True,
            fecha_ini__lte=fecha_hoy,
            fecha_fin__gte=fecha_hoy
        ).order_by('fecha_ini')
        
        data = []
        for reserva in reservas:
            data.append({
                'id_reserva_hotel': reserva.id_reserva_hotel,
                'cliente': f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}",
                'cliente_telefono': reserva.datos_cliente.telefono,
                'habitacion': reserva.habitacion.numero,
                'fecha_ini': reserva.fecha_ini,
                'fecha_fin': reserva.fecha_fin,
                'cant_personas': reserva.cant_personas,
                'dias_desde_inicio': (fecha_hoy - reserva.fecha_ini).days
            })
        
        return Response({
            'count': len(data),
            'fecha_actual': fecha_hoy,
            'reservas': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error al obtener reservas: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🔹 OBTENER RESERVAS CON CHECK-IN PERO SIN CHECK-OUT (GET)
@api_view(['GET'])
@permission_classes([AllowAny])
def reservas_pendientes_check_out(request):
    """
    Retorna reservas que tienen check-in pero aún no tienen check-out
    Ejemplo: GET /api/reservaHotel/reservas/pendientes-check-out/
    """
    try:
        reservas = ReservaHotel.objects.select_related(
            'datos_cliente',
            'habitacion'
        ).filter(
            estado='A',
            check_in__isnull=False,
            check_out__isnull=True
        ).order_by('check_in')
        
        data = []
        from django.utils import timezone
        ahora = timezone.now()
        
        for reserva in reservas:
            tiempo_desde_check_in = ahora - reserva.check_in
            dias_hospedaje = tiempo_desde_check_in.days
            horas_hospedaje = tiempo_desde_check_in.seconds // 3600
            
            data.append({
                'id_reserva_hotel': reserva.id_reserva_hotel,
                'cliente': f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}",
                'cliente_telefono': reserva.datos_cliente.telefono,
                'habitacion': reserva.habitacion.numero,
                'check_in': reserva.check_in.strftime('%Y-%m-%d %H:%M:%S'),
                'fecha_check_out_esperado': reserva.fecha_fin,
                'cant_personas': reserva.cant_personas,
                'tiempo_hospedado': {
                    'dias': dias_hospedaje,
                    'horas': horas_hospedaje,
                    'texto': f"{dias_hospedaje} días, {horas_hospedaje} horas"
                },
                'sobrepaso_fecha': date.today() > reserva.fecha_fin
            })
        
        return Response({
            'count': len(data),
            'reservas': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error al obtener reservas: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def reservas_finalizadas(request):
    """
    Retorna reservas finalizadas (con check-out)
    """
    try:
        reservas = ReservaHotel.objects.select_related(
            'datos_cliente',
            'habitacion'
        ).filter(
            estado='F'  # Reservas finalizadas
        ).order_by('-check_out')
        
        data = []
        for reserva in reservas:
            duracion = None
            if reserva.check_in and reserva.check_out:
                duracion_estadia = reserva.check_out - reserva.check_in
                dias = duracion_estadia.days
                horas = duracion_estadia.seconds // 3600
                minutos = (duracion_estadia.seconds % 3600) // 60
                duracion = {
                    'dias': dias,
                    'horas': horas,
                    'minutos': minutos,
                    'texto': f"{dias}d {horas}h {minutos}m"
                }
            
            data.append({
                'id_reserva_hotel': reserva.id_reserva_hotel,
                'cliente': f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}",
                'cliente_telefono': reserva.datos_cliente.telefono,
                'habitacion': reserva.habitacion.numero,
                'fecha_ini': reserva.fecha_ini,
                'fecha_fin': reserva.fecha_fin,
                'check_in': reserva.check_in.strftime('%Y-%m-%d %H:%M:%S') if reserva.check_in else None,
                'check_out': reserva.check_out.strftime('%Y-%m-%d %H:%M:%S') if reserva.check_out else None,
                'cant_personas': reserva.cant_personas,
                'duracion_estadia': duracion
            })
        
        return Response({
            'count': len(data),
            'reservas': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error al obtener reservas finalizadas: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)