# Qwen-TTS-WS-HTTP

Dieses Projekt kapselt die Echtzeit-WebSocket-Schnittstelle von Alibaba Cloud DashScope Qwen-TTS in eine benutzerfreundliche HTTP-Schnittstelle. Es unterstützt Standard-TTS, Voice Design (Stimme aus Beschreibung) und Voice Cloning (Stimme aus Audio).

## Funktionen

- **Einfacher HTTP POST**: Komplette Audiodatei auf einmal abrufen (automatisch als WAV-Format verpackt).
- **SSE Streaming-Unterstützung**: Echtzeit-Übertragung von Audio-Fragmenten (Base64-kodiertes PCM) für reduzierte Latenz.
- **Voice Design**: Erstelle benutzerdefinierte Stimmen aus Textbeschreibungen.
- **Voice Cloning**: Klone Stimmen aus Audio-Samples (10-20 Sekunden).
- **Web-Frontend**: Integriertes HTML-Frontend zum Testen aller Funktionen im Browser.
- **Flexible Speicheroptionen**: Unterstützung für lokale Speicherung oder Upload zu S3-kompatiblen Speicherdiensten.
- **Download nach Streaming**: WAV-Dateien können nach dem Streaming heruntergeladen werden.

## Voraussetzungen

- Python 3.10+
- Alibaba Cloud DashScope API Key (International: [dashscope-intl.aliyuncs.com](https://dashscope-intl.aliyuncs.com))

## Installation

1. Projekt lokal klonen.
2. Abhängigkeiten installieren:
   ```bash
   pip install dashscope fastapi uvicorn python-multipart dynaconf boto3 requests
   ```

## Konfiguration

### Konfigurationsdatei

Im Projektverzeichnis `settings.yaml` erstellen:

```yaml
default:
  dashscope:
    url: "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"
  server:
    host: "0.0.0.0"
    port: 9999
  enableSave: true
  storageType: "local"
  outputDir: "./output"
```

API Key in `.secrets.yaml` speichern:

```yaml
dashscope_api_key: "sk-xxxxxxxxxxxxxxxx"
```

## Ausführung

```bash
python main.py
```

Der Service läuft auf `http://localhost:9999`. Öffne `http://localhost:9999/index.html` für das Web-Frontend.

---

## API-Dokumentation

### Standard TTS

#### POST `/tts` - Vollständige WAV-Datei

```bash
curl -X POST http://localhost:9999/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hallo Welt", "model": "qwen3-tts-flash-realtime", "voice": "Chelsie"}' \
  --output output.wav
```

#### POST `/tts_stream` - SSE Streaming

```bash
curl -X POST http://localhost:9999/tts_stream \
  -H "Content-Type: application/json" \
  -d '{"text": "Streaming Test", "model": "qwen3-tts-flash-realtime", "voice": "Chelsie"}'
```

**Parameter:**

| Feld | Typ | Standard | Beschreibung |
|------|-----|----------|--------------|
| `text` | string | - | Zu synthetisierender Text |
| `model` | string | - | Modellname (z.B. `qwen3-tts-flash-realtime`) |
| `voice` | string | `Cherry` | Stimmenname (siehe unten) |
| `language_type` | string | `Auto` | Sprache: Auto, German, English, Chinese, etc. |
| `sample_rate` | int | `24000` | Abtastrate in Hz |
| `speech_rate` | float | `1.0` | Geschwindigkeit [0.5-2.0] |
| `pitch_rate` | float | `1.0` | Tonhöhe [0.5-2.0] |
| `volume` | float | `50` | Lautstärke [0-100] |

---

### Voice Design

Erstelle benutzerdefinierte Stimmen aus Textbeschreibungen.

**Modell:** `qwen3-tts-vd-realtime-2025-12-16`

#### POST `/voice_design/create` - Stimme erstellen

```bash
curl -X POST http://localhost:9999/voice_design/create \
  -H "Content-Type: application/json" \
  -d '{
    "voice_prompt": "A calm, professional German male voice, around 35 years old, with a deep pitch.",
    "preview_text": "Hello, this is a test of the voice.",
    "preferred_name": "narrator",
    "language": "en"
  }'
```

**Antwort:**
```json
{
  "success": true,
  "voice": "qwen-tts-vd-narrator-voice-20260130...",
  "preview_audio": "UklGRi4A...",
  "target_model": "qwen3-tts-vd-realtime-2025-12-16"
}
```

#### GET `/voice_design/list` - Stimmen auflisten

```bash
curl http://localhost:9999/voice_design/list
```

#### DELETE `/voice_design/{voice_name}` - Stimme löschen

```bash
curl -X DELETE http://localhost:9999/voice_design/voice-id-here
```

#### POST `/tts_vd_stream` - TTS mit Voice Design Stimme

```bash
curl -X POST http://localhost:9999/tts_vd_stream \
  -H "Content-Type: application/json" \
  -d '{"text": "Hallo Welt", "voice": "qwen-tts-vd-narrator-voice-..."}'
```

---

### Voice Cloning

Klone Stimmen aus Audio-Samples. Kosten: $0.01 pro Stimme (1000 gratis).

**Modell:** `qwen3-tts-vc-realtime-2026-01-15`

#### POST `/voice_cloning/create` - Stimme klonen

```bash
curl -X POST http://localhost:9999/voice_cloning/create \
  -H "Content-Type: application/json" \
  -d '{
    "audio_base64": "UklGRi4A...",
    "audio_mime_type": "audio/wav",
    "preferred_name": "meinestimme",
    "language": "de"
  }'
```

**Audio-Anforderungen:**
- Dauer: 10-20 Sekunden (max 60)
- Format: WAV, MP3, M4A
- Qualität: Min. 24 kHz, Mono
- Inhalt: Klare Sprache, keine Hintergrundgeräusche
- Größe: Max 10 MB

**Antwort:**
```json
{
  "success": true,
  "voice": "qwen-tts-vc-meinestimme-voice-20260130...",
  "target_model": "qwen3-tts-vc-realtime-2026-01-15"
}
```

#### GET `/voice_cloning/list` - Geklonte Stimmen auflisten

```bash
curl http://localhost:9999/voice_cloning/list
```

#### DELETE `/voice_cloning/{voice_name}` - Geklonte Stimme löschen

```bash
curl -X DELETE http://localhost:9999/voice_cloning/voice-id-here
```

#### POST `/tts_vc_stream` - TTS mit geklonter Stimme

```bash
curl -X POST http://localhost:9999/tts_vc_stream \
  -H "Content-Type: application/json" \
  -d '{"text": "Hallo mit meiner geklonten Stimme", "voice": "qwen-tts-vc-meinestimme-voice-..."}'
```

---

### Gesundheitsprüfung

```bash
curl http://localhost:9999/health
# {"status": "ok"}
```

---

## Web-Frontend

Öffne `http://localhost:9999/index.html` im Browser für das integrierte Test-Frontend mit:

- **TTS Tab**: Standard Text-to-Speech mit 49 vordefinierten Stimmen
- **Design Tab**: Voice Design - Stimme aus Beschreibung erstellen
- **Cloning Tab**: Voice Cloning - Stimme aus Audio klonen
- **Stimmen Tab**: Verwaltung und Verwendung erstellter Stimmen

Features:
- Echtzeit-Streaming mit Visualisierung
- Direkt im Browser abspielen
- WAV-Download nach Streaming
- Stopp-Funktion während der Wiedergabe

---

## Verfügbare Stimmen (Standard TTS)

### Englisch
Chelsie, Ethan, Serena, Aura, Stella, Cherry, Nova, Aria, Maple

### Chinesisch
龙小淳, 龙小夏, 龙小诚, 龙小白, 龙老铁, 龙二叔, 龙梆梆, 龙家琪, 龙果果, 龙思琪, 龙飞船, 龙马仕, 龙小天, 龙妍妍, 龙悦悦, 龙芊芊, 龙清然, 龙嘤嘤, 龙千千, 龙小萌, 龙青松

### Mehrsprachig
Camilla (DE/EN), Farah (AR), Layla (AR), Tarik (AR), Lisa (FR), Remy (FR), Luisa (DE), Vivi (ID), Kenzo (ID), Amelia (JA), Haruto (JA), Dahlia (KO), Minho (KO), Aurora (PT), Miguel (PT), Bella (RU), Ivan (RU), Lucia (ES), Carlos (ES)

---

## Modelle

| Modell | Beschreibung | Kosten |
|--------|--------------|--------|
| `qwen3-tts-flash-realtime` | Standard TTS (schnell) | $0.05/10k Zeichen |
| `qwen3-tts-vd-realtime-2025-12-16` | Voice Design TTS | $0.13/10k Zeichen |
| `qwen3-tts-vc-realtime-2026-01-15` | Voice Cloning TTS | $0.13/10k Zeichen |
| `qwen-voice-design` | Voice Design erstellen | $0.20/Stimme |
| `qwen-voice-enrollment` | Voice Cloning erstellen | $0.01/Stimme |

---

## Lizenz

MIT License
