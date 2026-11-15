# SETUP: subir las dos partes a la placa

El repo tiene dos partes independientes:

| Carpeta | Qué es | Script |
| --- | --- | --- |
| `teaching/` | La app web (Kangaroo Path: portal Edu-Wifi, app de la matriz LED, banco de problemas) | `upload_teaching.sh` |
| `prediction/` | El `predict.py` que ejecuta el jurado: Qwen3.5 2B + 5 rotaciones de opciones, en menos de 60 s | `upload_prediction.sh` |

Los dos scripts usan `adb` (USB) por defecto, o SSH si defines `BOARD=arduino@<ip>`. En Git Bash de Windows,
`export MSYS_NO_PATHCONV=1` (los scripts ya lo hacen con adb).

## 1. Teaching (app web)

```bash
./upload_teaching.sh                                  # USB
BOARD=arduino@192.168.1.50 ./upload_teaching.sh       # SSH
```

Copia `teaching/` a `/home/arduino/edu-portal` (la ruta que espera `teaching/install.sh`) y ejecuta
`install.sh` en la placa. Detalles, usuarios de prueba y cómo probarla en el portátil: `teaching/README.md`.

## 2. Prediction (el test del jurado)

```bash
./upload_prediction.sh                                # USB
BOARD=arduino@192.168.1.50 ./upload_prediction.sh     # SSH
```

Copia `prediction/` a `/home/arduino/prediction`. Si el modelo no está en la placa, lo baja una vez y comprueba
su SHA-256 (`board/download_model.sh`): `Qwen_Qwen3.5-2B-Q4_0.gguf` de `bartowski/Qwen_Qwen3.5-2B-GGUF`, revisión
fijada en `prediction/config.env`. Si está en `models/` del portátil, lo sube con el resto.

En la placa, como dice el README del reto (todo local, sin red):

```bash
cd ~/prediction
board/start_server.sh        # para el servidor oficial (math-llm) y arranca el 2B en 127.0.0.1:8081
python3 predict.py --input problems.jsonl --output predictions.csv
```

Para el set de práctica de los organizadores (50 problemas, inglés y catalán), en el portátil:

```bash
python3 laptop/prepare_m3kang.py --parquet data/demo-00000-of-00001.parquet --languages eng,cat --val-fraction 0 --out data/demo --save-images
```

Después se sube `data/demo/train.jsonl` a la placa y se ejecuta con `predict.py --input`.
Para volver al servidor oficial: `pkill -f board/bin/llama-server; docker start math-llm`
(o `sudo systemctl start math-llm`).

### Qué hace `prediction/`

- `board/bin/llama-server`: llama.cpp b12383 con un parche para el Cortex-A53 de la placa (`board/patch_sgemm.py`,
  recompilar con `board/build_a53.sh`). Lee el prompt un 59 % más rápido (2B: 4.7 → 7.5 tok/s). Estático: no
  necesita nada más en la placa.
- `copilot/perm.py`: sin system prompt; pregunta "Which option is correct?" y lee las probabilidades de A-E. Muestra
  las opciones en hasta 5 órdenes rotados y suma, para cancelar el sesgo de letra. Antes de empezar planifica
  cuántos órdenes caben en 48 s.
- **Solo texto:** a los problemas con figura se les pasa solo el texto, nunca la imagen. Sin las 5 opciones legibles
  responde D al instante.
- Siempre una letra A-E: errores o timeouts responden `FALLBACK_ANSWER` (D).

### Medido

| Prueba | Resultado |
| --- | --- |
| Placa, los 6 problemas más largos del set de práctica (3 en inglés, 3 en catalán) | todos en **37-44 s**, letra válida |
| Placa, benchmark del repo (164 problemas M3Kang) | 31.7 % (baseline 0.8B: 24.4 %), máximo 46 s, 0 por encima de 60 s |
| GPU, 1747 problemas M3Kang en inglés | 28.3 % (baseline 0.8B: 21.1 %) |
| GPU, set de práctica (100 filas, eng+cat) | **16/100** (texto 13/80, figura 3/20), 100/100 letras válidas |

**Ojo con el set de práctica:** ahí este solver va peor que en M3Kang. En el mismo set, el pipeline de razonamiento
del kit de fine-tuning (`reasoning-g/`) con el 2B fine-tuneado (checkpoint 45) acierta 25/80 filas de texto, pero
proyectado con las velocidades reales de la placa solo 14/80 aciertan **y** acaban en menos de 60 s. Con el 1.7B
de referencia, 23/80 y 16/80. Antes del test final, elegid entre:

- `prediction/`: siempre en tiempo, peor en este set.
- El razonamiento: mejor en este set, pero hay que ajustar `LLM_READ_TPS` / `LLM_WRITE_TPS` a la placa (2B Q4_K_M:
  4.64 / 2.44) o se pasa de 60 s.
