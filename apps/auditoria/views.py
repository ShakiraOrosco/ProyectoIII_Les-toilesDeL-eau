from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Auditoria
from .serializers import AuditoriaSerializer



@api_view(['GET'])
@permission_classes([AllowAny])
def listar_auditorias(request):
    """
    Endpoint para listar auditorías.
    Retorna todas las auditorías ordenadas por fecha descendente,
    incluyendo el nombre del usuario si existe.
    """
    auditorias = Auditoria.objects.select_related('usuario').all()
    serializer = AuditoriaSerializer(auditorias, many=True)
    return Response(serializer.data)


from apps.auditoria.models import Auditoria
from apps.usuario.models import Usuario 
from datetime import datetime

###################################################################
############## AUDITORIA DE RESERVAS DE HOTEL ####################
###################################################################

def registrar_creacion_reserva_hotel(request, user, reserva, cliente):
    """Crea un registro de auditoría para la creación de una reserva de hotel."""
    try:
        usuario = Usuario.objects.get(user=user) if user.is_authenticated else None
    except Usuario.DoesNotExist:
        usuario = None

    nombre_usuario = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else "Cliente"
    nombre_cliente = f"{cliente.nombre} {cliente.app_paterno} {cliente.app_materno or ''}".strip()
    
    descripcion = (
        f"El usuario {user.username} ({nombre_usuario}) registró una reserva de hotel "
        f"para el cliente {nombre_cliente} (CI: {cliente.ci}). "
        f"Habitación: {reserva.habitacion.numero}, "
        f"Fechas: {reserva.fecha_ini} al {reserva.fecha_fin}, "
        f"Personas: {reserva.cant_personas}, "
        f"Características: {'Amoblado' if reserva.amoblado == 'S' else 'Básico'} + "
        f"{'Baño privado' if reserva.baño_priv == 'S' else 'Baño compartido'}."
    )
    
    Auditoria.objects.create(
        usuario=user if user.is_authenticated else None,
        accion='REGISTRO',
        tabla='reserva_hotel',
        descripcion=descripcion
    )


def registrar_actualizacion_reserva_hotel(request, user, reserva, campos_actualizados, cambios_detalle=None):
    """Crea un registro de auditoría para la actualización de una reserva de hotel."""
    try:
        usuario = Usuario.objects.get(user=user) if user.is_authenticated else None
    except Usuario.DoesNotExist:
        usuario = None

    nombre_usuario = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else "Cliente"
    nombre_cliente = f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}"
    
    # Descripción base
    descripcion = (
        f"El usuario {user.username} ({nombre_usuario}) actualizó la reserva #{reserva.id_reserva_hotel} "
        f"del cliente {nombre_cliente}. "
    )
    
    # Agregar detalles de los cambios
    cambios = []
    
    for campo in campos_actualizados:
        if campo == 'datos_cliente':
            cambios.append("datos del cliente")
        elif campo == 'cliente_creado':
            cambios.append("nuevo cliente creado")
        elif campo == 'cliente_cambiado':
            cambios.append("cliente asignado")
        elif campo == 'habitacion':
            if cambios_detalle and 'habitacion_anterior' in cambios_detalle and 'habitacion_nueva' in cambios_detalle:
                cambios.append(f"habitación (de #{cambios_detalle['habitacion_anterior']} a #{cambios_detalle['habitacion_nueva']})")
            else:
                cambios.append("habitación")
        elif campo == 'fecha_ini':
            cambios.append(f"fecha de inicio")
        elif campo == 'fecha_fin':
            cambios.append(f"fecha de fin")
        elif campo == 'cant_personas':
            cambios.append("cantidad de personas")
        elif campo == 'estado':
            cambios.append(f"estado")
        elif campo == 'amoblado':
            cambios.append("tipo de amoblado")
        elif campo == 'baño_priv':
            cambios.append("tipo de baño")
        elif campo == 'check_in':
            cambios.append("registro de ingreso")
        elif campo == 'check_out':
            cambios.append("registro de salida")
        elif campo.startswith('cliente_'):
            cambios.append(campo.replace('cliente_', ''))
    
    if cambios:
        descripcion += f"Campos modificados: {', '.join(cambios)}."
    
    # Agregar información adicional si hay
    if cambios_detalle:
        if 'fechas_actualizadas' in cambios_detalle:
            descripcion += f" Nueva estadía: {cambios_detalle['fechas_actualizadas']['dias_estadia']} días."
        
        if 'cliente_creado' in cambios_detalle:
            descripcion += f" Cliente creado: {cambios_detalle['cliente_info']['nombre_completo']} (CI: {cambios_detalle['cliente_info']['ci']})."
    
    Auditoria.objects.create(
        usuario=user if user.is_authenticated else None,
        accion='ACTUALIZACIÓN',
        tabla='reserva_hotel',
        descripcion=descripcion
    )


