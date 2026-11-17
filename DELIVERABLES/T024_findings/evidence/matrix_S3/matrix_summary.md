# Crackle matrix

Seconds per run: 20. Clicks/min = clicks found in raw.wav by crackle_core (hypothesis, not proof).

## S3 tone loopback
| | mode | rate | block | clicks/min | drop | xruns | p99 ms | verdict |
|-|-|-|-|-|-|-|-|-|
| * | MME shared | 48000 | 128 | 2.992021 | 0 | 0 | 0.148 | electrical (medium) |
|  | MME shared | 48000 | 256 | 2.992021 | 1 | 0 | 0.156 | electrical (medium) |
|  | WASAPI shared | 48000 | 128 | 8.964143 | 0 | 0 | 0.155 | hardware_or_driver_input (medium) |
|  | WASAPI shared | 48000 | 256 | 8.968908 | 0 | 0 | 0.169 | hardware_or_driver_input (medium) |
|  | WASAPI exclusive | 48000 | 256 | 5278.478492 | 0 | 0 | 0.15 | hardware_or_driver_input (high) |
|  | WASAPI exclusive | 48000 | 128 | 8796.0 | 0 | 0 | 0.147 | hardware_or_driver_input (medium) |

