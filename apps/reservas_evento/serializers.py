from rest_framework import serializers
from .models import ReservasEvento
from apps.servicios_evento.models import ServiciosEvento
from apps.servicios_adicionales.models import ServiciosAdicionales


class ServiciosAdicionalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiciosAdicionales
        fields = ['id_servicios_adicionales', 'nombre', 'descripcion', 'precio', 'tipo', 'estado']


class ReservasEventoSerializer(serializers.ModelSerializer):
    servicios = serializers.SerializerMethodField()

    class Meta:
        model = ReservasEvento
        fields = [
            'id_reservas_evento',
            'cant_personas',
            'hora_ini',
            'hora_fin',
            'fecha',
            'estado',
            'check_in',
            'check_out',
            'reservas_gen',
            'datos_cliente',
            'servicios'
        ]

    def get_servicios(self, obj):
        servicios_rel = ServiciosEvento.objects.filter(reservas_evento=obj)
        servicios = [s.servicios_adicionales for s in servicios_rel]
        return ServiciosAdicionalesSerializer(servicios, many=True).data
