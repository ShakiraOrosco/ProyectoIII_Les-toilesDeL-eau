from django.db import models
from apps.reservas_gen.models import ReservasGen
from apps.datos_cliente.models import DatosCliente
from apps.habitacion.models import Habitacion

class ReservaHotel(models.Model):
    id_reserva_hotel = models.AutoField(primary_key=True)
    cant_personas = models.PositiveSmallIntegerField()
    amoblado = models.CharField(max_length=1)
    fecha_ini = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=1)
    baño_priv = models.CharField(max_length=1)
    reservas_gen = models.ForeignKey(ReservasGen, on_delete=models.CASCADE)
    datos_cliente = models.ForeignKey(DatosCliente, on_delete=models.CASCADE)
    habitacion = models.ForeignKey(Habitacion, on_delete=models.CASCADE)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)


    class Meta:
        db_table = 'reserva_hotel'