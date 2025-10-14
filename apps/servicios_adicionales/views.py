# apps/servicios/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import ServiciosAdicionales
from .serializers import ServiciosAdicionalesSerializer
from apps.usuario.models import Usuario  # Para validar roles
from apps.usuario.serializers import UsuarioSerializer
# 🔹 Perfil del usuario autenticado
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mi_perfil_servicios(request):
    """
    Devuelve los datos del usuario autenticado que hace requests sobre servicios.
    """
    try:
        usuario = Usuario.objects.get(user=request.user)
        serializer = UsuarioSerializer(usuario)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Usuario.DoesNotExist:
        return Response({'error': 'No existe un perfil asociado'}, status=status.HTTP_404_NOT_FOUND)

# 🔹 Crear servicio adicional (solo administrador)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crear_servicio(request):
    try:
        usuario = Usuario.objects.get(user=request.user)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    if usuario.rol.lower() != 'administrador':
        return Response({'error': 'Acceso no autorizado'}, status=status.HTTP_403_FORBIDDEN)

    serializer = ServiciosAdicionalesSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 🔹 Listar todos los servicios
@api_view(['GET'])
@permission_classes([AllowAny])  # Cualquiera puede ver los servicios
def lista_servicios(request):
    servicios = ServiciosAdicionales.objects.all()
    serializer = ServiciosAdicionalesSerializer(servicios, many=True)
    return Response(serializer.data)


# 🔹 Obtener servicio por ID
@api_view(['GET'])
@permission_classes([AllowAny])
def detalle_servicio(request, id_servicio):
    servicio = get_object_or_404(ServiciosAdicionales, id_servicios_adicionales=id_servicio)
    serializer = ServiciosAdicionalesSerializer(servicio)
    return Response(serializer.data)


# 🔹 Actualizar servicio (solo administrador)
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def actualizar_servicio(request, id_servicio):
    try:
        usuario = Usuario.objects.get(user=request.user)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    if usuario.rol.lower() != 'administrador':
        return Response({'error': 'Acceso no autorizado'}, status=status.HTTP_403_FORBIDDEN)

    servicio = get_object_or_404(ServiciosAdicionales, id_servicios_adicionales=id_servicio)
    if request.method == 'PUT':
        serializer = ServiciosAdicionalesSerializer(servicio, data=request.data)  # reemplaza todo
    else:  # PATCH
        serializer = ServiciosAdicionalesSerializer(servicio, data=request.data, partial=True)  # actualiza parcial

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


## 🔹 "Eliminar" servicio cambiando estado a Inactivo (solo administrador)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def eliminar_servicio(request, id_servicio):
    try:
        usuario = Usuario.objects.get(user=request.user)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    if usuario.rol.lower() != 'administrador':
        return Response({'error': 'Acceso no autorizado'}, status=status.HTTP_403_FORBIDDEN)

    servicio = get_object_or_404(ServiciosAdicionales, id_servicios_adicionales=id_servicio)
    
    # Cambiamos solo el estado
    servicio.estado = 'I'
    servicio.save()

    serializer = ServiciosAdicionalesSerializer(servicio)
    return Response({
        'mensaje': 'Servicio desactivado correctamente',
        'servicio': serializer.data
    }, status=status.HTTP_200_OK)
