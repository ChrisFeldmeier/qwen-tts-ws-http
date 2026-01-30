# Qwen-TTS-WS-HTTP

Dieses Projekt kapselt die Echtzeit-WebSocket-Schnittstelle von Alibaba Cloud DashScope Qwen-TTS in eine benutzerfreundliche HTTP-Schnittstelle. Es unterstützt sowohl den Download von Standard-Audiodateien als auch SSE (Server-Sent Events) für Streaming-Audio.

## Funktionen

- **Einfacher HTTP POST**: Komplette Audiodatei auf einmal abrufen (automatisch als WAV-Format verpackt).
- **SSE Streaming-Unterstützung**: Echtzeit-Übertragung von Audio-Fragmenten (Base64-kodiertes PCM) für reduzierte Latenz.
- **Flexible Speicheroptionen**: Unterstützung für lokale Speicherung oder Upload zu S3-kompatiblen Speicherdiensten (z.B. AWS S3, Minio).
- **Flexible Rückgabeoptionen**: Direkte Rückgabe von Audio-Binärdaten oder einer Zugriffs-URL nach Speicherung.
- **Automatische Formatkonvertierung**: Interne Umwandlung von PCM zu WAV für direkte Wiedergabe.
- **Gesundheitsprüfung**: `/health` Endpunkt für Service-Monitoring.

## Voraussetzungen

- Python 3.13+
- Alibaba Cloud DashScope API Key

## Installation

1. Projekt lokal klonen.
2. Abhängigkeiten installieren:
   ```bash
   pip install dashscope fastapi uvicorn
   # Oder mit dem mitgelieferten uv (empfohlen)
   uv sync
   ```

## Konfiguration

