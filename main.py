import io
import base64
import json
import os
import queue
import requests
from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, AudioFormat
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from config import settings, logger
from models import TTSRequest
from callbacks import HttpCallback, SSECallback
from utils import init_dashscope_api_key, pcm_to_wav, save_audio


# Voice Design Request Models
class VoiceDesignRequest(BaseModel):
    voice_prompt: str  # Beschreibung der gewünschten Stimme
    preview_text: str  # Text für die Vorschau
    preferred_name: Optional[str] = "custom"  # Name für die Stimme
    language: Optional[str] = "en"  # Sprache: zh, en, de, it, pt, es, ja, ko, fr, ru


class VoiceCloningRequest(BaseModel):
    audio_base64: str  # Base64-kodiertes Audio
    audio_mime_type: Optional[str] = "audio/wav"  # MIME-Type: audio/wav, audio/mpeg, audio/mp4
    preferred_name: Optional[str] = "cloned"  # Name für die Stimme
    language: Optional[str] = None  # Optional: zh, en, de, it, pt, es, ja, ko, fr, ru


class VoiceDesignTTSRequest(BaseModel):
    text: str
    voice: str  # Der von Voice Design generierte Stimmenname
    language_type: Optional[str] = "Auto"
    sample_rate: Optional[int] = 24000
    speech_rate: Optional[float] = 1.0
    volume: Optional[float] = 50
    pitch_rate: Optional[float] = 1.0

app = FastAPI()

# CORS für Browser-Zugriff aktivieren
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure storage
ENABLE_SAVE = settings.get("enableSave", True)
if isinstance(ENABLE_SAVE, str):
    ENABLE_SAVE = ENABLE_SAVE.lower() == "true"

STORAGE_TYPE = settings.get("storageType", "local").lower()
OUTPUT_DIR = settings.get("outputDir", "output")
if ENABLE_SAVE and STORAGE_TYPE == "local":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    # Mount static files to serve saved audio
    app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

# Initialize API key on startup
init_dashscope_api_key()


