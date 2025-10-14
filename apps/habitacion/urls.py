from django.urls import path
from .views import (
    crear_habitacion,
    lista_habitaciones,
    detalle_habitacion,
    actualizar_habitacion,
    eliminar_habitacion
)

urlpatterns = [
    path('', lista_habitaciones, name='lista-habitaciones'),
    path('crear/', crear_habitacion, name='crear-habitacion'),
    path('<int:id_habitacion>/', detalle_habitacion, name='detalle-habitacion'),
    path('<int:id_habitacion>/update/', actualizar_habitacion, name='actualizar-habitacion'),
    path('<int:id_habitacion>/delete/', eliminar_habitacion, name='eliminar-habitacion'),
]
