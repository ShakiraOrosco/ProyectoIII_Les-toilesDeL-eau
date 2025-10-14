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


# 🔹 Registrar una reserva de hotel
@api_view(['POST'])
@permission_classes([AllowAny])  # Permitir a cualquiera crear reserva
def registrar_reserva_hotel(request):
    data = request.data

    # --- 1️⃣ Datos del cliente
    nombre = data.get('nombre')
    app_paterno = data.get('app_paterno')
    app_materno = data.get('app_materno')
    telefono = data.get('telefono')
    ci = data.get('ci')
    email = data.get('email')

    if not (nombre and app_paterno and telefono and ci and email):
        return Response({'error': 'Faltan datos del cliente'}, status=400)

    # Buscar si ya existe cliente con los mismos datos
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

    # --- 2️⃣ Datos de la reserva
    cant_personas = data.get('cant_personas')
    amoblado = data.get('amoblado', 'N').upper()
    baño_priv = data.get('baño_priv', 'N').upper()
    fecha_ini = data.get('fecha_ini')
    fecha_fin = data.get('fecha_fin')
    estado = data.get('estado', 'A')

    if not (cant_personas and fecha_ini and fecha_fin):
        return Response({'error': 'Faltan datos de la reserva'}, status=400)

    # --- 3️⃣ Buscar habitación disponible según criterios
    habitacion = Habitacion.objects.filter(
        amoblado=amoblado,
        baño_priv=baño_priv,
        estado='DISPONIBLE'
    ).first()

    if not habitacion:
        return Response({'error': 'No hay habitaciones disponibles con esas características'}, status=404)

    # --- 4️⃣ Seleccionar primer empleado y primer administrador registrados
    empleado = Empleado.objects.first()
    administrador = Administrador.objects.first()

    if not empleado or not administrador:
        return Response({'error': 'No existen registros de empleado o administrador en la base de datos'}, status=400)

    # --- 5️⃣ Crear reserva general
    reservas_gen = ReservasGen.objects.create(
        tipo='H',  # H = Hotel
        pago=b'\x00',  # Valor por defecto
        administrador=administrador,
        empleado=empleado
    )

    # --- 6️⃣ Crear la reserva del hotel
    reserva = ReservaHotel.objects.create(
        cant_personas=cant_personas,
        amoblado=amoblado,
        baño_priv=baño_priv,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        estado=estado,
        reservas_gen=reservas_gen,
        datos_cliente=datos_cliente,
        habitacion=habitacion
    )

    # Marcar habitación como ocupada
    habitacion.estado = 'OCUPADA'
    habitacion.save()

    # --- 7️⃣ Serializar respuesta
    serializer = ReservaHotelSerializer(reserva)
    return Response({
        'mensaje': 'Reserva creada correctamente',
        'reserva': serializer.data,
        'cliente_id': datos_cliente.id_datos_cliente,
        'habitacion_id': habitacion.id_habitacion,
        'reserva_gen_id': reservas_gen.id_reservas_gen
    }, status=status.HTTP_201_CREATED)



@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
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