@app.post("/tts")
async def text_to_speech(request: TTSRequest, http_request: Request):
    logger.info(f"Received TTS request: voice={request.voice}, model={request.model}")
    callback = HttpCallback()

    # Initialize QwenTtsRealtime for each request to ensure isolation
    qwen_tts_realtime = QwenTtsRealtime(
        model=request.model,
        callback=callback,
        url=settings.get('dashscope.url', 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime')
    )

    try:
        logger.debug("Connecting to DashScope...")
        qwen_tts_realtime.connect()
        logger.debug(f"Updating session: voice={request.voice}")
        qwen_tts_realtime.update_session(
            voice=request.voice,
            response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            mode='server_commit',
            format='pcm',
            language_type=request.language_type,
            sample_rate=request.sample_rate,
            pitch_rate=request.pitch_rate,
            speech_rate=request.speech_rate,
            volume=request.volume,
        )

        logger.debug(f"Appending text: {request.text[:50]}...")
        qwen_tts_realtime.append_text(request.text)
        qwen_tts_realtime.finish()

        # Wait for the generation to complete
        logger.debug("Waiting for TTS synthesis to finish...")
        if not callback.wait_for_finished(timeout=60):
            logger.error("TTS synthesis timed out")
            raise HTTPException(status_code=504, detail="TTS synthesis timed out")

        if callback.error_msg:
            logger.error(f"TTS synthesis error: {callback.error_msg}")
            raise HTTPException(status_code=500, detail=f"TTS synthesis error: {callback.error_msg}")

        audio_data = callback.get_audio_data()

        if not audio_data:
            logger.error("No audio data generated")
            raise HTTPException(status_code=500, detail="No audio data generated")

        session_id = qwen_tts_realtime.get_session_id()
        first_audio_delay = qwen_tts_realtime.get_first_audio_delay()
        logger.info(f"TTS synthesis completed: session_id={session_id}, first_audio_delay={first_audio_delay}ms, audio_size={len(audio_data)} bytes")

        headers = {
            "X-Session-Id": session_id or "",
            "X-First-Audio-Delay": str(first_audio_delay or 0),
            "X-Usage-Characters":callback.get_usage_characters()
        }

        # Encapsulate PCM data into WAV format
        wav_audio_data = pcm_to_wav(audio_data)

        file_url = None
        if ENABLE_SAVE:
            logger.debug("Saving audio file...")
            file_url = save_audio(wav_audio_data, OUTPUT_DIR, http_request.base_url)
            logger.info(f"Audio saved: {file_url}")

        if request.return_url:
            if not ENABLE_SAVE:
                logger.warning("Saving is disabled, but return_url requested")
                raise HTTPException(status_code=400, detail="Saving is disabled, cannot return URL")
            return Response(content=json.dumps({"url": file_url}), media_type="application/json", headers=headers)

        return Response(content=wav_audio_data, media_type="audio/wav", headers=headers)

    except Exception as e:
        logger.exception(f"Unexpected error in /tts: {str(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Ensure resources are cleaned up if necessary
        # QwenTtsRealtime might need explicit closing if not handled by callback
        pass


@app.post("/tts_stream")
async def text_to_speech_stream(request: TTSRequest, http_request: Request):
    logger.info(f"Received TTS stream request: voice={request.voice}, model={request.model}")
    callback = SSECallback()

    # Initialize QwenTtsRealtime for each request to ensure isolation
    qwen_tts_realtime = QwenTtsRealtime(
        model=request.model,
        callback=callback,
        url=settings.get('dashscope.url', 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime')
    )

    def generate():
        audio_accumulator = io.BytesIO()
        try:
            logger.debug("Connecting to DashScope (stream)...")
            qwen_tts_realtime.connect()
            logger.debug(f"Updating session (stream): voice={request.voice}")
            qwen_tts_realtime.update_session(
                voice=request.voice,
                response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                mode='server_commit',
                format='pcm',
                language_type=request.language_type,
                sample_rate=request.sample_rate,
                pitch_rate=request.pitch_rate,
                speech_rate=request.speech_rate,
                volume=request.volume,
            )

            logger.debug(f"Appending text (stream): {request.text[:50]}...")
            qwen_tts_realtime.append_text(request.text)
            qwen_tts_realtime.finish()

            while True:
                try:
                    item = callback.queue.get(timeout=30)
                    if item is None:
                        logger.debug("Stream finished (received None)")
                        # Handle accumulated audio
                        pcm_data = audio_accumulator.getvalue()
                        usage_characters = callback.get_usage_characters()
                        if pcm_data and ENABLE_SAVE:
                            logger.debug("Saving accumulated audio from stream...")
                            wav_data = pcm_to_wav(pcm_data)
                            file_url = save_audio(wav_data, OUTPUT_DIR, http_request.base_url)
                            logger.info(f"Stream audio saved: {file_url}")
                            yield f"data: {json.dumps({'is_end': True, 'url': file_url, 'usage_characters': usage_characters})}\n\n"
                        else:
                            yield f"data: {json.dumps({'is_end': True, 'usage_characters': usage_characters})}\n\n"
                        break
                    
                    if isinstance(item, dict) and "audio" in item:
                        audio_accumulator.write(base64.b64decode(item["audio"]))

                    yield f"data: {json.dumps(item)}\n\n"
                except queue.Empty:
                    logger.error("Stream synthesis timed out waiting for audio")
                    yield f"data: {json.dumps({'error': 'Timeout waiting for audio'})}\n\n"
                    break
        except Exception as e:
            logger.exception(f"Error in stream generation: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Clean up if needed
            pass

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ============ Voice Design Endpoints ============

VOICE_DESIGN_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization"
VOICE_DESIGN_MODEL = "qwen-voice-design"
VOICE_DESIGN_TARGET_MODEL = "qwen3-tts-vd-realtime-2025-12-16"


@app.post("/voice_design/create")
async def create_voice(request: VoiceDesignRequest):
    """
    Erstellt eine neue Stimme basierend auf einer Textbeschreibung.
    Gibt den Stimmennamen und eine Audio-Vorschau zurück.
    """
    logger.info(f"Voice Design request: prompt={request.voice_prompt[:50]}...")
    
    import dashscope
    import re
    api_key = dashscope.api_key
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Sanitize preferred_name: nur Buchstaben, Zahlen, Unterstriche; max 16 Zeichen
    preferred_name = request.preferred_name or "voice"
    preferred_name = re.sub(r'[^a-zA-Z0-9_]', '', preferred_name)[:16]
    if not preferred_name:
        preferred_name = "voice"
    
    input_data = {
        "action": "create",
        "target_model": VOICE_DESIGN_TARGET_MODEL,
        "voice_prompt": request.voice_prompt,
        "preview_text": request.preview_text,
        "language": request.language
    }
    
    # preferred_name nur hinzufügen wenn vorhanden
    if preferred_name:
        input_data["preferred_name"] = preferred_name
    
    data = {
        "model": VOICE_DESIGN_MODEL,
        "input": input_data,
        "parameters": {
            "sample_rate": 24000,
            "response_format": "wav"
        }
    }
    
    try:
        response = requests.post(VOICE_DESIGN_URL, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            voice_name = result["output"]["voice"]
            preview_audio_b64 = result["output"]["preview_audio"]["data"]
            
            logger.info(f"Voice created successfully: {voice_name}")
            
            return {
                "success": True,
                "voice": voice_name,
                "preview_audio": preview_audio_b64,
                "target_model": VOICE_DESIGN_TARGET_MODEL
            }
        else:
            error_msg = response.text
            logger.error(f"Voice design failed: {error_msg}")
            raise HTTPException(status_code=response.status_code, detail=error_msg)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Voice design network error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")


@app.get("/voice_design/list")
async def list_voices(page_index: int = 0, page_size: int = 20):
    """
    Listet alle erstellten Stimmen auf.
    """
    import dashscope
    api_key = dashscope.api_key
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": VOICE_DESIGN_MODEL,
        "input": {
            "action": "list",
            "page_size": page_size,
            "page_index": page_index
        }
    }
    
    try:
        response = requests.post(VOICE_DESIGN_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "voices": result["output"].get("voice_list", []),
                "total_count": result["output"].get("total_count", 0),
                "page_index": result["output"].get("page_index", 0),
                "page_size": result["output"].get("page_size", page_size)
            }
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)
            
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")


@app.delete("/voice_design/{voice_name}")
async def delete_voice(voice_name: str):
    """
    Löscht eine erstellte Stimme.
    """
    import dashscope
    api_key = dashscope.api_key
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": VOICE_DESIGN_MODEL,
        "input": {
            "action": "delete",
            "voice": voice_name
        }
    }
    
    try:
        response = requests.post(VOICE_DESIGN_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            return {"success": True, "deleted": voice_name}
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)
            
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")


# ============ Voice Cloning Endpoints ============

VOICE_CLONING_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization"
VOICE_CLONING_MODEL = "qwen-voice-enrollment"
VOICE_CLONING_TARGET_MODEL = "qwen3-tts-vc-realtime-2026-01-15"


@app.post("/voice_cloning/create")
async def create_cloned_voice(request: VoiceCloningRequest):
    """
    Klont eine Stimme aus einem Audio-Sample (10-20 Sekunden).
    Audio muss als Base64 übergeben werden.
    """
    logger.info(f"Voice Cloning request: mime_type={request.audio_mime_type}")
    
    import dashscope
    import re
    api_key = dashscope.api_key
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Sanitize preferred_name
    preferred_name = request.preferred_name or "cloned"
    preferred_name = re.sub(r'[^a-zA-Z0-9_]', '', preferred_name)[:16]
    if not preferred_name:
        preferred_name = "cloned"
    
    # Erstelle Data URI aus Base64
    data_uri = f"data:{request.audio_mime_type};base64,{request.audio_base64}"
    
    input_data = {
        "action": "create",
        "target_model": VOICE_CLONING_TARGET_MODEL,
        "preferred_name": preferred_name,
        "audio": {"data": data_uri}
    }
    
    # Optional: Sprache hinzufügen
    if request.language:
        input_data["language"] = request.language
    
    data = {
        "model": VOICE_CLONING_MODEL,
        "input": input_data
    }
    
    try:
        response = requests.post(VOICE_CLONING_URL, headers=headers, json=data, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            voice_name = result["output"]["voice"]
            logger.info(f"Voice cloned successfully: {voice_name}")
            
            return {
                "success": True,
                "voice": voice_name,
                "target_model": VOICE_CLONING_TARGET_MODEL
            }
        else:
            error_msg = response.text
            logger.error(f"Voice cloning failed: {error_msg}")
            raise HTTPException(status_code=response.status_code, detail=error_msg)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Voice cloning network error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")


@app.get("/voice_cloning/list")
async def list_cloned_voices(page_index: int = 0, page_size: int = 20):
    """
    Listet alle geklonten Stimmen auf.
    """
    import dashscope
    api_key = dashscope.api_key
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": VOICE_CLONING_MODEL,
        "input": {
            "action": "list",
            "page_size": page_size,
            "page_index": page_index
        }
    }
    
    try:
        response = requests.post(VOICE_CLONING_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "voices": result["output"].get("voice_list", []),
                "total_count": result["output"].get("total_count", 0)
            }
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)
            
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")


@app.delete("/voice_cloning/{voice_name}")
async def delete_cloned_voice(voice_name: str):
    """
    Löscht eine geklonte Stimme.
    """
    import dashscope
    api_key = dashscope.api_key
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": VOICE_CLONING_MODEL,
        "input": {
            "action": "delete",
            "voice": voice_name
        }
    }
    
    try:
        response = requests.post(VOICE_CLONING_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            return {"success": True, "deleted": voice_name}
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)
            
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")


