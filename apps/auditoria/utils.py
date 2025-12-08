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