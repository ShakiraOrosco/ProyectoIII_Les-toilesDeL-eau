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
    
    # 🔹 CRUD DE RESERVAS DE EVENTOS
    # Listar todas las reservas de evento
    path('reservaEvento/listar/', views.lista_reservas_evento, name='lista_reservas_evento'),
    
    # Detalle de una reserva específica (usa id_reserva, no id_reserva_gen)
    path('reservaEvento/detallar/<int:id_reserva>/', views.detalle_reserva_evento, name='detalle_reserva_evento'),
    
    # Actualizar una reserva (usa id_reserva, no id_reserva_gen)
    path('reservaEvento/actualizar/<int:id_reserva>/', views.actualizar_reserva_evento, name='actualizar_reserva_evento'),
    
    # Eliminar/Cancelar una reserva (usa id_reserva, no id_reserva_gen)
    path('reservaEvento/eliminar/<int:id_reserva>/', views.eliminar_reserva_evento, name='eliminar_reserva_evento'),
    
    # 🔹 FILTROS ADICIONALES
    # Filtrar por estado
    path('reservaEvento/estado/<str:estado>/', views.reservas_evento_por_estado, name='reservas_evento_por_estado'),
    
    # Filtrar por cliente
    path('reservaEvento/cliente/<int:cliente_id>/', views.reservas_evento_por_cliente, name='reservas_evento_por_cliente'),
    
    # 🆕 Estadísticas de la cola
    path('reservaEvento/estadisticas-cola/', views.obtener_estadisticas_cola, name='estadisticas_cola'),
]