@app.post("/tts_vc_stream")
async def tts_voice_cloning_stream(request: VoiceDesignTTSRequest, http_request: Request):
    """
    TTS Streaming mit einer geklonten Stimme.
    """
    logger.info(f"Voice Cloning TTS stream request: voice={request.voice}")
    callback = SSECallback()
    
    qwen_tts_realtime = QwenTtsRealtime(
        model=VOICE_CLONING_TARGET_MODEL,
        callback=callback,
        url=settings.get('dashscope.url', 'wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime')
    )
    
    def generate():
        audio_accumulator = io.BytesIO()
        try:
            qwen_tts_realtime.connect()
            qwen_tts_realtime.update_session(
                voice=request.voice,
                response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                mode='server_commit',
                language_type=request.language_type,
                sample_rate=request.sample_rate,
                pitch_rate=request.pitch_rate,
                speech_rate=request.speech_rate,
                volume=request.volume,
            )
            
            qwen_tts_realtime.append_text(request.text)
            qwen_tts_realtime.finish()
            
            while True:
                try:
                    item = callback.queue.get(timeout=30)
                    if item is None:
                        pcm_data = audio_accumulator.getvalue()
                        usage_characters = callback.get_usage_characters()
                        if pcm_data and ENABLE_SAVE:
                            wav_data = pcm_to_wav(pcm_data)
                            file_url = save_audio(wav_data, OUTPUT_DIR, http_request.base_url)
                            yield f"data: {json.dumps({'is_end': True, 'url': file_url, 'usage_characters': usage_characters})}\n\n"
                        else:
                            yield f"data: {json.dumps({'is_end': True, 'usage_characters': usage_characters})}\n\n"
                        break
                    
                    if isinstance(item, dict) and "audio" in item:
                        audio_accumulator.write(base64.b64decode(item["audio"]))
                    
                    yield f"data: {json.dumps(item)}\n\n"
                except queue.Empty:
                    yield f"data: {json.dumps({'error': 'Timeout waiting for audio'})}\n\n"
                    break
        except Exception as e:
            logger.exception(f"Error in VC stream: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/tts_vd_stream")