def registrar_cancelacion_reserva_hotel(request, user, reserva, motivo=None):
    """Crea un registro de auditoría para la cancelación de una reserva de hotel."""
    try:
        usuario = Usuario.objects.get(user=user) if user.is_authenticated else None
    except Usuario.DoesNotExist:
        usuario = None

    nombre_usuario = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else "Sistema"
    nombre_cliente = f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}"
    
    descripcion = (
        f"El usuario {user.username} ({nombre_usuario}) canceló la reserva #{reserva.id_reserva_hotel} "
        f"del cliente {nombre_cliente} (CI: {reserva.datos_cliente.ci}). "
        f"Habitación: #{reserva.habitacion.numero}, "
        f"Fechas: {reserva.fecha_ini} al {reserva.fecha_fin}."
    )
    
    if motivo:
        descripcion += f" Motivo: {motivo}."
    
    Auditoria.objects.create(
        usuario=user if user.is_authenticated else None,
        accion='CANCELACIÓN',
        tabla='reserva_hotel',
        descripcion=descripcion
    )


def registrar_check_in_hotel(request, user, reserva):
    """Crea un registro de auditoría para el registro de ingreso de una reserva."""
    try:
        usuario = Usuario.objects.get(user=user) if user.is_authenticated else None
    except Usuario.DoesNotExist:
        usuario = None

    nombre_usuario = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else "Sistema"
    nombre_cliente = f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}"
    
    descripcion = (
        f"El usuario {user.username} ({nombre_usuario}) registró el ingreso (check-in) "
        f"de la reserva #{reserva.id_reserva_hotel} del cliente {nombre_cliente}. "
        f"Habitación: #{reserva.habitacion.numero}, "
        f"Hora de ingreso: {reserva.check_in.strftime('%Y-%m-%d %H:%M:%S')}."
    )
    
    Auditoria.objects.create(
        usuario=user if user.is_authenticated else None,
        accion='REGISTRO INGRESO',
        tabla='reserva_hotel',
        descripcion=descripcion
    )


def registrar_check_out_hotel(request, user, reserva, duracion=None):
    """Crea un registro de auditoría para el registro de salida de una reserva."""
    try:
        usuario = Usuario.objects.get(user=user) if user.is_authenticated else None
    except Usuario.DoesNotExist:
        usuario = None

    nombre_usuario = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else "Sistema"
    nombre_cliente = f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}"
    
    descripcion = (
        f"El usuario {user.username} ({nombre_usuario}) registró la salida (check-out) "
        f"de la reserva #{reserva.id_reserva_hotel} del cliente {nombre_cliente}. "
        f"Habitación: #{reserva.habitacion.numero}, "
        f"Hora de salida: {reserva.check_out.strftime('%Y-%m-%d %H:%M:%S')}."
    )
    
    if duracion:
        descripcion += f" Duración de estadía: {duracion}."
    
    Auditoria.objects.create(
        usuario=user if user.is_authenticated else None,
        accion='REGISTRO SALIDA',
        tabla='reserva_hotel',
        descripcion=descripcion
    )


def registrar_cancelacion_check_in(request, user, reserva):
    """Crea un registro de auditoría para la cancelación de un ingreso."""
    try:
        usuario = Usuario.objects.get(user=user) if user.is_authenticated else None
    except Usuario.DoesNotExist:
        usuario = None

    nombre_usuario = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else "Sistema"
    nombre_cliente = f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}"
    
    descripcion = (
        f"El usuario {user.username} ({nombre_usuario}) canceló el ingreso (check-in) "
        f"de la reserva #{reserva.id_reserva_hotel} del cliente {nombre_cliente}. "
        f"Habitación: #{reserva.habitacion.numero}."
    )
    
    Auditoria.objects.create(
        usuario=user if user.is_authenticated else None,
        accion='CANCELACIÓN INGRESO',
        tabla='reserva_hotel',
        descripcion=descripcion
    )


def registrar_subida_comprobante(request, user, reserva_gen_id, reserva=None):
    """Crea un registro de auditoría para la subida de comprobante de pago."""
    try:
        usuario = Usuario.objects.get(user=user) if user.is_authenticated else None
    except Usuario.DoesNotExist:
        usuario = None

    nombre_usuario = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else "Sistema"
    
    descripcion = (
        f"El usuario {user.username} ({nombre_usuario}) subió un comprobante de pago "
        f"para la reserva general ID #{reserva_gen_id}."
    )
    
    if reserva:
        nombre_cliente = f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}"
        descripcion += f" Cliente: {nombre_cliente}."
    
    Auditoria.objects.create(
        usuario=user if user.is_authenticated else None,
        accion='SUBIDA COMPROBANTE',
        tabla='reservas_gen',
        descripcion=descripcion
    )


def registrar_consulta_reserva_hotel(request, user, reserva):
    """Crea un registro de auditoría para la consulta de detalles de una reserva."""
    try:
        usuario = Usuario.objects.get(user=user) if user.is_authenticated else None
    except Usuario.DoesNotExist:
        usuario = None

    nombre_usuario = f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}" if usuario else "Sistema"
    nombre_cliente = f"{reserva.datos_cliente.nombre} {reserva.datos_cliente.app_paterno}"
    
    descripcion = (
        f"El usuario {user.username} ({nombre_usuario}) consultó los detalles "
        f"de la reserva #{reserva.id_reserva_hotel} del cliente {nombre_cliente}."
    )
    
    Auditoria.objects.create(
        usuario=user if user.is_authenticated else None,
        accion='CONSULTA',
        tabla='reserva_hotel',
        descripcion=descripcion
    )