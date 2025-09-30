from django.db import models
from apps.usuario.models import Usuario

class Empleado(models.Model):
    id_empleado = models.AutoField(primary_key=True)
    cod_empleado = models.CharField(max_length=15)
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)



    class Meta:
        db_table = 'empleado'
    def __str__(self):
        return self.cod_empleado
