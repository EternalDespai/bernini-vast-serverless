#!/usr/bin/env python3
"""Local Bernini UI: R2 upload, benchmark preparation, Vast job submission."""
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
import threading
import time
from io import BytesIO
from urllib.parse import quote
from PIL import Image, ImageOps, UnidentifiedImageError
from email.parser import BytesParser
from email.policy import default
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import parse_qs
# ComfyUI portable Python uses an isolated ._pth file and may omit the
# script directory. Add only this application directory for sibling imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_duration import inspect_video

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / 'jobs'
MAX_BODY = 350 * 1024 * 1024
JOB_RE = re.compile(r'[a-f0-9]{32}')
TASKS = {}
TASKS_LOCK = threading.Lock()


def r2_settings():
    path = ROOT / 'r2_config.env'
    if not path.exists():
        raise ValueError('Нет r2_config.env. Скопируй r2_config.example.env и заполни ключи локально.')
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError('Ошибка формата r2_config.env: ожидается KEY=VALUE')
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    required = ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')
    if any(not values.get(key) for key in required):
        raise ValueError('Заполни все 4 значения в r2_config.env')
    if values['R2_BUCKET'] != 'bernini-rv2v':
        raise ValueError('Проверь R2_BUCKET: ожидается bernini-rv2v')
    if not re.fullmatch(r'[0-9a-fA-F]{32}', values['R2_ACCOUNT_ID']):
        raise ValueError('R2_ACCOUNT_ID должен быть 32-символьным ID аккаунта Cloudflare, не URL')
    return values


