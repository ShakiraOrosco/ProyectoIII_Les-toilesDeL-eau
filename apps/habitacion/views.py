from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Habitacion
from .serializers import HabitacionSerializer
from apps.usuario.models import Usuario

# 🔹 Crear habitación
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crear_habitacion(request):
    try:
        usuario = Usuario.objects.get(user=request.user)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=404)

    # Solo administradores pueden crear habitaciones
    if usuario.rol.lower() != 'administrador':
        return Response({'error': 'Acceso no autorizado'}, status=403)

    serializer = HabitacionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


# 🔹 Listar todas las habitaciones
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def lista_habitaciones(request):
    habitaciones = Habitacion.objects.all()
    serializer = HabitacionSerializer(habitaciones, many=True)
    return Response(serializer.data, status=200)


# 🔹 Obtener una habitación por ID
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_habitacion(request, id_habitacion):
    habitacion = get_object_or_404(Habitacion, id_habitacion=id_habitacion)
    serializer = HabitacionSerializer(habitacion)
    return Response(serializer.data, status=200)


# 🔹 Actualizar habitación
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def actualizar_habitacion(request, id_habitacion):
    try:
        usuario = Usuario.objects.get(user=request.user)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=404)

    #===============================================
    # Solo administradores pueden actualizar
    #===============================================
    if usuario.rol.lower() != 'Administrador':
        return Response({'error': 'Acceso no autorizado'}, status=403)

    habitacion = get_object_or_404(Habitacion, id_habitacion=id_habitacion)
    serializer = HabitacionSerializer(habitacion, data=request.data, partial=True)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)


# 🔹 Eliminar habitación
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def eliminar_habitacion(request, id_habitacion):
    try:
        usuario = Usuario.objects.get(user=request.user)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=404)
    #===============================================
    # Solo administradores pueden eliminar
    #===============================================
    if usuario.rol.lower() != 'Administrador':
        return Response({'error': 'Acceso no autorizado'}, status=403)

    habitacion = get_object_or_404(Habitacion, id_habitacion=id_habitacion)
    habitacion.delete()

    return Response({'mensaje': 'Habitación eliminada correctamente'}, status=204)

