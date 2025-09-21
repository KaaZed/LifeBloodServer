"""Step/energy accrual constants for the LifeBlood MetaCross flow."""
from typing import Final

# Base geometry
STEP_LENGTH_METERS: Final[float] = 0.75  # см. Documentation/EN_WP_1_extracted.txt строки 70-79 (step length 0.75 м)
CLUSTER_DISTANCE_METERS: Final[float] = 30.0  # см. Documentation/EN_WP_1_extracted.txt строки 528-539 + техплан PATCH-110  
EARTH_RADIUS_METERS: Final[float] = 6_371_000.0  # WGS84 усреднённый радиус Земли для хаверсина

# Activity filters
SPEED_MIN_KMH: Final[float] = 3.0  # см. Documentation/EN_WP_1_extracted.txt строки 478-479 (Casual sneakers 3-8 км/ч)
SPEED_MAX_KMH: Final[float] = 8.0  # см. Documentation/EN_WP_1_extracted.txt строки 478-479 (Casual sneakers 3-8 км/ч)
GPS_MAX_ACCURACY_METERS: Final[float] = 25.0  # см. Documentation/EN_WP_1_extracted.txt строки 72-85 + PATCH-110 (лимит точности 25 м для «устойчивого GPS»)

# GPS smoothing / anti-cheat
SMOOTHING_WINDOW_POINTS: Final[int] = 5  # PATCH-110 античит: окно 5 последних точек для усреднения
MAX_JUMP_METERS: Final[float] = 120.0  # PATCH-110 античит: отсечение скачка >120 м
MIN_JUMP_INTERVAL_SEC: Final[int] = 10  # PATCH-110 античит: скачок проверяем в окне <10 сек

# Accruals
LBC_PER_STEP: Final[float] = 0.00042  # см. Documentation/EN_WP_1_extracted.txt строки 489-492 (base gain per step)
REF_LBC_PER_STEP: Final[float] = 0.00010  # см. Documentation/EN_WP_1_extracted.txt раздел Free entry + PATCH-110 (реферальная доля 0.00010 LBC/шаг)
SIGNUP_BONUS_LBC: Final[float] = 25.0  # см. Documentation/EN_WP_1_extracted.txt раздел Free entry + PATCH-110 (приветственный бонус 25 LBC)

# Energy limits
DAILY_ENERGY_STEPS: Final[int] = 3_000  # см. Documentation/EN_WP_1_extracted.txt строки 511-513 (1 ед. энергии = 3000 шагов)

__all__ = [
    "STEP_LENGTH_METERS",
    "CLUSTER_DISTANCE_METERS",
    "EARTH_RADIUS_METERS",
    "SPEED_MIN_KMH",
    "SPEED_MAX_KMH",
    "GPS_MAX_ACCURACY_METERS",
    "SMOOTHING_WINDOW_POINTS",
    "MAX_JUMP_METERS",
    "MIN_JUMP_INTERVAL_SEC",
    "LBC_PER_STEP",
    "REF_LBC_PER_STEP",
    "SIGNUP_BONUS_LBC",
    "DAILY_ENERGY_STEPS",
]
