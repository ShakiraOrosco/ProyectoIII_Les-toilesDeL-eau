from django.db import models

class DatosCliente(models.Model):
    id_datos_cliente = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=15)
    app_paterno = models.CharField(max_length=15, null=True, blank=True)
    app_materno = models.CharField(max_length=15, null=True, blank=True)
    telefono = models.IntegerField()
    ci = models.BigIntegerField()
    email = models.EmailField(max_length=50)

    class Meta:
        db_table = 'datos_cliente'
    def __str__(self):
        return f"{self.nombre} {self.app_paterno or ''}"
    