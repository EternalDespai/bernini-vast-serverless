# Bernini Serverless и интерфейс v6

Подготовленный код проверен локально. Проверка на живом Vast worker пока не выполнена.

## Что найдено в логах

В `instance-55063724-instance-logs (1).txt` Docker и ComfyUI запускаются,
ComfyUI отвечает на 18188, репозиторий клонируется и ветка выбирается.
Bootstrap создаёт `/workspace/worker-env` на Python 3.10.20 и устанавливает
vastai 1.8.3. Файл заканчивается после генерации сертификата. В нём нет
Python traceback, поэтому точную причину падения PyWorker этот файл не доказывает.
Нужен `/workspace/pyworker.log` и, при его отсутствии, `/workspace/debug.log`.

Исправлены воспроизводимые проблемы:

- Ненулевой `supervisorctl status` больше не обрывает обнаружение ComfyUI.
- Резервный adapter не вызывает отсутствующий pip внутри uv-окружения.
- SDK проверяется до загрузки моделей, этапы старта печатаются в лог.
- Наличие трёх benchmark-файлов в R2 проверяется до загрузки весов.
- Клиент v6 задаёт отдельные таймауты ожидания GPU и обработки, по 14400 секунд.
- Не выполняется автоматическая повторная отправка потенциально работающего видео.
- Проверяется HTTP-ответ SDK и вложенный ответ Bernini с правильным job_id.
- Ошибка отправки не перекрывает уже поступающий прогресс обработки из R2.

## Существующий шаблон

Использовать исходный **ComfyUI Serverless** template как основу. Сохранить
его штатные настройки сети и запуска. Не заменять его обычным On-Demand template.

| Поле | Значение |
| --- | --- |
| Название | Bernini RV2V Serverless |
| Image | vastai/comfy:v0.20.1-cuda-12.9-py312 |
| Disk | 120 GB |
| PYWORKER_REPO | https://github.com/EternalDespai/bernini-vast-serverless |
| PYWORKER_REF | fix/supervisor-startup-status |
| SERVERLESS | true |
| BACKEND | comfyui-json |
| COMFYUI_API_BASE | http://localhost:18188 |
| COMFY_API_URL | http://127.0.0.1:18188 |
| COMFY_DIR | /workspace/ComfyUI |
| COMFY_PYTHON | /venv/main/bin/python |
| BERNINI_COMFY_SUPERVISOR_NAME | comfyui |
| BERNINI_FULL_VIDEO | 1 |
| BERNINI_JOB_TIMEOUT_SECONDS | 7200 |
| R2_BUCKET | bernini-rv2v |

R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY оставить в приватных
переменных Vast. BERNINI_BENCHMARK_JOB_ID должен совпадать с существующим
`benchmark_job_id.txt` интерфейса v6. Не использовать ID полного пользовательского
видео вместо короткого benchmark. Это служебный прогрев Vast, он выполняется
автоматически при запуске worker.

Из истории известен фильтр `cuda_max_good>=12.6 compute_cap>=750 num_gpus=1 gpu_ram>=48000`.
Это историческая настройка, не доказательство совместимости каждого подходящего GPU.
Для первой проверки разумно использовать уже проверенный проектом H100.

Восстановленный из истории on-start:

```bash
export SERVERLESS=true
export BACKEND=comfyui-json
export COMFYUI_API_BASE="http://localhost:18188"
entrypoint.sh
```

Endpoint из истории: имя `ylxfcvlr`, ID `40317`. Проверить, что он ещё существует.
Ограничение для первого запуска: максимум 1 worker. Для scale-to-zero:
min_workers=0, min_load=0, cold_workers=0, inactivity_timeout=600.
После сохранения template проверить template hash у workgroup: изменение
шаблона не доказывает, что уже существующая группа использует новую ревизию.

## Интерфейс v6

Исходный v6 включён в `ui_v6/`, сохранены форма видео/фото, загрузка R2,
прогресс и скачивание. Это обновление той же версии, без замены дизайна.

1. Сохранить имеющиеся приватные `r2_config.env`, `vast_config.env`,
   `benchmark_job_id.txt`, `benchmark_configured.txt` и папку `jobs`.
2. Обновить программные файлы из `ui_v6/`. Приватные файлы не входят в архив.
3. Запустить `INSTALL_R2_WINDOWS.bat`. Python по умолчанию:
   `C:\AI\ComfyUI_windows_portable\python_embeded\python.exe`.
4. Для анализа видео нужен FFmpeg с **ffprobe.exe** в PATH.
   Пакет imageio-ffmpeg предоставляет ffmpeg, но не заменяет ffprobe.
   Можно задать полный путь переменной BERNINI_FFPROBE.
5. В существующем `vast_config.env` указать имя действующего endpoint.
   Пример файла содержит восстановленное имя `ylxfcvlr`.
6. Запустить `START_WINDOWS.bat`, выбрать MP4 и JPG/PNG и отправить задание.

Если benchmark ещё не настроен, v6 автоматически создаст его и покажет ID.
Один раз сохранить этот ID в приватной переменной Vast и в
`benchmark_configured.txt`. При обновлении уже настроенного v6 не удалять эти файлы.

## Проверка запуска

Ожидаемые этапы в `/workspace/pyworker.log`:

```text
BERNINI_BOOTSTRAP_STAGE=sdk_check
BERNINI_BOOTSTRAP_STAGE=prepare_backend
BERNINI_BOOTSTRAP_STAGE=benchmark_inputs
BERNINI_BENCHMARK_INPUTS_READY
BERNINI_BOOTSTRAP_STAGE=setup_bernini
BERNINI_BOOTSTRAP_STAGE=restart_comfyui
BERNINI_BOOTSTRAP_STAGE=preflight
BERNINI_PREFLIGHT_READY
BERNINI_BOOTSTRAP_STAGE=run_sdk
```

Отсутствие следующего этапа указывает, где искать проблему. Важно отличать
успешный запуск контейнера от готовности worker после benchmark.
Проверка считается завершённой только после получения result.mp4 через v6,
проверки всей длительности ролика и перехода worker в ожидаемое состояние
после inactivity timeout. Модели и подготовка могут занимать значительное время
на первом запуске; локальные тесты не измеряют cold start.

## Локальные тесты

`python -m pytest -q`: 48 тестов и 18 subtests на vastai 1.8.3.
Это проверяет код и SDK-контракты без GPU, R2-ключей и платной генерации.
