# ✦ Manas Ciel — Capabilities & Operations Guide

> **Wisdom Core System**: Autonomous AI Desktop Assistant  
> **Personality**: Manas Ciel (*That Time I Got Reincarnated as a Slime*)  
> **Host Machine**: Local Windows Workstation  
> **Privacy & Cost**: 100% Local & 100% Free Forever  

---

## 1. System Architecture & Intelligence Engines

| Engine Component | Model / Technology | Role & Purpose |
| :--- | :--- | :--- |
| **Primary Intelligence Core** | `qwen2.5-coder:7b` (Ollama) | Powers all reasoning, computer tasks, documents, coding, and tool execution. |
| **Deep Reasoning Engine** | `qwen3:latest` (Ollama) | Engaged for complex logic proofs, mathematical formulations, and deep analyses. |
| **Ultra-Fast Speed Engine** | `qwen2.5-coder:1.5b` (Ollama) | Handles short status checks and basic arithmetic in under 1 second. |
| **Art Synthesis Engine** | `sdxl-turbo` / Stable Diffusion | Synthesizes digital artwork directly onto the canvas and desktop. |
| **Voice Perception (Ears)** | `faster-whisper` (`small.en`, int8) | Hands-free background listener detecting wake words (*"Ciel"*, *"Hey Ciel"*). |
| **Speech Voice (Vocal Core)** | Edge TTS (`en-US-AriaNeural`) | Ciel's calm, elegant voice responses. |

---

## 2. Where Working Data Is Stored

| Data Category | File / Folder Location | Description |
| :--- | :--- | :--- |
| **Chat Histories** | `chats/conversations.json` | Stores all active dialogue, session logs, and conversation threads. |
| **Long-Term Memory** | `chats/memory.json` | Persistent facts Ciel remembers about Master across restarts. |
| **Generated Artworks** | `app/static/images/` & Desktop | All generated images are displayed in chat and saved to `OneDrive\Desktop\Ciel_Artwork_<file>.png`. |
| **Downloaded AI Models** | `models/huggingface/hub/` & `models/ollama/` | Local weights for text-to-image and language models. |
| **Core Tools & Logic** | `app/agent_tools.py` | Complete Python registry of 35+ tools and direct command triggers. |
| **Operating Server** | `app/app.py` | Main Flask server, voice listener, model router, and API endpoints. |

---

## 3. Complete Command & Feature Reference

### A. Autonomous Drawing & Painting
Ciel creates actual visual art instead of text tutorials.

| Command Examples | Action Taken by Ciel |
| :--- | :--- |
| `"draw a cat"`, `"draw something"` | Synthesizes an AI digital artwork, renders it inside the chat, saves a high-res PNG to your Desktop, and opens it. |
| `"paint a cyberpunk city"`, `"sketch a dragon"` | Generates custom artwork using local diffusion pipeline. |
| `"draw a cat in paint"`, `"open paint and draw a house"` | Launches MS Paint, focuses the canvas, and autonomously moves the mouse to sketch the subject in real time. |
| *(Supported MS Paint subjects)* | `cat`, `house`, `heart`, `star`, `smiley face`. |

---

### B. Autonomous Multi-Step Computer Tasks
Tell Ciel to do work on any application or website:

| Command Examples | Action Taken by Ciel |
| :--- | :--- |
| `"make a presentation about AI in Canva"` | Opens Canva in browser, navigates to presentation templates, types topic, and starts slide design. |
| `"open google docs and write an essay on quantum computing"` | Launches Google Docs, creates a new document, and types an essay. |
| `"open notion and create a project roadmap"` | Opens Notion workspace and initializes a project management structure. |
| `"open sheets and create a monthly budget"` | Opens Google Sheets and generates budgeting columns and formula templates. |

---

### C. Direct App & Website Launchers
Zero-latency instant launching:

