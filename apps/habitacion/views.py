from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import Habitacion
from apps.tarifa_hotel.models import TarifaHotel


# -------------------------------
# LISTAR HABITACIONES
# -------------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def lista_habitaciones(request):
    habitaciones = Habitacion.objects.select_related('tarifa_hotel').all()
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
                'precio_persona': float(h.tarifa_hotel.precio_persona)
            }
        })
    return Response(data, status=status.HTTP_200_OK)


# -------------------------------
# CREAR HABITACIÓN (tarifa automática)
# -------------------------------
@api_view(['POST'])
@permission_classes([AllowAny])
def crear_habitacion(request):
    try:
        numero = request.data.get('numero')
        piso = request.data.get('piso')
        amoblado = request.data.get('amoblado')
        baño_priv = request.data.get('baño_priv')

        # Validar campos obligatorios
        if not all([numero, piso, amoblado, baño_priv]):
            return Response({'error': 'Faltan datos obligatorios.'}, status=status.HTTP_400_BAD_REQUEST)

        # Buscar la tarifa que coincide con las características
        tarifa = TarifaHotel.objects.filter(amoblado=amoblado, baño_priv=baño_priv).first()
        if not tarifa:
            return Response(
                {'error': 'No se encontró una tarifa que coincida con los valores de amoblado y baño privado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Crear la habitación con tarifa automática y estado por defecto
        habitacion = Habitacion.objects.create(
            numero=numero,
            piso=piso,
            tipo=tarifa.nombre,  # Se guarda el nombre de la tarifa
            amoblado=amoblado,
            baño_priv=baño_priv,
            estado='DISPONIBLE',  # Estado por defecto
            tarifa_hotel=tarifa
        )

        return Response(
            {
                'mensaje': 'Habitación creada correctamente.',
                'id_habitacion': habitacion.id_habitacion,
                'tarifa_asignada': tarifa.nombre
            },
            status=status.HTTP_201_CREATED
        )

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# -------------------------------
# DETALLE HABITACIÓN
# -------------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def detalle_habitacion(request, id_habitacion):
    try:
        habitacion = Habitacion.objects.select_related('tarifa_hotel').get(id_habitacion=id_habitacion)
        data = {
            'id_habitacion': habitacion.id_habitacion,
            'numero': habitacion.numero,
            'piso': habitacion.piso,
            'tipo': habitacion.tipo,
            'amoblado': habitacion.amoblado,
            'baño_priv': habitacion.baño_priv,
            'estado': habitacion.estado,
            'tarifa_hotel': {
                'id_tarifa_hotel': habitacion.tarifa_hotel.id_tarifa_hotel,
                'nombre': habitacion.tarifa_hotel.nombre,
                'precio_persona': float(habitacion.tarifa_hotel.precio_persona)
            }
        }
        return Response(data, status=status.HTTP_200_OK)
    except Habitacion.DoesNotExist:
        return Response({'error': 'Habitación no encontrada.'}, status=status.HTTP_404_NOT_FOUND)


# -------------------------------
# ACTUALIZAR HABITACIÓN (tarifa automática)
# -------------------------------
@api_view(['PUT'])
@permission_classes([AllowAny])
def actualizar_habitacion(request, id_habitacion):
    try:
        habitacion = Habitacion.objects.get(id_habitacion=id_habitacion)

        habitacion.numero = request.data.get('numero', habitacion.numero)
        habitacion.piso = request.data.get('piso', habitacion.piso)
        habitacion.amoblado = request.data.get('amoblado', habitacion.amoblado)
        habitacion.baño_priv = request.data.get('baño_priv', habitacion.baño_priv)
        habitacion.estado = request.data.get('estado', habitacion.estado)

        # Buscar nueva tarifa si cambian amoblado o baño
        tarifa = TarifaHotel.objects.filter(
            amoblado=habitacion.amoblado,
            baño_priv=habitacion.baño_priv
        ).first()

        if tarifa:
            habitacion.tarifa_hotel = tarifa
            habitacion.tipo = tarifa.nombre

        habitacion.save()

        return Response(
            {
                'mensaje': 'Habitación actualizada correctamente.',
                'tarifa_asignada': tarifa.nombre if tarifa else 'Sin cambios de tarifa'
            },
            status=status.HTTP_200_OK
        )

    except Habitacion.DoesNotExist:
        return Response({'error': 'Habitación no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# -------------------------------
# ELIMINAR HABITACIÓN
# -------------------------------
@api_view(['DELETE'])
@permission_classes([AllowAny])
def eliminar_habitacion(request, id_habitacion):
    try:
        habitacion = Habitacion.objects.get(id_habitacion=id_habitacion)
        habitacion.delete()
        return Response({'mensaje': 'Habitación eliminada correctamente.'}, status=status.HTTP_200_OK)
    except Habitacion.DoesNotExist:
        return Response({'error': 'Habitación no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
