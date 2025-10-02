from django.db import models
from apps.administrador.models import Administrador
from apps.empleado.models import Empleado

class ReservasGen(models.Model):
    id_reservas_gen = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=1)
    pago = models.BinaryField()
    administrador = models.ForeignKey(Administrador, on_delete=models.CASCADE)
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)


    class Meta:
        db_table = 'reservas_gen'
    def __str__(self):
        return f"ReservaGen {self.id_reservas_gen} ({self.tipo})"
