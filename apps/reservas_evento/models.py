from django.db import models
from apps.reservas_gen.models import ReservasGen
from apps.datos_cliente.models import DatosCliente

class ReservasEvento(models.Model):
    id_reservas_evento = models.AutoField(primary_key=True)
    cant_personas = models.SmallIntegerField()
    hora_ini = models.DateTimeField()
    hora_fin = models.DateTimeField()
    fecha = models.DateField()
    reservas_gen = models.ForeignKey(ReservasGen, on_delete=models.CASCADE)
    datos_cliente = models.ForeignKey(DatosCliente, on_delete=models.CASCADE)
    estado = models.CharField(max_length=1)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'reservas_evento'