from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import ReservasEvento
from apps.reservas_gen.models import ReservasGen
from apps.datos_cliente.models import DatosCliente
from apps.servicios_evento.models import ServiciosEvento
from apps.servicios_adicionales.models import ServiciosAdicionales
from apps.administrador.models import Administrador
from apps.empleado.models import Empleado
from .serializers import ReservasEventoSerializer, ServiciosAdicionalesSerializer


# 🔹 Registrar una reserva de evento
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def registrar_reserva_evento(request):
    data = request.data

    # --- 1️⃣ Datos del cliente
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

    # --- 2️⃣ Datos del evento
    cant_personas = data.get('cant_personas')
    fecha = data.get('fecha')
    hora_ini = data.get('hora_ini')
    hora_fin = data.get('hora_fin')
    estado = data.get('estado', 'A')

    if not (cant_personas and fecha and hora_ini and hora_fin):
        return Response({'error': 'Faltan datos del evento'}, status=status.HTTP_400_BAD_REQUEST)

    # --- 3️⃣ Seleccionar primer empleado y primer administrador
    empleado = Empleado.objects.first()
    administrador = Administrador.objects.first()

    if not empleado or not administrador:
        return Response({'error': 'No existen registros de empleado o administrador en la base de datos'}, status=status.HTTP_400_BAD_REQUEST)

    # --- 4️⃣ Crear reserva general
    reservas_gen = ReservasGen.objects.create(
        tipo='E',  # E = Evento
        pago=None,
        administrador=administrador,
        empleado=empleado
    )

    # --- 5️⃣ Crear la reserva de evento
    reserva_evento = ReservasEvento.objects.create(
        cant_personas=cant_personas,
        hora_ini=hora_ini,
        hora_fin=hora_fin,
        fecha=fecha,
        estado=estado,
        reservas_gen=reservas_gen,
        datos_cliente=datos_cliente
    )

    # --- 6️⃣ Servicios adicionales (opcional)
    servicios_ids = data.get('servicios_adicionales', [])
    if isinstance(servicios_ids, str):
        # Si viene como texto JSON (por ejemplo "[1,2,3]")
        import json
        try:
            servicios_ids = json.loads(servicios_ids)
        except Exception:
            servicios_ids = []

    for servicio_id in servicios_ids:
        servicio = ServiciosAdicionales.objects.filter(pk=servicio_id, estado='A').first()
        if servicio:
            ServiciosEvento.objects.create(
                reservas_evento=reserva_evento,
                servicios_adicionales=servicio
            )

    # --- 7️⃣ Serializar respuesta
    serializer = ReservasEventoSerializer(reserva_evento)
    return Response({
        'mensaje': 'Reserva de evento creada correctamente',
        'reserva': serializer.data,
        'cliente_id': datos_cliente.id_datos_cliente,
        'reserva_gen_id': reservas_gen.id_reservas_gen
    }, status=status.HTTP_201_CREATED)



# 🔹 Listar servicios adicionales activos (para los checkboxes)
@api_view(['GET'])
@permission_classes([AllowAny])
def listar_servicios_adicionales_evento(request):
    """
    Retorna todos los servicios adicionales activos (estado='A')
    del tipo relacionado con eventos (por ejemplo tipo='E')
    """
    servicios = ServiciosAdicionales.objects.filter(estado='A', tipo='E')
    serializer = ServiciosAdicionalesSerializer(servicios, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
