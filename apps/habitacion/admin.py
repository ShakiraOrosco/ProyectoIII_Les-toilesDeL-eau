from django.contrib import admin
from .models import Habitacion

@admin.register(Habitacion)
class HabitacionAdmin(admin.ModelAdmin):
    list_display = ('id_habitacion', 'numero', 'piso', 'tipo', 'estado', 'tarifa_hotel')
    list_filter = ('estado', 'tipo', 'piso')
    search_fields = ('numero', 'tipo')
    ordering = ('piso', 'numero')
