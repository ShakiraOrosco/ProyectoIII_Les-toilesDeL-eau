from rest_framework import serializers
from .models import ServiciosAdicionales

class ServiciosAdicionalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiciosAdicionales
        fields = '__all__'
