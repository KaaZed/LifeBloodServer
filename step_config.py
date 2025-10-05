"""Step/energy accrual constants for the LifeBlood MetaCross flow."""

from typing import Final

# Base geometry
STEP_LENGTH_METERS: Final[float] = 0.75  # см. Documentation/EN_WP_1_extracted.txt строки 70-79 (длина шага 0.75 м)
CLUSTER_DISTANCE_METERS: Final[float] = 15.0  # см. Documentation/EN_WP_1_extracted.txt строки 528-539 + техплан PATCH-110
EARTH_RADIUS_METERS: Final[float] = 6_371_000.0  # WGS84 усреднённый радиус Земли для хаверсина

# Off-chain MetaCross (базовый) конфиг
ENERGY_STEPS_PER_UNIT: Final[int] = 3_000  # см. Documentation/EN_WP_1_extracted.txt строки 511-513 (1 энергия = 3000 шагов)
BASE_METACROSS_ENERGY_UNITS: Final[float] = 3.0  # базово 3 энергии (редактируйте при необходимости)
BASE_METACROSS_SPEED_MIN_KMH: Final[float] = 3.0  # см. Documentation/EN_WP_1_extracted.txt строки 478-479 (Casual sneakers 3-8 км/ч)
BASE_METACROSS_SPEED_MAX_KMH: Final[float] = 8.0  # см. Documentation/EN_WP_1_extracted.txt строки 478-479 (Casual sneakers 3-8 км/ч)
NFT_BASE_LBC_PER_STEP: Final[float] = 0.0042  # см. Documentation/EN_WP_1_extracted.txt строки 538-543 (базовое NFT начисление)
BASE_METACROSS_LBC_MULTIPLIER: Final[float] = 0.1  # см. Documentation/EN_WP_1_extracted.txt строка 531 (MetaCross = 10% NFT дохода)
BASE_METACROSS_LBC_PER_STEP: Final[float] = NFT_BASE_LBC_PER_STEP * BASE_METACROSS_LBC_MULTIPLIER

# Activity filters
SPEED_MIN_KMH: Final[float] = BASE_METACROSS_SPEED_MIN_KMH
SPEED_MAX_KMH: Final[float] = BASE_METACROSS_SPEED_MAX_KMH
GPS_MAX_ACCURACY_METERS: Final[float] = 100.0  # см. Documentation/EN_WP_1_extracted.txt строки 72-85 + PATCH-110 (лимит точности 25 м для устойчивого GPS)

# GPS smoothing / anti-cheat
SMOOTHING_WINDOW_POINTS: Final[int] = 3  # PATCH-110 античит: окно из 3 последних точек
MAX_JUMP_METERS: Final[float] = 120.0  # PATCH-110 античит: отсечение скачка >120 м
MIN_JUMP_INTERVAL_SEC: Final[int] = 5  # PATCH-110 античит: проверка скачка в окне <10 сек

# Accruals
LBC_PER_STEP: Final[float] = BASE_METACROSS_LBC_PER_STEP
REF_LBC_PER_STEP: Final[float] = 0.00010  # см. Documentation/EN_WP_1_extracted.txt раздел Free entry + PATCH-110
SIGNUP_BONUS_LBC: Final[float] = 25.0  # см. Documentation/EN_WP_1_extracted.txt раздел Free entry + PATCH-110

# Производное суточное ограничение в шагах
DAILY_ENERGY_STEPS: Final[int] = int(BASE_METACROSS_ENERGY_UNITS * ENERGY_STEPS_PER_UNIT)

__all__ = [
    "STEP_LENGTH_METERS",
    "CLUSTER_DISTANCE_METERS",
    "EARTH_RADIUS_METERS",
    "ENERGY_STEPS_PER_UNIT",
    "BASE_METACROSS_ENERGY_UNITS",
    "BASE_METACROSS_SPEED_MIN_KMH",
    "BASE_METACROSS_SPEED_MAX_KMH",
    "SPEED_MIN_KMH",
    "SPEED_MAX_KMH",
    "GPS_MAX_ACCURACY_METERS",
    "SMOOTHING_WINDOW_POINTS",
    "MAX_JUMP_METERS",
    "MIN_JUMP_INTERVAL_SEC",
    "NFT_BASE_LBC_PER_STEP",
    "BASE_METACROSS_LBC_MULTIPLIER",
    "BASE_METACROSS_LBC_PER_STEP",
    "LBC_PER_STEP",
    "REF_LBC_PER_STEP",
    "SIGNUP_BONUS_LBC",
    "DAILY_ENERGY_STEPS",
]

