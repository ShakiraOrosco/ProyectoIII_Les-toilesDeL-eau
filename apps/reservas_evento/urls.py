from django.urls import path
from . import views

urlpatterns = [
     # Registrar reserva de evento
    path('reservaEvento/registrar/', views.registrar_reserva_evento, name='registrar_reserva_evento'),
    
    # 🆕 Verificar disponibilidad
    path('reservaEvento/verificar-disponibilidad/', views.verificar_disponibilidad, name='verificar_disponibilidad'),
    
    # 🆕 Obtener horarios ocupados
    path('reservaEvento/horarios-ocupados/', views.obtener_horarios_ocupados, name='horarios_ocupados'),
    
    # Listar servicios adicionales
    path('reservaEvento/servicios-adicionales/', views.listar_servicios_adicionales_evento, name='listar_servicios_adicionales'),
    
    # Subir comprobante
    path('reservaEvento/comprobante/<int:id_reserva_gen>/', views.subir_comprobante, name='subir_comprobante'),

]
