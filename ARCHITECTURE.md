# CinemaTUI - Backend Architecture

## Overview

CinemaTUI è un Media Center TUI (Terminal User Interface) costruito con Textual, progettato per funzionare su sistemi minimal Linux (X11 + xterm) collegati a proiettori.

## Architettura Backend

Il backend è organizzato in **5 moduli specializzati** che lavorano in parallelo, disaccoppiati dal frontend:

### 1. **FileScanner** (`controllers/scanner.py`)
Gestione asincrona del file system locale.

**Funzionalità:**
- Scanning ricorsivo di directory video (.mp4, .mkv, .avi, .mov, .flv, .wmv)
- Caching intelligente con TTL di 5 minuti
- Filtraggio per pattern regex (case-insensitive)
- Limite configurabile di risultati (default: 500)
- Estrazione durata video via ffprobe (con fallback)

**API:**
```python
scanner = FileScanner()
results = await scanner.scan(
    paths=["/home/user/Videos"],
    pattern="avengers",
    use_cache=True
)
# Restituisce: [{"filename": "...", "path": "...", "size": int, "duration": "00:00"}]
```

**Note:**
- Non-blocking I/O tramite `asyncio.to_thread()`
- Scansione parallela di directory con `asyncio.gather()`

---

### 2. **MpvController** (`controllers/player.py`)
Controllo media player locale e YouTube via mpv.

**Funzionalità:**
- Riproduzione in fullscreen (`--fs`)
- Controllo IPC via socket JSON a `/tmp/mpvsocket`
- Supporto file locali e URL YouTube
- Comandi: play, pause, resume, stop, volume_up/down, seek
- Callback su fine riproduzione

**API:**
```python
player = MpvController(on_finish=callback)
await player.play("/path/to/video.mp4")
await player.pause()
await player.volume_up(5)
await player.stop()
```

**Stato:**
- Enum `PlaybackState`: STOPPED, PLAYING, PAUSED
- Query: `get_volume()`, `get_duration()`, `get_position()`

**Note:**
- Comunicazione socket non-blocking
- Timeout 5 secondi su comando IPC
- Fallback a terminazione SIGKILL se necessario

---

### 3. **WebKiosk** (`controllers/kiosk.py`)
Gestione browser Chromium in kiosk mode per servizi con DRM.

**Funzionalità:**
- Lancio Chromium con flag `--kiosk`
- Supporto Netflix, Prime Video, YouTube
- Gestione del ciclo di vita del processo
- Shutdown graceful (SIGTERM → timeout → SIGKILL)
- Callback su chiusura kiosk

**API:**
```python
kiosk = WebKiosk(on_kiosk_closed=callback)
await kiosk.launch("https://netflix.com")
# TUI si blocca qui fino alla chiusura del browser
await kiosk.shutdown()

# O con context manager:
async with KioskManager() as manager:
    await manager.launch("https://primevideo.com")
```

**Eccezioni:**
- `ChromiumNotFoundError` - Chromium non installato
- `InvalidURLError` - URL invalido
- `KioskProcessError` - Errore processo

**Note:**
- Rilascio automatico del focus Textual
- Ricerca percorso Chromium nel PATH

---

### 4. **SystemControl** (`controllers/system.py`)
Controllo volume di sistema e spegnimento.

**Funzionalità:**
- Auto-rilevamento backend audio (PipeWire via wpctl, PulseAudio via pactl)
- Get/set volume (0-100%)
- Mute/unmute
- Spegnimento sistema sicuro (`sudo poweroff`)

**API:**
```python
system = SystemControl()
volume_info = await system.get_volume()
# VolumeInfo(level=70, muted=False, backend=AudioBackend.PULSEAUDIO)

await system.set_volume(80)
await system.toggle_mute()
await system.shutdown()
```

**Note:**
- Fallback graceful se backend audio non disponibile
- Timeout 10 secondi per evitare freeze TUI
- Logging dettagliato per debug

---

### 5. **CinemaController** (`controllers/__init__.py`)
Orchestrator che aggrega i 4 moduli in un'API unificata.

**Responsabilità:**
- Gestione dello stato dell'applicazione (`ControllerState`)
- Sistema di event callback (playback_finish, kiosk_close, error, volume_change)
- Gestione errori centralizzata
- Lazy initialization del player (only when needed)

**API Pubblica:**

```python
controller = CinemaController()

# File Scanning
success, items, error = await controller.scan_files(
    paths=["/mnt/media"],
    pattern="marvel"
)

# Playback
success, msg = await controller.play_file("/path/to/file.mp4")
success, msg = await controller.play_youtube("https://youtube.com/watch?v=...")
success, msg = await controller.player_pause()
success, msg = await controller.player_resume()
success, msg = await controller.player_stop()

# Volume
success, msg = await controller.volume_up(5)
success, msg = await controller.volume_down(5)
volume, err = await controller.get_volume()
success, msg = await controller.set_volume(80)

# Streaming
success, msg = await controller.stream_service("netflix")
success, msg = await controller.stream_service("prime")
success, msg = await controller.stream_service("youtube", custom_url="...")

# System
success, msg = await controller.system_poweroff()
await controller.cleanup()

# State
state = controller.get_state()
# ControllerState(playback_state, current_file, current_volume, kiosk_state, ...)

# Events
controller.on("playback_finish", callback)
controller.on("error", error_callback)
controller.off("playback_finish", callback)
```