Das Projekt verwendet [dynaconf](https://www.dynaconf.com/) für die Konfigurationsverwaltung. Die Konfiguration kann auf folgende Weisen erfolgen:

### 1. Konfigurationsdatei

Im Projektverzeichnis kann `settings.yaml` für nicht-sensible Informationen verwendet werden:

```yaml
default:
  dashscope:
    url: "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
  server:
    host: "0.0.0.0"
    port: 9999
  enableSave: true # Ob synthetisiertes Audio gespeichert werden soll
  storageType: "local" # Speichertyp: local oder s3
  outputDir: "./output" # Lokales Speicherverzeichnis

  # S3 Speicherkonfiguration (erforderlich wenn storageType s3 ist)
  s3:
    bucket: "your-bucket-name"
    endpoint: "http://localhost:9000" # S3-Service-Adresse
    region: "us-west-1"
    publicUrlPrefix: "" # Optional, benutzerdefinierter Domain-Präfix
    urlType: "public" # Link-Typ: public oder private
    expiresIn: 3600 # Gültigkeitsdauer für private Links (Sekunden)
```

Sensible Informationen (wie API Keys) sollten in `.secrets.yaml` gespeichert werden (diese Datei wird von `.gitignore` ignoriert):

```yaml
dashscope_api_key: "IHR_DASHSCOPE_API_KEY"
# S3-Schlüssel können auch hier gespeichert werden
s3:
  accessKeyId: "..."
  accessKeySecret: "..."
```

### 2. Umgebungsvariablen

Konfigurationsoptionen können auch über Umgebungsvariablen gesetzt werden. Das Standard-Präfix ist `DYNACONF_` (sofern nicht anders konfiguriert). Für bestimmte sensible Informationen wird auch direktes Auslesen unterstützt:

- `DASHSCOPE_API_KEY`: Alibaba Cloud DashScope API Key.

Für andere Konfigurationsoptionen siehe das Namensformat in der [dynaconf-Dokumentation](https://www.dynaconf.com/envvars/). Beispiel für das Setzen des Server-Ports:
```bash
export DYNACONF_SERVER__PORT=9001
```

## Ausführung

Folgenden Befehl ausführen, um den Service zu starten:

```bash
python main.py
```

Der Service lauscht standardmäßig auf `0.0.0.0:9999`.

## API-Dokumentation

### 1. Text-zu-Sprache (WAV-Datei zurückgeben)

Konvertiert Text in eine vollständige WAV-Audiodatei.

- **URL**: `/tts`
- **Methode**: `POST`
- **Content-Type**: `application/json`

**Request-Body**:

| Feld | Typ | Erforderlich | Standardwert | Beschreibung |
| :--- | :--- | :--- | :--- |:--- |
| `text` | string | Ja | - | Der zu synthetisierende Text |
| `model` | string | Ja | - | Modellname. Details siehe: [Echtzeit-Sprachsynthese-Qwen](https://help.aliyun.com/zh/model-studio/qwen-tts-realtime) |
| `voice` | string | Nein | `Cherry` | Gewählte Stimme |
| `language_type` | string | Nein | `Auto` | Sprachtyp. Optionen: `Auto`, `Chinese`, `English`, `German`, `Italian`, `Portuguese`, `Spanish`, `Japanese`, `Korean`, `French`, `Russian` |
| `sample_rate` | integer | Nein | `24000` | Audio-Abtastrate (Hz). Übliche Werte: 8000, 16000, 24000, 48000 |
| `speech_rate` | float | Nein | `1.0` | Sprechgeschwindigkeit, Bereich: [0.5, 2.0] |
| `volume` | float | Nein | `50` | Lautstärke, Bereich: [0, 100] |
| `pitch_rate` | float | Nein | `1.0` | Tonhöhe, Bereich: [0.5, 2.0] |
| `return_url` | boolean | Nein | `false` | Ob eine Audio-URL statt Binärdaten zurückgegeben werden soll (erfordert aktivierte Speicherfunktion) |

**Beispiel-Request (cURL - Binärdaten zurückgeben)**:

```bash
curl -X POST http://localhost:9999/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hallo, willkommen beim Qwen Sprachsynthese-Service.",
    "model": "qwen3-tts-flash-realtime",
    "voice": "Cherry"
  }' --output output.wav
```

**Beispiel-Request (cURL - URL zurückgeben)**:

```bash
curl -X POST http://localhost:9999/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hallo, willkommen beim Qwen Sprachsynthese-Service.",
    "model": "qwen3-tts-flash-realtime",
    "return_url": true
  }'
```

**Beispiel-Antwort (JSON)**:
```json
{
  "url": "http://localhost:9999/output/xxxx.wav"
}
```

### 2. Streaming Text-zu-Sprache (SSE)

Echtzeit-Abruf von Audio-Fragmenten über das SSE-Protokoll.

- **URL**: `/tts_stream`
- **Methode**: `POST`
- **Content-Type**: `application/json`

**Request-Body**: Wie oben.

**Beispiel-Request (cURL)**:

```bash
curl -X POST http://localhost:9999/tts_stream \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hallo, dies ist ein Streaming-Ausgabe-Test.",
    "model": "qwen3-tts-flash-realtime",
    "voice": "Cherry"
  }'
```

**Beispiel-Antwort**:

```text
data: {"audio": "...", "is_end": false}
data: {"audio": "...", "is_end": false}
...
data: {"is_end": true, "url": "...", "usage_characters": "12"}
```
*Hinweis: Das `audio`-Feld enthält Base64-kodierte PCM-Daten (24000Hz, Mono, 16bit). Wenn die Speicherfunktion aktiviert ist, enthält die letzte Nachricht die `url` der Audiodatei. `usage_characters` gibt die Anzahl der verbrauchten Zeichen für diese Synthese an.*

### 3. Gesundheitsprüfung

- **URL**: `/health`
- **Methode**: `GET`

**Antwort**: `{"status": "ok"}`

## Response-Header

Bei der Antwort des `/tts`-Endpunkts werden folgende benutzerdefinierte Header mitgeliefert:
- `X-Session-Id`: Session-ID dieser Synthese.
- `X-First-Audio-Delay`: Latenz bis zum ersten Audio-Paket (Millisekunden).
- `X-Usage-Characters`: Anzahl der verbrauchten Zeichen für diese Synthese.
- `Content-Type`: `audio/wav` (bei Binärdaten-Rückgabe) oder `application/json` (bei URL-Rückgabe).
