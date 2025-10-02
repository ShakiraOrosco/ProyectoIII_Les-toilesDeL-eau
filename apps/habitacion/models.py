from django.db import models
from apps.tarifa_hotel.models import TarifaHotel

class Habitacion(models.Model):
    id_habitacion = models.AutoField(primary_key=True)
    numero = models.CharField(max_length=10)
    piso = models.IntegerField()
    tipo = models.CharField(max_length=30)
    amoblado = models.CharField(max_length=1)
    baño_priv = models.CharField(max_length=1)
    estado = models.CharField(
        max_length=20,
        choices=[('DISPONIBLE','Disponible'),('OCUPADA','Ocupada'),('MANTENIMIENTO','Mantenimiento')],
        default='DISPONIBLE'
    )
    tarifa_hotel = models.ForeignKey(TarifaHotel, on_delete=models.CASCADE)



    class Meta:
        db_table = 'habitacion'
    def __str__(self):
        return f"Habitación {self.numero} ({self.estado})"
