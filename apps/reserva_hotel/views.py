from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

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
        amoblado=amoblado,
        baño_priv=baño_priv,
        estado='DISPONIBLE'
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
