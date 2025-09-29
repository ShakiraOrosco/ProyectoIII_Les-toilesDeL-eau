from django.db import models
from apps.usuarios.models import Usuario

class ReservaGen(models.Model):
    id_reservas_gen = models.AutoField(primary_key=True) 
    tipo = models.CharField(max_length=1)
    pago = models.BinaryField()
    administrador_id = models.IntegerField()
    empleado_id = models.IntegerField()

    class Meta:
        db_table = "reservas_gen"
