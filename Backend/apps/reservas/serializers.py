from rest_framework import serializers
from .models import ReservaGen

class ReservaGenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservaGen
        fields = "__all__"
