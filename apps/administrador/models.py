from django.db import models
from apps.usuario.models import Usuario

class Administrador(models.Model):
    id_admi = models.AutoField(primary_key=True)
    cod_admi = models.CharField(max_length=15)
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, unique=True)


    class Meta:
        db_table = 'administrador'
    def __str__(self):
        return self.cod_admi
