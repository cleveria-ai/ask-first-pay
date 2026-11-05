# Entendido (tarea C1, rama claude/ask-first-pay-webhooks-video-xjlz0e, base n5-judge feaaa6c)

Foco: hackathon-paypal#entrega. Objetivo superior: llevar la entrada hasta el último punto que se
puede hacer en código, para que el operador solo tenga que grabar, correr en vivo y publicar.

## (a) La tarea en mis palabras

1. Cerrar las dos debilidades de código que JUDGE_REVIEW.md deja abiertas:
   - Webhooks: un receptor `POST /webhooks/paypal` que verifica la firma de PayPal
     (formato real: `transmission_id|transmission_time|webhook_id|crc32(body)`, SHA256withRSA,
     certificado de `paypal-cert-url`) con el certificado servido por un doble local; un simulador
     local que emite eventos firmados; `CHECKOUT.ORDER.APPROVED` reemplaza al «I paid» del cliente.
     El webhook nunca mueve dinero: a lo sumo dispara la retención (authorize).
   - Persistencia opcional en SQLite (`ASK_FIRST_DB`), con `shop_id`, para que reiniciar no
     borre reservas, mandatos aprobados ni el conjunto de mandatos ya usados (un reinicio no puede
     reabrir un replay).
   Sin cambiar el contrato del mandato firmado (libs/, gate.py, ports.py intactos).
2. Recursos del video: `scripts/record_demo.py` (Chromium sin cabeza 1280x720, un .webm por toma
   en docs/video/raw/), `docs/video/subtitles.srt`, `docs/video/SHOTLIST.md` (total <= 180 s y
   lista previa a grabar).
3. Re-puntuar con la rúbrica en docs/JUDGE_REVIEW_N6.md (antes/después con evidencia).

## (b) Criterios y comando de cada uno

| # | Criterio | Comando | Salida esperada |
|---|---|---|---|
| 1 | Suite verde con más de 116 pruebas | `.venv/bin/python -m pytest -q \| tail -1` | `N passed` con N > 116, sin `failed` |
| 2 | demo.sh arranca sin llaves | `env -u ANTHROPIC_API_KEY -u PAYPAL_CLIENT_ID bash scripts/demo.sh & sleep 8; curl -s 127.0.0.1:8000/healthz` | `{"ok":true}` |
| 3 | Existen SHOTLIST.md y subtitles.srt | `test -f docs/video/SHOTLIST.md && test -f docs/video/subtitles.srt && echo ok` | `ok` |
| 4 | Suma del shotlist <= 180 s (y srt coherente) | `.venv/bin/python scripts/check_video_assets.py` | `OK total ... s <= 180` |
| 5 | Receptor de webhooks verificado | `.venv/bin/python -m pytest -q tests/paypal/test_paypal_webhooks.py tests/demo/test_demo_webhooks.py` | verde |
| 6 | Persistencia SQLite | `.venv/bin/python -m pytest -q tests/demo/test_demo_store.py` | verde |
| 7 | record_demo.py probado en seco | `.venv/bin/python scripts/record_demo.py --dry-run` | sale 0 y lista las 9 tomas |
| 8 | JUDGE_REVIEW_N6.md con antes/después | `grep -c '^| \*\*Total' docs/JUDGE_REVIEW_N6.md` | `1` |
| 9 | Contrato del mandato sin cambios | `git diff --stat feaaa6c -- libs/ src/ask_first_pay/gate.py src/ask_first_pay/ports.py \| wc -l` | `0` |

## (c) Lo que no haré

- No cambio pyproject.toml ni agrego dependencias al proyecto (playwright solo en el entorno).
- No toco libs/ask-first-mandate, gate.py ni ports.py (contrato del mandato).
- No llamo a PayPal, Anthropic ni a ninguna red real; la corrida en vivo es del operador.
- No grabo con voz ni publico el video; no abro PR; no fusiono.
- No leo .env ni credenciales, ni docs/legal, docs/operations, docs/strategy/meta-onboarding.

## Medición inicial

| # | Resultado |
|---|---|
| 1 | falla: `116 passed, 1 deselected` (no supera 116) |
| 2 | pasa: `{"ok":true}`, offline scripted model + FakeProvider |
| 3 | falla: no existe docs/video |
| 4 | falla: no existe el script ni el shotlist |
| 5 | falla: no existen las pruebas |
| 6 | falla: no existen las pruebas |
| 7 | falla: no existe el script |
| 8 | falla: no existe el archivo |
| 9 | pasa: 0 líneas |

d inicial = 7/9 = 0.78

## Búsquedas antes de crear

- `grep -rni "webhook\|sqlite"` en src, tests, scripts, docs: solo menciones en JUDGE_REVIEW.md:92
  y DEVPOST.md:103 (trabajo pendiente). No hay receptor, simulador ni almacén que mejorar.
- Doble HTTP de PayPal existente: tests/paypal/fakepaypal.py (para el adaptador REST); el
  webhook no pasa por el adaptador, así que el doble de certificado es nuevo.
- docs/video no existe; VIDEO_SCRIPT.md es la fuente del guion (se reutiliza, no se duplica).
