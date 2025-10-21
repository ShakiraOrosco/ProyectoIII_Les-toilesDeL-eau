from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Usuario
from .serializers import UsuarioSerializer
from django.contrib.auth.models import User
from apps.empleado.models import Empleado
from apps.administrador.models import Administrador

# 🔹 Perfil del usuario autenticado
@api_view(['GET'])
@permission_classes([AllowAny])
def mi_perfil(request):
    if not request.user or request.user.is_anonymous:
        return Response({'mensaje': 'No hay usuario autenticado'}, status=200)

    usuario = Usuario.objects.filter(user=request.user).first()
    if not usuario:
        return Response({'error': 'No existe un perfil asociado'}, status=404)

    serializer = UsuarioSerializer(usuario)
    return Response(serializer.data)

    
# 🔹 Crear nuevo usuario (registro público)
# apps/usuario/views.py
@api_view(['POST'])
@permission_classes([AllowAny])  # Permitir registro sin autenticación
def crear_usuario(request):
    # Extraer datos del request
    nombre = request.data.get('nombre')
    app_paterno = request.data.get('app_paterno')
    app_materno = request.data.get('app_materno')
    ci = request.data.get('ci')
    telefono = request.data.get('telefono')
    email = request.data.get('email')
    password = request.data.get('password')
    estado = request.data.get('estado', 'A')  # por defecto activo
    rol = request.data.get('rol')

    # Validar campos obligatorios
    if not nombre or not app_paterno or not ci or not email or not password or not rol:
        return Response({"error": "Faltan campos obligatorios"}, status=status.HTTP_400_BAD_REQUEST)

    # Generar username (nombre + apellido paterno en minúsculas)
    username = f"{nombre.lower()}.{app_paterno.lower()}"

    # Verificar unicidad
    if User.objects.filter(username=username).exists():
        return Response({"error": "El username ya existe"}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email=email).exists():
        return Response({"error": "El email ya está registrado"}, status=status.HTTP_400_BAD_REQUEST)

    # Crear usuario en auth_user
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )

    # Crear registro en Usuario
    usuario = Usuario.objects.create(
        user=user,
        nombre=nombre,
        app_paterno=app_paterno,
        app_materno=app_materno,
        ci=ci,
        telefono=telefono,
        email=email,
        password=password,  # plano, aunque lo ideal es encriptar
        estado=estado,
        rol=rol
    )

    # Generar código único
    iniciales = f"{nombre[0]}{app_paterno[0]}{app_materno[0] if app_materno else ''}".upper()
    codigo = f"{iniciales}{ci}"

    # Si es empleado, crear en tabla empleado
    if rol.lower() == "empleado":
        empleado = Empleado.objects.create(
            cod_empleado=codigo,
            usuario=usuario
        )
        extra_data = {"empleado_id": empleado.id_empleado, "cod_empleado": empleado.cod_empleado}

    # Si es administrador, crear en tabla administrador
    elif rol.lower() == "administrador":
        admin = Administrador.objects.create(
            cod_admi=codigo,
            usuario=usuario
        )
        extra_data = {"admin_id": admin.id_admi, "cod_admi": admin.cod_admi}

    else:
        extra_data = {"info": "Usuario creado sin rol específico"}

    # Serializar respuesta
    return Response({
        "id_usuario": usuario.id_usuario,
        "auth_user_id": user.id,
        "username": user.username,
        "nombre": usuario.nombre,
        "app_paterno": usuario.app_paterno,
        "app_materno": usuario.app_materno,
        "ci": usuario.ci,
        "telefono": usuario.telefono,
        "email": usuario.email,
        "rol": usuario.rol,
        **extra_data
    }, status=status.HTTP_201_CREATED)


#🔹 Listar todos los usuarios (solo Administrador puede listarlos)

@api_view(['GET']) 
@permission_classes([IsAuthenticated]) 
def lista_usuarios(request): 
    try:
        usuario = Usuario.objects.get(user=request.user)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=404)

    if usuario.rol in ['empleado', 'administrador']:
        usuarios = Usuario.objects.all() 
        serializer = UsuarioSerializer(usuarios, many=True)
        return Response(serializer.data)
    else: 
        return Response({'error': 'Acceso no autorizado'}, status=403)


# 🔹 Actualizar usuario por ID
@api_view(['PUT'])
@permission_classes([AllowAny])
def actualizar_usuario(request, id_usuario):
    try:
        usuario = Usuario.objects.get(id_usuario=id_usuario)
        
        # Actualizar campos del modelo Usuario
        usuario.nombre = request.data.get('nombre', usuario.nombre)
        usuario.app_paterno = request.data.get('app_paterno', usuario.app_paterno)
        usuario.app_materno = request.data.get('app_materno', usuario.app_materno)
        usuario.ci = request.data.get('ci', usuario.ci)
        usuario.telefono = request.data.get('telefono', usuario.telefono)
        usuario.email = request.data.get('email', usuario.email)
        usuario.estado = request.data.get('estado', usuario.estado)
        usuario.rol = request.data.get('rol', usuario.rol)
        
        # Si se proporciona una nueva contraseña, actualizarla
        nueva_password = request.data.get('password')
        if nueva_password:
            usuario.password = nueva_password
            # Actualizar también en el User de Django si existe
            if usuario.user:
                usuario.user.set_password(nueva_password)
                usuario.user.save()
        
        # Actualizar email en el User de Django si existe
        if usuario.user and usuario.email:
            usuario.user.email = usuario.email
            usuario.user.save()
        
        usuario.save()
        
        return Response(
            {
                'mensaje': 'Usuario actualizado correctamente.',
                'usuario': {
                    'id_usuario': usuario.id_usuario,
                    'nombre': usuario.nombre,
                    'app_paterno': usuario.app_paterno,
                    'app_materno': usuario.app_materno,
                    'ci': usuario.ci,
                    'telefono': usuario.telefono,
                    'email': usuario.email,
                    'estado': usuario.estado,
                    'rol': usuario.rol
                }
            },
            status=status.HTTP_200_OK
        )
        
    except Usuario.DoesNotExist:
        return Response(
            {'error': 'Usuario no encontrado.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST  
        )


#🔹 Eliminar usuario por ID
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def eliminar_usuario(request, id_usuario):
    try:
        usuario = Usuario.objects.get(user=request.user)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    # Solo administradores pueden eliminar
    if usuario.rol.lower() != 'Administrador':
        return Response({'error': 'Acceso no autorizado'}, status=status.HTTP_403_FORBIDDEN)

    usuario_obj = get_object_or_404(Usuario, id_usuario=id_usuario)
    usuario_obj.delete()

    return Response({'mensaje': 'Usuario eliminado correctamente'}, status=status.HTTP_204_NO_CONTENT)
    
