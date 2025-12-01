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

    # 🔹 CHECK-IN Y CHECK-OUT DE EVENTOS
    path('reservaEvento/<int:id_reserva>/check-in/', views.realizar_check_in_evento, name='realizar_check_in_evento'),
    path('reservaEvento/<int:id_reserva>/check-out/', views.realizar_check_out_evento, name='realizar_check_out_evento'),
    path('reservaEvento/<int:id_reserva>/check-in/cancelar/', views.cancelar_check_in_evento, name='cancelar_check_in_evento'),
    
    # 🔹 CONSULTAS DE GESTIÓN
    path('reservaEvento/pendientes-check-in/', views.reservas_evento_pendientes_check_in, name='reservas_evento_pendientes_check_in'),
    path('reservaEvento/pendientes-check-out/', views.reservas_evento_pendientes_check_out, name='reservas_evento_pendientes_check_out'),

    path('reservaEvento/finalizados/', views.eventos_finalizados, name='eventos_finalizados'),
    path('reservaEvento/cancelados/', views.eventos_cancelados, name='eventos_cancelados'),

    #🔹 NOTIFICACIONES DE EVENTOS
    path('reservaEvento/notificaciones/', views.obtener_notificaciones_eventos, name='obtener_notificaciones_eventos'),
    #🔹 Estadistica de eventos de hoy 
    path('reservaEvento/estadisticas-hoy/', views.estadisticas_eventos_hoy, name='estadisticas_eventos_hoy'),



]