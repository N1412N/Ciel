<div align="center">

# âœ¦ MANAS CIEL

### *Autonomous AI Desktop Assistant & Intelligence Core*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Backend](https://img.shields.io/badge/Backend-Flask%20%2B%20PyWebView-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![LLM Engine](https://img.shields.io/badge/Inference-Ollama%20Local-purple?logo=ollama&logoColor=white)](https://ollama.com/)
[![Voice](https://img.shields.io/badge/Perception-Faster--Whisper%20%2B%20EdgeTTS-pink)](https://github.com/SYSTRAN/faster-whisper)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6?logo=windows&logoColor=white)](https://microsoft.com/windows)

<p align="center">
  <b>A private, offline-capable AI desktop companion inspired by Wisdom King Raphael / Manas Ciel.</b><br/>
  Featuring hands-free voice control, autonomous multi-step computer automation, real-time mouse painting, and intelligent local model routing.
</p>

</div>

---

## ðŸ›ï¸ System Architecture

<div align="center">
  <img src="docs/ciel_architecture.svg" alt="Manas Ciel Architecture Diagram" width="100%"/>
</div>

---

## âœ¨ Key Features & Capabilities

### ðŸ§  1. Multi-Engine Intelligence Router
Ciel dynamically delegates tasks to specialized local models running on your hardware:
* **Primary Intelligence Core** (`qwen2.5-coder:7b`): Handles reasoning, coding, document creation, and tool calling.
* **Deep Reasoning Engine** (`qwen3:latest`): Engages for complex mathematical logic proofs and multi-step analyses.
* **Ultra-Fast Speed Engine** (`qwen2.5-coder:1.5b`): Executes instant status inquiries and short commands in under a second.
* **Text-to-Image Synthesis** (`sdxl-turbo` / Stable Diffusion): Synthesizes digital artwork directly onto canvas and desktop.

### ðŸŽ™ï¸ 2. Hands-Free Voice Perception & Speech
* **Voice Ear**: Offline wake-word detection (*"Ciel"*, *"Hey Ciel"*) powered by `faster-whisper` (`small.en`, int8 quantization).
* **Vocal Core**: Smooth, natural speech responses utilizing Microsoft Edge Neural TTS (`en-US-AriaNeural`).

### ðŸ–±ï¸ 3. Autonomous Computer Control & Automation
* **Live App Automation**: Controls apps and browsers (Canva, Google Docs, Notion, Sheets, Calculator).
* **Autonomous MS Paint Sketching**: Launches MS Paint and autonomously guides the cursor to draw cats, stars, hearts, and houses in real time.
* **System Telemetry & Control**: Real-time VRAM monitoring, memory purging (`/api/models/purge`), clipboard analysis, and hotkey listeners.

---

## ðŸ“ Repository Structure

```text
Ciel/
â”œâ”€â”€ app/
â”‚   â”œâ”€â”€ app.py                 # Core Flask application, API router & SSE server
â”‚   â”œâ”€â”€ agent_tools.py         # 35+ autonomous tools & execution registry
â”‚   â”œâ”€â”€ launch_desktop.py      # PyWebView native desktop window container
â”‚   â”œâ”€â”€ launcher.cs            # Native C# launcher source
â”‚   â”œâ”€â”€ model_router.py        # Dynamic LLM routing engine
â”‚   â”œâ”€â”€ primitive_engine.py    # Autonomous canvas and drawing routines
â”‚   â”œâ”€â”€ security.py            # Tool safety guardrails and permissions
â”‚   â”œâ”€â”€ task_manager.py        # Asynchronous background task scheduler
â”‚   â”œâ”€â”€ requirements.txt       # Python dependencies
â”‚   â”œâ”€â”€ static/                # Cyberpunk HUD styles, icons & animations
â”‚   â””â”€â”€ templates/             # HUD interface template (index.html)
â”œâ”€â”€ docs/
â”‚   â””â”€â”€ ciel_architecture.svg # Complete system architecture diagram
â”œâ”€â”€ plans/
â”‚   â””â”€â”€ ciel-improvement-roadmap.md   # Architectural roadmap and hardening plan
â”œâ”€â”€ tests/                     # Automated test harness & security validations
â”œâ”€â”€ CIEL_CAPABILITIES.md       # Detailed operations & commands reference
â”œâ”€â”€ CONFIG_GUIDE.md            # Hardware & model configuration guide
â”œâ”€â”€ INITIAL_PROJECT_ANALYSIS.md# Technical audit and API reference
â”œâ”€â”€ INSTALL_DEPENDENCIES.bat   # One-click dependency installer
â”œâ”€â”€ RUN_CIEL.bat               # One-click desktop launcher
â”œâ”€â”€ RUN_CIEL_COMPANION.bat     # Compact taskbar companion launcher
â”œâ”€â”€ LICENSE                    # MIT Open Source License
â””â”€â”€ README.md                  # Project documentation
```

---

## ðŸš€ Getting Started

### Prerequisites
1. **Windows 10 / 11** (64-bit).
2. **Python 3.10+** (ensure `Add Python to PATH` is checked during install).
3. **[Ollama](https://ollama.com/)** installed and running locally.
   ```bash
   ollama pull qwen2.5-coder:7b
   ```

### 1. Installation
Clone the repository:
```bash
git clone https://github.com/N1412N/Ciel.git
cd Ciel
```

Install required Python dependencies:
* Run **`INSTALL_DEPENDENCIES.bat`**  
  *or manually:*
```bash
pip install -r app/requirements.txt
```

### 2. Launching Ciel
Simply double-click **`RUN_CIEL.bat`** (or `Ciel.exe`).

The desktop HUD interface will open maximized with hands-free voice detection active!

---

## ðŸ§ª Running Tests

The test suite covers backend security, model routing, safety guardrails, and APIs:
```bash
pytest tests/
```

---

## ðŸ›¡ï¸ License

This project is licensed under the [MIT License](LICENSE) â€” Copyright (c) 2026 **N1412N**.

