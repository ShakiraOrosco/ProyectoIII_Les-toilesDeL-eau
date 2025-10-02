from rest_framework import serializers
from .models import Usuario
from apps.empleado.models import Empleado
from apps.administrador.models import Administrador


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = '__all__'

    def create(self, validated_data):
        # Crear usuario primero
        usuario = Usuario.objects.create(**validated_data)

        # Generar código (iniciales + CI)
        iniciales = (
            (usuario.nombre[0] if usuario.nombre else "") +
            (usuario.app_paterno[0] if usuario.app_paterno else "") +
            (usuario.app_materno[0] if usuario.app_materno else "")
        ).upper()
        codigo = f"{iniciales}{usuario.ci}"

        # Crear Empleado o Administrador según el rol
        if usuario.rol.lower() == "empleado":
            Empleado.objects.create(
                cod_empleado=codigo,
                usuario=usuario
            )
        elif usuario.rol.lower() == "administrador":
            Administrador.objects.create(
                cod_admi=codigo,
                usuario=usuario
            )

        return usuario