# Деплой на удалённый VPS (доступ по IP)

Гайд для запуска полного стенда (frontend + API + redis + searxng + meilisearch,
со всеми 4 источниками включая Ozon) на удалённом VPS с доступом по `http://IP:5173`.

## 0. Что мы запускаем и какие порты

`docker/docker-compose.yml` поднимает 5 контейнеров, все с `network_mode: host`
(порты биндятся прямо на хост, без проброса):

| Сервис      | Порт  | Наружу? |
|-------------|-------|---------|
| frontend (nginx) | 5173 | **да** — единственный публичный порт |
| api (FastAPI)    | 8000 | нет (фронт ходит через nginx `/api/`) |
| redis            | 6379 | **нет, закрыть** (без пароля!) |
| searxng          | 8080 | нет, закрыть |
| meilisearch      | 7700 | нет (и так слушает только 127.0.0.1) |

Фронтенд обращается к API по относительному пути `/api/...`, nginx проксирует на
`127.0.0.1:8000`. Поэтому **наружу достаточно открыть только 5173** — менять код
или адрес API не нужно, всё работает на любом IP/домене автоматически.

> ⚠️ Из-за `network_mode: host` redis (6379) и searxng (8080) по умолчанию слушают
> на всех интерфейсах. Redis — без пароля. На публичном VPS это дыра, поэтому
> **firewall (шаг 4) обязателен**.

## 1. Требования к VPS

- Ubuntu/Debian, **2+ CPU, 4+ GB RAM** (Ozon-браузер прожорлив; для комфорта 8 GB).
- Открытый SSH-доступ (root или sudo).
- Если планируете Ozon — нужен дисплей для браузера. По умолчанию используется
  виртуальный Xvfb прямо в контейнере (см. шаг 6).

## 2. Подготовка сервера

```bash
# Подключаемся
ssh root@<IP>

# Docker + compose plugin (официальный скрипт)
curl -fsSL https://get.docker.com | sh
docker compose version   # проверка, что плагин на месте

# git
apt-get update && apt-get install -y git
```

## 3. Доставка проекта на VPS

```bash
git clone https://github.com/IR630/tender_hack.git
cd tender_hack
```

Файл `.env` **не лежит в git** (в нём боевые креды прокси), поэтому переносим его
вручную с локальной машины:

```bash
# с ЛОКАЛЬНОЙ машины, из корня проекта
scp .env root@<IP>:/root/tender_hack/.env
```

Затем на VPS убедитесь, что в `.env` включены все источники (добавьте строку, если её нет):

```env
SEARCH_ENABLED_SOURCES=wildberries,yandex_market,other,ozon
WB_PROXY=pool.proxy.market:10000@<user>:<pass>   # должен остаться из вашего .env
```

> Без `WB_PROXY` Wildberries почти наверняка упрётся в rate-limit/блок с IP сервера.
> Прокси обязателен.

## 4. Firewall — ОБЯЗАТЕЛЬНО

Открываем только SSH и фронтенд, остальное закрываем:

```bash
apt-get install -y ufw
ufw allow 22/tcp        # SSH (не потеряйте доступ!)
ufw allow 5173/tcp      # фронтенд
ufw deny 6379/tcp       # redis
ufw deny 8000/tcp       # api
ufw deny 8080/tcp       # searxng
ufw enable
ufw status
```

Если у провайдера есть внешняя security group / firewall в панели — продублируйте
там же: открыт только 22 и 5173.

## 5. Запуск

```bash
cd /root/tender_hack
# фоновый запуск с пересборкой образов
docker compose -f docker/docker-compose.yml up --build -d

# логи
docker compose -f docker/docker-compose.yml logs -f api
```

Готово — открывайте `http://<IP>:5173` в браузере.

Проверка вручную:

```bash
curl http://127.0.0.1:8000/health           # API жив
curl http://127.0.0.1:5173/api/regions       # фронт→nginx→API
```

## 6. Ozon на VPS (браузер + GPU)

Ozon работает через реальный браузер (nodriver). На сервере без монитора браузеру
нужен дисплей. Реализованы два пути:

**A. Xvfb внутри контейнера (по умолчанию, ничего не настраивать).**
`entrypoint-api.sh` сам поднимает виртуальный дисплей `:99` и запускает браузер в
не-headless режиме. Работает «из коробки», но это софт-рендеринг — Ozon-WAF иногда
может блокировать. Достаточно для демо.

В `docker-compose.yml` уже выставлено `OZON_USE_BROWSER=true` и
`OZON_BROWSER_HEADLESS=false` — отдельно включать не нужно.

**B. Использовать GPU вашего VPS (опционально, чтобы стабильнее проходить WAF).**
GPU сам по себе браузеру не нужен — нужен *реальный* дисплей. Чтобы задействовать
видеокарту, придётся:

1. Поставить драйверы NVIDIA на хост: `apt-get install -y nvidia-driver-535` (или
   версию под вашу карту), `nvidia-smi` должен работать.
2. Поставить `nvidia-container-toolkit`, чтобы пробросить GPU в контейнер:
   ```bash
   apt-get install -y nvidia-container-toolkit
   nvidia-ctk runtime configure --runtime=docker
   systemctl restart docker
   ```
3. Добавить в сервис `api` в `docker/docker-compose.yml`:
   ```yaml
   api:
     # ...
     gpus: all
   ```
4. Дисплей: либо оставить Xvfb (GPU тогда доступен для ML/Ollama, но не для
   рендера X), либо поднять на хосте реальный X-сервер на GPU и пробросить его
   сокет (`/tmp/.X11-unix` уже монтируется в compose) с `DISPLAY=:0`.

> Практический совет для хакатона: начните с пути **A (Xvfb)**. Если Ozon стабильно
> ловит блок — тогда уже занимайтесь GPU/реальным X. GPU заметнее всего поможет, если
> вы локально гоняете Ollama/ML-реранк, а не сам браузер.

## 7. Автозапуск после перезагрузки

В compose нет `restart`-политики. Чтобы стенд поднимался сам после ребута, добавьте
каждому сервису в `docker/docker-compose.yml`:

```yaml
    restart: unless-stopped
```

и Docker включите в автозагрузку: `systemctl enable docker`.

## 8. Обновление версии

```bash
cd /root/tender_hack
git pull
docker compose -f docker/docker-compose.yml up --build -d
```

## Шпаргалка по диагностике

| Симптом | Куда смотреть |
|---|---|
| Сайт не открывается по IP:5173 | `ufw status` (открыт ли 5173), `docker compose ps` |
| Сайт есть, поиск пустой/висит | `docker compose logs -f api` |
| WB не отдаёт результаты | проверь `WB_PROXY` в `.env`, перезапусти api |
| Ozon пусто/блок | логи api по `ozon`, попробуй путь 6B (GPU/реальный X) |
| Redis/searxng торчат наружу | повтори шаг 4 (firewall) |