async def tts_voice_design_stream(request: VoiceDesignTTSRequest, http_request: Request):
    """
    TTS Streaming mit einer per Voice Design erstellten Stimme.
    Verwendet das spezielle Voice Design TTS Modell.
    """
    logger.info(f"Voice Design TTS stream request: voice={request.voice}")
    callback = SSECallback()
    
    # Voice Design verwendet ein spezielles Modell
    qwen_tts_realtime = QwenTtsRealtime(
        model=VOICE_DESIGN_TARGET_MODEL,
        callback=callback,
        url=settings.get('dashscope.url', 'wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime')
    )
    
    def generate():
        audio_accumulator = io.BytesIO()
        try:
            logger.debug("Connecting to DashScope (VD stream)...")
            qwen_tts_realtime.connect()
            logger.debug(f"Updating session (VD): voice={request.voice}")
            qwen_tts_realtime.update_session(
                voice=request.voice,
                response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                mode='server_commit',
                language_type=request.language_type,
                sample_rate=request.sample_rate,
                pitch_rate=request.pitch_rate,
                speech_rate=request.speech_rate,
                volume=request.volume,
            )
            
            logger.debug(f"Appending text (VD): {request.text[:50]}...")
            qwen_tts_realtime.append_text(request.text)
            qwen_tts_realtime.finish()
            
            while True:
                try:
                    item = callback.queue.get(timeout=30)
                    if item is None:
                        pcm_data = audio_accumulator.getvalue()
                        usage_characters = callback.get_usage_characters()
                        if pcm_data and ENABLE_SAVE:
                            wav_data = pcm_to_wav(pcm_data)
                            file_url = save_audio(wav_data, OUTPUT_DIR, http_request.base_url)
                            yield f"data: {json.dumps({'is_end': True, 'url': file_url, 'usage_characters': usage_characters})}\n\n"
                        else:
                            yield f"data: {json.dumps({'is_end': True, 'usage_characters': usage_characters})}\n\n"
                        break
                    
                    if isinstance(item, dict) and "audio" in item:
                        audio_accumulator.write(base64.b64decode(item["audio"]))
                    
                    yield f"data: {json.dumps(item)}\n\n"
                except queue.Empty:
                    yield f"data: {json.dumps({'error': 'Timeout waiting for audio'})}\n\n"
                    break
        except Exception as e:
            logger.exception(f"Error in VD stream: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.get('server.host', '0.0.0.0'),
        port=settings.get('server.port', 9000)
    )