| Command Examples | Action Taken by Ciel |
| :--- | :--- |
| `"open music"`, `"play music"`, `"youtube"` | Opens Master's dedicated YouTube shortcut (`b⚡.lnk`) in Brave. |
| `"play Bohemian Rhapsody"` | Opens Brave and searches YouTube directly for the track. |
| `"open chrome"`, `"open brave"`, `"open discord"` | Launches the respective application immediately. |
| `"open vscode"`, `"open notepad"`, `"open calculator"` | Opens developer and productivity utilities. |
| `"open roblox"`, `"open opera"`, `"open spotify"` | Launches entertainment and gaming applications. |

---

### D. PowerPoint Slide Deck Generator
Ciel can generate native PowerPoint files without opening a browser:

| Command Examples | Action Taken by Ciel |
| :--- | :--- |
| `"make a presentation about robotics"` | Generates a styled 5-slide `.pptx` deck complete with headers, bullet points, and speaker notes, saving it directly to Master's desktop. |

---

### E. Desktop & Hardware Controls

| Control Type | Voice / Chat Commands |
| :--- | :--- |
| **System Volume** | `"volume up"`, `"volume down"`, `"mute"`, `"unmute"`, `"volume 50%"` |
| **Media Playback** | `"pause music"`, `"resume"`, `"next song"`, `"previous track"` |
| **Display Brightness** | `"brightness up"`, `"brightness down"`, `"brightness 75%"` |
| **Active Screen Perception** | `"what's on my screen"`, `"what am i looking at"` *(reads active window title and inspects workstation)* |
| **Clipboard Diagnostics** | `"inspect clipboard"`, `"analyze clipboard"` *(diagnoses copied code errors, JSON, or text)* |
| **Direct Mouse Actions** | `"click at 500, 300"`, `"double click at 200, 400"`, `"scroll down"`, `"scroll up"` |
| **Direct Keyboard Actions**| `"type 'Hello Master'"`, `"press enter"`, `"press esc"`, `"press tab"` |

---

### F. Coding, File Management & Security (ECC)

| Feature | Commands / Tools | Description |
| :--- | :--- | :--- |
| **File Operations** | `read_file`, `write_file`, `list_directory`, `search_files` | Reads, creates, edits, and organizes files across your computer. |
| **Script Execution** | `run_python`, `run_command` | Runs Python scripts or PowerShell commands directly in your workspace. |
| **Code Review** | `"ecc review [filename]"` | Analyzes code for bugs, edge cases, and performance bottlenecks. |
| **Security Audit** | `"ecc security [filename]"` | Audits code for vulnerabilities, injection vectors, and security leaks. |
| **Web Search** | `web_search(query)`, `fetch_webpage(url)` | Searches Google / DuckDuckGo for live internet info and reads documentation. |

---

### G. Workstation Modes & Routines

| Routine Name | Trigger Command | Automated Actions |
| :--- | :--- | :--- |
| **Coding Routine** | `"start coding mode"` | Launches VS Code, opens developer terminal, sets coding window layout. |
| **Focus Routine** | `"start focus mode"` | Mutes notifications, launches background ambient workspace, dims distractions. |
| **Chill Routine** | `"start entertainment mode"` | Launches YouTube / music player and adjusts volume for relaxation. |

---

## 4. Voice Interaction (Hands-Free)

* **Wake Words**: Speak naturally near your laptop microphone:
  * *"Ciel"*
  * *"Hey Ciel"*
  * *"Manas Ciel"*
* **Conversation Window**: Once awakened, Ciel remains attentive for 9 seconds to accept follow-up directives without needing to repeat the wake word.
* **Continuous Transcription**: Handled locally via Faster-Whisper CPU INT8 with zero data leaving your computer.

---

## 5. Ciel's Personality & Response Protocol

In accordance with Tensura lore, Ciel addresses the user exclusively as **"Master"** and organizes tactical reports using structured tags:

* `[Notice]` — Operational alerts, tool invocations, system status.
* `[Report]` — Execution outcomes, completed artwork notifications, task summaries.
* `[Analysis]` — Deep code reviews, logic breakdowns, mathematical calculations.
* `[Proposal]` — Strategic suggestions, performance enhancements, architectural ideas.
