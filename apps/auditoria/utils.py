from apps.auditoria.models import Auditoria
from apps.usuario.models import Usuario 

def registrar_login(request, user, usuario=None):
    """Crea un registro de auditoría para login."""
    if usuario is None:
        try:
            usuario = Usuario.objects.get(user=user)
        except Usuario.DoesNotExist:
            usuario = None

    nombre = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else ""
    descripcion = f"El usuario {user.username} ({nombre}) inició sesión en la aplicación."
    
    Auditoria.objects.create(
        usuario=user,
        accion='INICIO DE SESIÓN',
        tabla='auth_user',
        descripcion=descripcion
    )




###################################################################
################## AUDITORIA DE USUARIOS ##########################
###################################################################

def registrar_creacion_usuario(request, user, usuario):
    """Crea un registro de auditoría para la creación de un usuario."""
    descripcion = f"El usuario {user.username} registró el usuario {usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}."
    
    Auditoria.objects.create(
        usuario=user,
        accion='REGISTRO',
        tabla='usuario',
        descripcion=descripcion
    )

def registrar_actualizacion_usuario(request, user, usuario, datos_viejos, datos_nuevos):
    """Crea un registro de auditoría para la actualización de un usuario, campo por campo."""
    # Iterar sobre los datos nuevos para comparar con los viejos
    for campo, valor_nuevo in datos_nuevos.items():
        # Obtener el valor viejo para comparación
        valor_viejo = datos_viejos.get(campo)

        # Si el valor ha cambiado, registrar la auditoría
        if valor_viejo != valor_nuevo:
            descripcion = (
                f"El usuario {user.username} actualizó el {campo} del usuario "
                f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''} "
                f"de '{valor_viejo}' a '{valor_nuevo}'."
            )

            Auditoria.objects.create(
                usuario=user,
                accion='ACTUALIZACIÓN',
                tabla='usuario',
                descripcion=descripcion
            )


def registrar_estado_usuario(request, user, usuario):
    """Crea un registro de auditoría para el cambio de estado de un usuario."""
    estado = "habilitó" if usuario.activo else "deshabilitó"
    descripcion = f"El usuario {user.username} {estado} al usuario {usuario.nombre} {usuario.apellido_paterno or ''} {usuario.apellido_materno or ''}."
    
    Auditoria.objects.create(
        usuario=user,
        accion='ACTUALIZACIÓN',
        tabla='usuarios',
        descripcion=descripcion
    )