def upload_to_r2(folder, job_id):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise ValueError('Не установлен boto3. Запусти INSTALL_R2_WINDOWS.bat.')
    settings = r2_settings()
    client = boto3.client('s3', endpoint_url='https://' + settings['R2_ACCOUNT_ID'] + '.r2.cloudflarestorage.com',
        aws_access_key_id=settings['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=settings['R2_SECRET_ACCESS_KEY'],
        region_name='auto', config=Config(signature_version='s3v4', retries={'max_attempts': 3}))
    names = ['source.mp4', 'workflow_api.json']
    refs = [f for f in folder.iterdir() if f.name.startswith('reference.') and f.suffix.lower() in ('.jpg','.jpeg','.png')]
    if len(refs) != 1: raise ValueError('Не найдена фотография reference')
    names.append(refs[0].name)
    for name in names:
        content_type = 'video/mp4' if name.endswith('.mp4') else 'application/json' if name.endswith('.json') else 'image/png' if name.endswith('.png') else 'image/jpeg'
        client.upload_file(str(folder / name), settings['R2_BUCKET'], f'jobs/{job_id}/{name}', ExtraArgs={'ContentType':content_type})
    return names

BENCHMARK_ID_FILE = ROOT / 'benchmark_job_id.txt'


def benchmark_ffmpeg():
    """Use PATH FFmpeg or the portable imageio-ffmpeg executable."""
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        raise ValueError('Для автоматического benchmark нужен FFmpeg. Запусти INSTALL_R2_WINDOWS.bat.')


def ensure_benchmark_from_upload(folder):
    """Prepare one persistent 17-frame benchmark in R2, once per UI install.

    Called only after the ordinary user job has already uploaded successfully.
    The user job remains untouched; the benchmark gets its own UUID.
    """
    if BENCHMARK_ID_FILE.exists():
        saved = BENCHMARK_ID_FILE.read_text(encoding='ascii').strip()
        if JOB_RE.fullmatch(saved):
            return saved, False
        raise ValueError('Некорректный benchmark_job_id.txt; проверь настройку')
    ffmpeg = benchmark_ffmpeg()
    benchmark_id = uuid.uuid4().hex
    client, bucket = r2_client()
    import tempfile
    with tempfile.TemporaryDirectory(prefix='bernini_benchmark_') as tmp:
        clip = Path(tmp) / 'benchmark.mp4'
        try:
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                            '-i', str(folder / 'source.mp4'), '-vf', 'fps=16',
                            '-frames:v', '17', '-an', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', str(clip)],
                           check=True, timeout=180, capture_output=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            raise ValueError('Не удалось создать 17-кадровый benchmark через FFmpeg')
        if not clip.is_file() or clip.stat().st_size == 0:
            raise ValueError('FFmpeg не создал benchmark.mp4')
        target = f'jobs/{benchmark_id}/'
        client.upload_file(str(clip), bucket, target + 'source.mp4',
                           ExtraArgs={'ContentType': 'video/mp4'})
        for name, mime in [('reference.jpg', 'image/jpeg'),
                           ('workflow_api.json', 'application/json')]:
            client.upload_file(str(folder / name), bucket, target + name,
                               ExtraArgs={'ContentType': mime})
    # Save only after all 3 objects uploaded successfully.
    BENCHMARK_ID_FILE.write_text(benchmark_id + '\n', encoding='ascii')
    return benchmark_id, True


def extra_settings():
    """Vast SDK endpoint config; keys stay in local private file."""
    path = ROOT / 'vast_config.env'
    if not path.exists():
        raise ValueError('Создай vast_config.env из vast_config.example.env')
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, val = line.split('=', 1)
            values[key.strip()] = val.strip().strip('"').strip("'")
    name = values.get('BERNINI_ENDPOINT_NAME', '')
    token = values.get('VAST_API_KEY', '')
    if not re.fullmatch(r'[a-z0-9_-]{3,64}', name) or not token:
        raise ValueError('Укажи BERNINI_ENDPOINT_NAME и VAST_API_KEY в vast_config.env')
    return name, token


async def submit_vast_job(name, token, job_id):
    from vast_submit import submit_job
    return await submit_job(name, token, job_id,
        timeout=os.getenv('BERNINI_REQUEST_TIMEOUT_SECONDS', '14400'))


def r2_client():
    import boto3
    settings = r2_settings()
    return boto3.client('s3', endpoint_url='https://' + settings['R2_ACCOUNT_ID'] + '.r2.cloudflarestorage.com',
        aws_access_key_id=settings['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=settings['R2_SECRET_ACCESS_KEY'], region_name='auto'), settings['R2_BUCKET']


def launch_vast(job_id):
    """Submit one job through official Vast SDK without exposing secrets."""
    try:
        import asyncio
        name, token = extra_settings()
        with TASKS_LOCK:
            TASKS[job_id] = {'state': 'waiting_for_gpu'}
        asyncio.run(submit_vast_job(name, token, job_id))
    except Exception as exc:
        print('Vast submission error type:', type(exc).__name__)
        with TASKS_LOCK:
            TASKS[job_id] = {'state': 'failed', 'stage': 'failed',
                             'message': 'Ошибка отправки Vast (' + type(exc).__name__ + '). Проверь настройки endpoint и логи worker.'}


def read_status(job_id):
    with TASKS_LOCK:
        local = dict(TASKS.get(job_id, {}))
    if not local:
        raise ValueError('Задание не найдено в текущем сеансе')
    client, bucket = r2_client()
    try:
        obj = client.get_object(Bucket=bucket, Key=f'jobs/{job_id}/status.json')
        state = json.loads(obj['Body'].read())
    except client.exceptions.NoSuchKey:
        state = {'state': 'queued', 'stage': 'waiting_for_gpu', 'percent': None}
    except Exception as exc:
        print('Status read error type:', type(exc).__name__)
        state = {'state': 'queued', 'stage': 'waiting_for_gpu', 'percent': None}
    if local.get('state') == 'failed' and state.get('state') in ('queued', 'waiting_for_gpu'):
        state = dict(local)
    if state.get('state') == 'complete':
        try:
            client.head_object(Bucket=bucket, Key=f'jobs/{job_id}/result.mp4')
            state['download_ready'] = True
        except Exception:
            state['state'], state['stage'], state['percent'] = 'running', 'uploading', None
    return state


def delete_cloud(job_id):
    client, bucket = r2_client()
    prefix = f'jobs/{job_id}/'
    continuation = None
    deleted = 0
    while True:
        args = {'Bucket': bucket, 'Prefix': prefix, 'MaxKeys': 1000}
        if continuation:
            args['ContinuationToken'] = continuation
        page = client.list_objects_v2(**args)
        keys = [{'Key': item['Key']} for item in page.get('Contents', [])]
        if keys:
            client.delete_objects(Bucket=bucket, Delete={'Objects': keys, 'Quiet': True})
            deleted += len(keys)
        if not page.get('IsTruncated'):
            break
        continuation = page['NextContinuationToken']
    return deleted


HOST = '127.0.0.1'
PORT = int(os.environ.get('BERNINI_UI_PORT', '8765'))

HTML = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bernini Studio · Подготовка задания</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#0d1018;color:#e9ecf5;margin:0;min-height:100vh;display:grid;place-items:center;padding:28px}main{width:min(660px,100%);background:#171b27;border:1px solid #333a4c;border-radius:20px;padding:32px;box-shadow:0 20px 70px #0005}h1{font-size:26px;margin:0 0 8px}.muted{color:#abb5c7;line-height:1.55}.tag{display:inline-block;font-size:12px;background:#283d35;color:#8ce6ba;padding:5px 10px;border-radius:20px;margin-bottom:16px}label{display:block;font-weight:600;margin:24px 0 8px}input[type=file],select{width:100%;padding:14px;background:#0f1420;border:1px dashed #66718a;border-radius:12px;color:#e9ecf5}select{border-style:solid}button,.btn{display:inline-block;width:100%;background:#8a72f8;color:#fff;border:0;border-radius:12px;padding:15px;font-size:16px;font-weight:700;margin-top:26px;cursor:pointer;text-decoration:none;text-align:center}button:hover,.btn:hover{background:#765ee3}.notice{margin-top:20px;padding:14px;background:#222a39;border-radius:12px;font-size:13px;color:#bac4d6;line-height:1.5}#status{margin-top:14px;color:#b2f1c9}small{font-size:12px;color:#abb5c7}a{color:#b5a8ff}</style></head><body><main>
<span class="tag">Локальный интерфейс · R2 + Vast Serverless</span><h1>Bernini Studio</h1><p class="muted">Выбери MP4 и фотографию. Одной кнопкой загрузим их в R2 и отправим на генерацию. Результат можно скачать здесь же.</p>
<form action="/prepare" method="post" enctype="multipart/form-data" id="form"><label>🎬 Исходное видео (MP4)</label><input type="file" name="video" accept=".mp4,video/mp4" required>
<label>🖼️ Фото для замены головы (JPG/PNG)</label><input type="file" name="reference" accept=".jpg,.jpeg,.png,image/jpeg,image/png" required>
<div class="notice">⏱ Длительность определяется автоматически из MP4. Генерируется весь ролик в 16 FPS. Длинные видео обрабатываются частями, без обрезки по первым 17/81 кадрам. Защитный лимит — 10 минут; длинные задания могут быть дорогими.</div>
<button type="submit">Загрузить и запустить генерацию</button><div id="status" role="status"></div></form>
<div class="notice">🔒 Доступы к R2 и Vast хранятся только локально. Для запуска нужен настроенный Vast Serverless endpoint. Результат хранится в приватном R2; рекомендуемый срок автоудаления — 7 дней.</div>
</main><script>document.getElementById('form').addEventListener('submit',()=>{document.getElementById('status').textContent='Подготавливаю файлы, подожди…';});</script></body></html>'''


def parse_multipart(body, content_type):
    msg = BytesParser(policy=default).parsebytes(b'Content-Type: ' + content_type.encode('ascii') + b'\r\nMIME-Version: 1.0\r\n\r\n' + body)
    if not msg.is_multipart():
        raise ValueError('Нужна multipart/form-data форма')
    values = {}
    for part in msg.iter_parts():
        disposition = part.get('Content-Disposition', '')
        match = re.search(r'(?:^|;)\s*name="([^"]+)"', disposition)
        if not match:
            continue
        name = match.group(1)
        values[name] = (part.get_filename(), part.get_payload(decode=True))
    return values


PROGRESS_HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bernini · Генерация</title><style>body{font:16px system-ui;background:#0d1018;color:#e9ecf5;max-width:680px;margin:55px auto;padding:20px}main{background:#171b27;border:1px solid #333a4c;border-radius:18px;padding:26px}h1{margin-top:0}progress{width:100%;height:23px;accent-color:#8a72f8}a,button{display:inline-block;color:white;background:#8a72f8;border:0;border-radius:9px;padding:13px 18px;margin:12px 8px 0 0;text-decoration:none;font:600 15px system-ui;cursor:pointer}.muted{color:#aab4c5}#error{color:#ffacac}</style></head><body><main><h1>Bernini · Генерация</h1><p id="status">Ожидаем запуск GPU...</p><progress id="bar" max="100" style="display:none"></progress><p class="muted" id="detail">Во время холодного старта проценты недоступны. Во время сэмплирования показывается процент текущего этапа, а не всего ролика.</p><div id="result"></div><form id="delete" action="/delete-cloud" method="post" style="display:none"><input type="hidden" name="job_id" value="__JOB_ID__"><button type="submit" onclick="return confirm('Безвозвратно удалить исходники и результат из R2?')">Удалить файлы из облака</button></form><p><a href="/">Новое задание</a></p></main><script>
const job='__JOB_ID__';const names={queued:'В очереди',waiting_for_gpu:'Ожидание GPU / холодный старт',downloading:'Загрузка исходников на GPU',loading:'Подготовка ComfyUI и моделей',executing_node:'Выполнение графа ComfyUI',sampling:'Сэмплирование',normalizing:'Подготовка видео 16 FPS',chunk:'Обработка части видео',stitching:'Склейка всех частей',uploading:'Загрузка результата в R2',complete:'Готово',failed:'Ошибка генерации'};
async function poll(){try{let r=await fetch('/api/status/'+job,{cache:'no-store'});if(!r.ok)throw Error('Статус недоступен');let s=await r.json();let pct=Number.isFinite(s.percent)?s.percent:null;let chunk=(s.chunk_index&&s.chunk_total)?' · часть '+s.chunk_index+' из '+s.chunk_total:'';document.getElementById('status').textContent=(names[s.stage]||s.stage||s.state)+chunk+(s.stage==='sampling'&&pct!==null?' — '+pct+'% текущего этапа':'');let bar=document.getElementById('bar');if(s.stage==='sampling'&&pct!==null){bar.style.display='block';bar.value=pct;}else{bar.style.display='none';}if(s.state==='complete'&&s.download_ready){let a=document.createElement('a');a.href='/result/'+job;a.textContent='⬇ Скачать готовое MP4';document.getElementById('result').replaceChildren(a);document.getElementById('delete').style.display='block';return;}if(s.state==='failed'){document.getElementById('detail').textContent=s.message||'Проверь логи Vast worker.';document.getElementById('delete').style.display='block';return;}}catch(e){document.getElementById('detail').textContent='Временная ошибка проверки статуса: '+e.message;}setTimeout(poll,3000)}poll();
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, content, content_type='text/html; charset=utf-8', headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            return self.respond(200, HTML.encode('utf-8'))
        match = re.fullmatch(r'/api/status/([a-f0-9]{32})', path)
        if match:
            try:
                data = json.dumps(read_status(match.group(1)), ensure_ascii=False).encode('utf-8')
                return self.respond(200, data, 'application/json; charset=utf-8')
            except Exception:
                return self.respond(404, b'{"error":"not_found"}', 'application/json')
        match = re.fullmatch(r'/result/([a-f0-9]{32})', path)
        if match:
            job_id = match.group(1)
            with TASKS_LOCK:
                known = job_id in TASKS
            if not known:
                return self.respond(404, b'Unknown job', 'text/plain')
            try:
                client, bucket = r2_client()
                key = f'jobs/{job_id}/result.mp4'
                client.head_object(Bucket=bucket, Key=key)
                url = client.generate_presigned_url('get_object', Params={
                    'Bucket': bucket, 'Key': key,
                    'ResponseContentDisposition': 'attachment; filename="bernini-result.mp4"'
                }, ExpiresIn=900)
                self.send_response(302)
                self.send_header('Location', url)
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            except Exception:
                return self.respond(404, b'Result not found', 'text/plain')
        match = re.fullmatch(r'/download/([a-f0-9]{32})', path)
        if match:
            filename = JOBS / match.group(1) / 'bernini_job.zip'
            if filename.is_file():
                return self.respond(200, filename.read_bytes(), 'application/zip', {'Content-Disposition': 'attachment; filename="bernini_job.zip"'})
        self.respond(404, b'Not found', 'text/plain')

    def do_POST(self):
        if urlparse(self.path).path == '/delete-cloud':
            try:
                n = int(self.headers.get('Content-Length', '-1'))
                if n < 0 or n > 4096: raise ValueError('Invalid body')
                fields = parse_qs(self.rfile.read(n).decode('utf-8'))
                job_id = fields.get('job_id', [''])[0]
                if not JOB_RE.fullmatch(job_id): raise ValueError('Invalid job')
                with TASKS_LOCK:
                    if job_id not in TASKS: raise ValueError('Unknown job')
                status = read_status(job_id)
                if status.get('state') not in ('complete', 'failed'):
                    raise ValueError('Нельзя удалять файлы во время генерации')
                deleted = delete_cloud(job_id)
                with TASKS_LOCK: TASKS.pop(job_id, None)
                return self.respond(200, f'<html lang="ru"><meta charset="utf-8"><body style="font:18px system-ui;background:#111;color:white;padding:40px"><h2>Удалено объектов: {deleted}</h2><a style="color:#b5a8ff" href="/">Новое задание</a></body></html>'.encode('utf-8'))
            except Exception as e:
                return self.respond(400, f'Ошибка удаления: {escape(str(e))}'.encode('utf-8'))
        if urlparse(self.path).path == '/upload-r2':
            try:
                n = int(self.headers.get('Content-Length', '-1'))
                if n < 0 or n > 4096: raise ValueError('Неверный запрос')
                fields = parse_qs(self.rfile.read(n).decode('utf-8'))
                job_id = fields.get('job_id', [''])[0]
                if not re.fullmatch(r'[a-f0-9]{32}', job_id): raise ValueError('Неверный ID задания')
                folder = JOBS / job_id
                if not (folder / 'workflow_api.json').is_file(): raise ValueError('Задание не найдено')
                extra_settings()  # fail before uploading if Vast is not configured
                names = upload_to_r2(folder, job_id)
                benchmark_id, created = ensure_benchmark_from_upload(folder)
                # Vast benchmarks run before the endpoint can serve jobs.
                # Never submit a paid GPU request until the endpoint's private
                # BERNINI_BENCHMARK_JOB_ID has been configured by the owner.
                configured_id = (ROOT / 'benchmark_configured.txt')
                if not configured_id.exists() or configured_id.read_text(encoding='ascii').strip() != benchmark_id:
                    response = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><body style="background:#0d1018;color:#e9ecf5;font:17px system-ui;max-width:700px;margin:70px auto;padding:24px"><h2>Файлы загружены в R2 ✓</h2><p>Отдельный 17-кадровый benchmark подготовлен автоматически. GPU ещё не запускался.</p><p>Один раз добавь в <b>Vast.ai → Environment Variables</b> переменную:</p><pre style="white-space:pre-wrap;background:#252c3d;padding:16px">BERNINI_BENCHMARK_JOB_ID={benchmark_id}</pre><p>После сохранения переменной создай в папке интерфейса файл <code>benchmark_configured.txt</code> с этим ID на единственной строке. Это подтверждение, что Vast настроен.</p><p>Затем снова отправь задание через интерфейс. Существующий job сохранён в R2.</p><p><a style="color:#b5a8ff" href="/">Вернуться</a></p></body></html>'''
                    return self.respond(200, response.encode('utf-8'))
                with TASKS_LOCK:
                    TASKS[job_id] = {'state': 'queued', 'stage': 'waiting_for_gpu'}
                threading.Thread(target=launch_vast, args=(job_id,), daemon=True).start()
                response = PROGRESS_HTML.replace('__JOB_ID__', job_id)
                return self.respond(200, response.encode('utf-8'))
            except Exception as e:
                # Never display credentials or full S3 exception details in browser.
                msg = 'Не удалось загрузить в R2. Проверь Account ID, ключи, bucket и разрешения. Подробности смотри в консоли без публикации ключей.'
                if isinstance(e, ValueError): msg = str(e)
                print('R2 upload error type:', type(e).__name__)
                return self.respond(400, f'<html lang="ru"><meta charset="utf-8"><body><h2>{escape(msg)}</h2><a href="/">Назад</a></body></html>'.encode('utf-8'))
        if self.path != '/prepare':
            return self.respond(404, b'Not found', 'text/plain')
        try:
            n = int(self.headers.get('Content-Length', '-1'))
            if n < 0 or n > MAX_BODY:
                raise ValueError('Файлы слишком большие (максимум 350 МБ на запрос)')
            content_type = self.headers.get('Content-Type', '')
            if not content_type.lower().startswith('multipart/form-data'):
                raise ValueError('Неверный тип формы')
            parts = parse_multipart(self.rfile.read(n), content_type)
            for name in ('video', 'reference'):
                if name not in parts:
                    raise ValueError(f'Не заполнено поле {name}')
            vname, video = parts['video']
            rname, ref = parts['reference']
            if not vname or Path(vname).suffix.lower() != '.mp4' or not video or b'ftyp' not in video[:32]:
                raise ValueError('Выбери корректный MP4-файл')
            ext = Path(rname or '').suffix.lower()
            if ext not in ('.jpg', '.jpeg', '.png') or not ref:
                raise ValueError('Выбери JPG или PNG')
            if ext == '.png' and not ref.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('PNG-файл повреждён')
            if ext in ('.jpg', '.jpeg') and not ref.startswith(b'\xff\xd8\xff'):
                raise ValueError('JPG-файл повреждён')
            try:
                with Image.open(BytesIO(ref)) as photo:
                    photo = ImageOps.exif_transpose(photo)
                    if photo.width * photo.height > 60_000_000:
                        raise ValueError('Фото слишком большое')
                    converted = BytesIO()
                    photo.convert('RGB').save(converted, 'JPEG', quality=95)
                    ref = converted.getvalue()
            except (UnidentifiedImageError, OSError):
                raise ValueError('Не удалось прочитать фотографию')
            ext = '.jpg'
            job_id = uuid.uuid4().hex
            folder = JOBS / job_id
            folder.mkdir(parents=True)
            (folder / 'source.mp4').write_bytes(video)
            video_info = inspect_video(folder / 'source.mp4')
            (folder / 'video_info.json').write_text(json.dumps(video_info, ensure_ascii=False, indent=2), encoding='utf-8')
            # The GPU worker re-counts exact frames after normalizing to 16fps.
            frames = max(17, 1 + 4 * ((min(video_info['estimated_frames'], 81) - 1 + 3) // 4))
            (folder / ('reference' + ext)).write_bytes(ref)
            workflow = json.loads((ROOT / 'workflow_api_external_reference.json').read_text(encoding='utf-8'))
            workflow['5']['inputs']['length'] = frames
            workflow['21']['inputs']['frame_load_cap'] = frames
            workflow['21']['inputs']['video'] = 'source.mp4'
            # External LoadImage overrides Bernini's internal reference slot.
            image_nodes = [k for k, val in workflow.items() if val.get('class_type') == 'LoadImage']
            if len(image_nodes) != 1:
                raise ValueError('Шаблон не содержит единственного узла LoadImage')
            workflow[image_nodes[0]]['inputs']['image'] = 'reference' + ext
            (folder / 'workflow_api.json').write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding='utf-8')
            (folder / 'IMPORTANT.txt').write_text('Automatic full-video mode: 16fps, chunking on GPU, final duration verification. The workflow is a per-chunk template, not a complete one-shot video.\n', encoding='utf-8')
            with zipfile.ZipFile(folder / 'bernini_job.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                for name in ('source.mp4', 'reference' + ext, 'workflow_api.json', 'video_info.json', 'IMPORTANT.txt'):
                    archive.write(folder / name, name)
            # One click: the browser immediately submits the prepared job to R2.
            response = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><body style="background:#0d1018;color:#e9ecf5;font:17px system-ui;max-width:650px;margin:80px auto;padding:20px"><h2>Видео {video_info['duration_seconds']} сек · ~{video_info['estimated_frames']} кадров при 16 FPS</h2><p>Подготовлено. Загружаем в R2 и запускаем GPU...</p><p>Job ID: <code>{job_id}</code></p><p><a style="color:#b5a8ff" href="/download/{job_id}">Скачать ZIP задания</a></p><form id="next" action="/upload-r2" method="post"><input type="hidden" name="job_id" value="{job_id}"><button type="submit">Повторить отправку, если переход не сработал</button></form><script>document.getElementById('next').submit();</script></body></html>'''
            return self.respond(200, response.encode('utf-8'))
        except Exception as e:
            error = escape(str(e))
            return self.respond(400, f'<html lang="ru"><meta charset="utf-8"><body><h2>Ошибка: {error}</h2><a href="/">Назад</a></body></html>'.encode('utf-8'))


if __name__ == '__main__':
    JOBS.mkdir(exist_ok=True)
    print(f'Bernini UI: http://{HOST}:{PORT}/')
    print('Vast generation requires a configured endpoint. Press Ctrl+C to stop.')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
