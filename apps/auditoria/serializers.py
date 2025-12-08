from rest_framework import serializers
from .models import Auditoria
from django.utils import timezone
import pytz


class AuditoriaSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    usuario_nombre = serializers.SerializerMethodField()
    fecha = serializers.SerializerMethodField()
    hora = serializers.SerializerMethodField()

    class Meta:
        model = Auditoria
        fields = [
            'id',
            'usuario',
            'username',
            'usuario_nombre',
            'accion',
            'tabla',
            'descripcion',
            'fecha',
            'hora',
        ]

    def get_username(self, obj):
        if obj.usuario:
            return obj.usuario.username
        return None

    def get_usuario_nombre(self, obj):
        if obj.usuario and hasattr(obj.usuario, 'usuario'):
            usuario = obj.usuario.usuario
            return f"{usuario.nombre} {usuario.app_paterno or ''} {usuario.app_materno or ''}".strip()
        return None

    def get_fecha(self, obj):
        return obj.fecha.date() if obj.fecha else None

    def get_hora(self, obj):
        if obj.fecha:
            tz = pytz.timezone("Etc/GMT+4")  # GMT-4
            fecha_local = obj.fecha.astimezone(tz)
            return fecha_local.time().strftime("%H:%M:%S")
        return None