**State Tracking:**
```python
@dataclass
class ControllerState:
    playback_state: PlaybackState = PlaybackState.STOPPED
    current_file: Optional[str] = None
    current_volume: int = 70
    kiosk_state: KioskState = KioskState.CLOSED
    scan_in_progress: bool = False
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
```

---

## Integrazione TUI

### Flusso di Interazione

1. **User clicca bottone "Play"** → `on_button_pressed(Button.Pressed)`
2. **Handler TUI** chiama `action_play_pause()` → `run_worker(_async_play_pause())`
3. **Async worker** chiama `controller.player_pause()` oppure `controller.player_resume()`
4. **CinemaController** delega a `MpvController.pause()` / `resume()`
5. **MpvController** invia JSON via socket IPC
6. **Status update** via `_update_status()` in TUI

### Bindings Tastiera

```python
Binding("q", "quit", "Quit")
Binding("p", "play_pause", "Play/Pause")
Binding("s", "stop", "Stop")
Binding("n", "next_vol", "Vol+")
Binding("m", "prev_vol", "Vol-")
```

### Callbacks Evento

```python
controller.on("playback_finish", self._on_playback_finish)
controller.on("error", self._on_error)
controller.on("volume_change", self._on_volume_change)
```

---

## Gestione Errori

Tutti i metodi pubblici restituiscono `Tuple[bool, str]`:

```python
success, message = await controller.play_file("/path/to/file.mp4")

if not success:
    print(f"Error: {message}")
    # L'errore è anche registrato in state.last_error
```

Gli errori sono gestiti con try-except internamente:
- **MpvController non installato** → RuntimeError al init
- **Chromium non disponibile** → ChromiumNotFoundError
- **Socket IPC fallisce** → Fallback e logging
- **URL invalido** → InvalidURLError

---

## Setup di Sviluppo

### Dipendenze Richieste

```bash
# Python
python3.11+

# Pip packages
textual          # TUI framework
ffprobe          # Duration extraction (sudo apt install ffmpeg)

# System tools
mpv              # Media player (sudo apt install mpv)
chromium-browser # For streaming services (sudo apt install chromium-browser)
pactl/wpctl      # Audio control (installed by default)
```

### Installazione

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install system tools
sudo apt install mpv chromium-browser ffmpeg

# Run
python main.py
```

### Logging

Logging è configurato in `main.py`:
- File: `/tmp/cinema.log`
- Console: stderr
- Level: INFO (debug info nei moduli)

---

## Performance & Scalability

### FileScanner
- Cache 5 minuti: evita riscansioni frequenti
- Limite 500 file: previene memory exhaustion
- Non-blocking: async/await non blocca TUI

### MpvController
- IPC socket: latenza <50ms per comando
- Monitor task asincrono: detects playback finish without polling
- Timeout 5s: evita freeze su socket hang

### WebKiosk
- Process monitoring: detects Chromium exit
- Graceful shutdown: 15s timeout → SIGKILL
- Signal handlers: cleanup su inaspettato terminate

### CinemaController
- Lazy player init: solo se necessario
- Event callbacks: non-blocking via `asyncio.create_task()`
- State tracking: O(1) queries

---

## Testing

### Unit Tests (Doctest Format)
Ogni modulo include doctest inline. Esegui:

```bash
python -m doctest controllers/scanner.py -v
```

### Integration Test
```bash
python -c "
from controllers import CinemaController
c = CinemaController()
state = c.get_state()
print(f'Controller ready: {state.playback_state.value}')
"
```

---

## Troubleshooting

### MpvController: "mpv not installed"
```bash
sudo apt install mpv
```

### WebKiosk: "Chromium not found"
```bash
sudo apt install chromium-browser
```

### FileScanner: "No files found"
- Verificare paths sono accessibili: `ls -la /home/user/Videos`
- Controllare estensioni supportate: .mp4, .mkv, .avi, .mov, .flv, .wmv
- Verificare cache: `scanner.clear_cache()`

### Socket IPC Timeout
- Verificare mpv è in running: `pgrep mpv`
- Controllare socket: `ls -la /tmp/mpvsocket`
- Check mpv logs in `/tmp/cinema.log`

---

## Note di Produzione

1. **Thread Pool**: FileScanner e SystemControl usano `asyncio.to_thread()` per operazioni blocking
2. **Signal Handling**: WebKiosk gestisce SIGTERM/SIGKILL correttamente
3. **Resource Cleanup**: `CinemaController.cleanup()` chiude tutti i processi
4. **Error Recovery**: Tutti i fallback sono graceful (non crash TUI)
5. **Logging**: Production-ready con timestamps e livelli

---

## Architettura Futura

Possibili estensioni:

- **PipeWire support**: Già rilevato in SystemControl, pronto
- **DLNA/UPnP**: Nuova source oltre local/YouTube/streaming
- **Playlist support**: Array di media items
- **Resume playback**: Tracking position in DB
- **Remote control**: Supporto IR via lirc
- **HDR/Codec negotiation**: Display device capabilities

---

**Version**: 1.0.0  
**Last Updated**: 2026-07-21  
**Status**: Production-Ready
