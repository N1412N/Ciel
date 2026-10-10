# Ciel Configuration System

Ciel uses a centralized, typed configuration system defined in [`app/config.py`](file:///C:/Users/Lenovo/Ciel/app/config.py).
Configuration values are loaded with safe defaults, and can be customized via environment variables or a `.env` file at the root of the project.

---

## Configuration Categories

### 1. Server Configuration (`ServerConfig`)
| Variable | Default | Description |
|---|---|---|
| `CIEL_HOST` | `127.0.0.1` | Host address the Flask backend binds to |
| `CIEL_PORT` | `5000` | Port the Flask backend listens on |
| `CIEL_DEBUG` | `false` | Enable Flask debug mode (keep false in production) |
| `CIEL_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### 2. Paths Configuration (`PathConfig`)
| Variable | Default | Description |
|---|---|---|
| `CIEL_WORKSPACE` | `<CIEL_ROOT>` | Root directory for agent file sandboxing |
| `CIEL_CHATS_DIR` | `<CIEL_ROOT>/chats` | Directory for conversations and memory JSON files |
| `CIEL_IMAGE_DIR` | `<APP_DIR>/static/images` | Directory where AI-generated images are saved |
| `HF_HOME` | `<CIEL_ROOT>/models/huggingface` | Cache directory for Diffusers/Hugging Face models |
| `OLLAMA_MODELS` | `<CIEL_ROOT>/models/ollama` | Storage directory for Ollama model weights |

### 3. Ollama Model Configuration (`OllamaConfig`)
| Variable | Default | Description |
|---|---|---|
| `OLLAMA_API_URL` | `http://127.0.0.1:11434` | Ollama local API base URL |
| `OLLAMA_DEFAULT_MODEL` | `qwen2.5-coder:7b` | Primary model for code and complex queries |
| `OLLAMA_FAST_MODEL` | `qwen2.5:1.5b` | Ultra-fast lightweight model for short pings |
| `OLLAMA_REASONING_MODEL` | `deepseek-r1:7b` | Reasoning model for deep math & architectural analysis |
| `OLLAMA_VISION_MODEL` | `llava:7b` | Multimodal model for analyzing images |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Timeout for LLM generation responses |

### 4. Voice Configuration (`VoiceConfig`)
| Variable | Default | Description |
|---|---|---|
| `CIEL_TTS_VOICE` | `en-US-AriaNeural` | Edge-TTS neural voice name |
| `CIEL_TTS_PITCH` | `+14Hz` | Voice pitch adjustment |
| `CIEL_TTS_RATE` | `+5%` | Speech speed rate adjustment |
| `CIEL_WAKE_TIMEOUT` | `10` | Timeout in seconds waiting for user speech |
| `CIEL_WHISPER_MODEL` | `base.en` | Faster-Whisper model size |

### 5. Execution Limits (`LimitsConfig`)
| Variable | Default | Description |
|---|---|---|
| `CIEL_COMMAND_TIMEOUT` | `30` | Subprocess command timeout (seconds) |
| `CIEL_PERMISSION_TIMEOUT` | `120` | Desktop user permission modal timeout (seconds) |
| `CIEL_MAX_IMAGE_WIDTH` | `1024` | Maximum allowable width for image generation |
| `CIEL_MAX_IMAGE_HEIGHT` | `1024` | Maximum allowable height for image generation |
| `CIEL_MAX_CODE_SIZE` | `500000` | Maximum file characters accepted in IDE endpoints |
| `CIEL_MAX_OUTPUT_LENGTH`| `100000` | Maximum characters captured from shell outputs |

---

## How to Customize

1. Copy `.env.example` to `.env`:
   ```powershell
   copy .env.example .env
   ```
2. Edit `.env` with your desired configuration values.
3. Start Ciel normally with `RUN_CIEL.bat`. The configuration module will automatically read your `.env` values and validate them on startup.
