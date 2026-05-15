# traffic_model.py

"""
Модуль моделирования прогнозного дорожного трафика.

В модели учитываются:
- базовая скорость по категории дороги;
- утренний и вечерний пики;
- обычная зона повышенной загруженности;
- отдельная зона модельного локального ухудшения дорожной ситуации,
  включаемая через веб-интерфейс.
"""

import math

from config import (
    MIN_SPEED_KPH,
    MORNING_PEAK_CENTER,
    EVENING_PEAK_CENTER,
    MORNING_PEAK_SIGMA,
    EVENING_PEAK_SIGMA,
    TRAFFIC_DROP_BY_HIGHWAY,
    CONGESTION_ZONE,
    CONGESTION_ZONE_EXTRA_DROP_MORNING,
    CONGESTION_ZONE_EXTRA_DROP_EVENING,
    ENABLE_INCIDENT_SCENARIO,
    INCIDENT_ZONE,
    INCIDENT_CENTER_TIME,
    INCIDENT_SIGMA,
    INCIDENT_EXTRA_DROP,
)


# Глобальный переключатель модельного локального ухудшения.
# По умолчанию берется значение из config.py.
# В веб-интерфейсе это значение меняется через галочку.
INCIDENT_SCENARIO_ACTIVE = ENABLE_INCIDENT_SCENARIO


def set_incident_scenario_enabled(is_enabled: bool):
    """
    Включает или выключает учет модельного локального ухудшения дорожной ситуации.
    Используется веб-интерфейсом.
    """
    global INCIDENT_SCENARIO_ACTIVE
    INCIDENT_SCENARIO_ACTIVE = is_enabled


def gaussian_drop(tau_min: float, center: float, sigma: float) -> float:
    """
    Значение гауссовой функции снижения скорости.
    tau_min, center, sigma задаются в минутах.
    """
    return math.exp(-((tau_min - center) ** 2) / (2 * sigma**2))


def get_traffic_drop(highway_type: str) -> tuple[float, float]:
    """
    Возвращает коэффициенты глубины утреннего и вечернего снижения скорости.
    """
    return TRAFFIC_DROP_BY_HIGHWAY.get(
        highway_type,
        TRAFFIC_DROP_BY_HIGHWAY["unclassified"],
    )


def is_point_in_zone(lat: float, lon: float, zone: dict) -> bool:
    """
    Проверяет, находится ли точка внутри прямоугольной зоны.
    """
    return (
        zone["min_lat"] <= lat <= zone["max_lat"]
        and zone["min_lon"] <= lon <= zone["max_lon"]
    )


def is_edge_in_congestion_zone(edge_data: dict) -> bool:
    """
    Проверяет, находится ли ребро в обычной зоне повышенной загруженности.
    """
    lat = edge_data.get("midpoint_lat")
    lon = edge_data.get("midpoint_lon")

    if lat is None or lon is None:
        return False

    return is_point_in_zone(lat, lon, CONGESTION_ZONE)


def is_edge_in_incident_zone(edge_data: dict) -> bool:
    """
    Проверяет, находится ли ребро в отдельной зоне модельного локального ухудшения.
    """
    lat = edge_data.get("midpoint_lat")
    lon = edge_data.get("midpoint_lon")

    if lat is None or lon is None:
        return False

    return is_point_in_zone(lat, lon, INCIDENT_ZONE)


def get_incident_factor(edge_data: dict, tau_min: float) -> float:
    """
    Возвращает дополнительный коэффициент снижения скорости для
    демонстрационного режима локального ухудшения дорожной ситуации.

    Если сценарий выключен или ребро не попадает в INCIDENT_ZONE,
    дополнительное снижение не применяется.
    """
    if not INCIDENT_SCENARIO_ACTIVE:
        return 0.0

    if not is_edge_in_incident_zone(edge_data):
        return 0.0

    time_factor = gaussian_drop(
        tau_min=tau_min,
        center=INCIDENT_CENTER_TIME,
        sigma=INCIDENT_SIGMA,
    )

    return INCIDENT_EXTRA_DROP * time_factor


def predicted_speed_kph(edge_data: dict, tau_min: float) -> float:
    """
    Вычисляет прогнозируемую скорость на ребре в момент времени tau_min.
    """
    base_speed = float(edge_data.get("base_speed_kph", 30.0))
    highway_type = edge_data.get("highway_type", "unclassified")

    morning_drop, evening_drop = get_traffic_drop(highway_type)

    morning_factor = gaussian_drop(
        tau_min=tau_min,
        center=MORNING_PEAK_CENTER,
        sigma=MORNING_PEAK_SIGMA,
    )

    evening_factor = gaussian_drop(
        tau_min=tau_min,
        center=EVENING_PEAK_CENTER,
        sigma=EVENING_PEAK_SIGMA,
    )

    traffic_factor = (
        1.0
        - morning_drop * morning_factor
        - evening_drop * evening_factor
    )

    # Обычная дополнительная загруженность центральной зоны.
    if is_edge_in_congestion_zone(edge_data):
        traffic_factor -= CONGESTION_ZONE_EXTRA_DROP_MORNING * morning_factor
        traffic_factor -= CONGESTION_ZONE_EXTRA_DROP_EVENING * evening_factor

    # Отдельное модельное локальное ухудшение дорожной ситуации.
    traffic_factor -= get_incident_factor(edge_data, tau_min)

    speed = base_speed * traffic_factor

    return max(MIN_SPEED_KPH, speed)


def dynamic_travel_time_min(edge_data: dict, tau_min: float) -> float:
    """
    Вычисляет динамический вес ребра:
    время прохождения участка в минутах при въезде в момент tau_min.
    """
    length_m = float(edge_data.get("length", 0.0))
    speed_kph = predicted_speed_kph(edge_data, tau_min)

    return length_m / speed_kph * 0.06
