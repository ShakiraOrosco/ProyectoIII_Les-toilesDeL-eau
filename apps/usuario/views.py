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
from apps.auditoria.utils import registrar_login, registrar_creacion_usuario, registrar_actualizacion_usuario
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.test import APIRequestFactory

@api_view(['POST'])
def usuario_login(request):
    """Login de usuarios con generación segura de token JWT."""

    # --- Verificación de usuario y empleado ---
    username = request.data.get('username')
    password = request.data.get('password')

    try:
        user = User.objects.get(username=username)
        usuario = Usuario.objects.get(user=user)
    except (User.DoesNotExist, Usuario.DoesNotExist):
        return Response({
            "mensaje": "Credenciales inválidas"
        }, status=status.HTTP_401_UNAUTHORIZED)

    if not usuario.estado == 'A':
        return Response({
            "mensaje": "Usuario inactivo. Contacte al administrador."
        }, status=status.HTTP_403_FORBIDDEN)
    
    # --- Registrar auditoría ---
    registrar_login(request, user, usuario)    
    # --- RECONSTRUIR EL REQUEST PARA JWT  ---
    factory = APIRequestFactory()
    jwt_request = factory.post(
        "/api/token/",
        {"username": username, "password": password},
        format='json'
    )

    # TokenObtainPairView necesita el usuario autenticado dentro del request
    jwt_request.user = user

    # --- Ejecutar la vista de SimpleJWT ---
    response = TokenObtainPairView.as_view()(jwt_request)

    return response

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
    # Verificar duplicados
    if Usuario.objects.filter(ci=ci).exists():
        return Response({"error": "El CI ya está registrado"}, status=status.HTTP_400_BAD_REQUEST)

    if Usuario.objects.filter(telefono=telefono).exists():
        return Response({"error": "El teléfono ya está registrado"}, status=status.HTTP_400_BAD_REQUEST)

    if Usuario.objects.filter(email=email).exists():
        return Response({"error": "El email ya está registrado"}, status=status.HTTP_400_BAD_REQUEST)

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

    # Registrar auditoría de creación de usuario
    registrar_creacion_usuario(request, request.user, usuario)

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
        
        # Guardar datos viejos para auditoría
        datos_viejos = {
            'nombre': usuario.nombre,
            'app_paterno': usuario.app_paterno,
            'app_materno': usuario.app_materno,
            'ci': usuario.ci,
            'telefono': usuario.telefono,
            'email': usuario.email,
            'estado': usuario.estado,
            'rol': usuario.rol
        }
        
        # Lista de campos que NO deben actualizarse
        campos_prohibidos = ['id_usuario', 'user', 'password']
        
        # Actualizar solo los campos permitidos que vienen en el request
        campos_actualizables = {
            'nombre': request.data.get('nombre'),
            'app_paterno': request.data.get('app_paterno'),
            'app_materno': request.data.get('app_materno'),
            'ci': request.data.get('ci'),
            'telefono': request.data.get('telefono'),
            'email': request.data.get('email'),
            'estado': request.data.get('estado'),
            'rol': request.data.get('rol')
        }
        
        # Solo actualizar campos que no son None y que están permitidos
        for campo, valor in campos_actualizables.items():
            if valor is not None:
                setattr(usuario, campo, valor)
        
        # Validar duplicados solo si los campos cambiaron
        if 'ci' in request.data and request.data['ci'] != datos_viejos['ci']:
            if Usuario.objects.filter(ci=request.data['ci']).exclude(id_usuario=id_usuario).exists():
                return Response(
                    {"error": "El CI ya está registrado en otro usuario"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if 'telefono' in request.data and request.data['telefono'] != datos_viejos['telefono']:
            if Usuario.objects.filter(telefono=request.data['telefono']).exclude(id_usuario=id_usuario).exists():
                return Response(
                    {"error": "El teléfono ya está registrado en otro usuario"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if 'email' in request.data and request.data['email'] != datos_viejos['email']:
            if Usuario.objects.filter(email=request.data['email']).exclude(id_usuario=id_usuario).exists():
                return Response(
                    {"error": "El email ya está registrado en otro usuario"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Actualizar email en el User de Django si existe y cambió
        if usuario.user and 'email' in request.data:
            usuario.user.email = request.data['email']
            usuario.user.save()
        
        usuario.save()
        
        # Registrar auditoría solo con los campos que realmente cambiaron
        datos_nuevos = {k: v for k, v in request.data.items() if k not in campos_prohibidos}
        registrar_actualizacion_usuario(request, request.user, usuario, datos_viejos, datos_nuevos)
        
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
    
