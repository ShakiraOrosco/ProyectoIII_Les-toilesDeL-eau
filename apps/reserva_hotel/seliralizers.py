from rest_framework import serializers
from .models import ReservaHotel

class ReservaHotelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservaHotel
        fields = '__all__'  # incluye todos los campos del modelo