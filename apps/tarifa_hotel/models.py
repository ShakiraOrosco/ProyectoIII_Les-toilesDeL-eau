from django.db import models

class TarifaHotel(models.Model):
    id_tarifa_hotel = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=15)
    descripcion = models.CharField(max_length=200)
    amoblado = models.CharField(max_length=1)
    baño_priv = models.CharField(max_length=1)
    precio_persona = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        db_table = 'tarifa_hotel'

    def __str__(self):
        return f"{self.nombre} - {self.precio_persona}"
