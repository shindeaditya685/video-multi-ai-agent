# 🎬 Free AI Crime Video Agent

A fully automated **multi-agent system** that generates true-crime documentary
videos from a topic — completely free, no paid APIs required.

```
Topic Input
    ↓ Research Agent      — Collects case details
    ↓ Story Agent         — Writes documentary narration
    ↓ Scene Agent         — Splits story into 12–16 scenes
    ↓ Prompt Agent        — Creates cinematic image prompts
    ↓ Voice Agent         — Generates narration (Edge-TTS, free)
    ↓ Image Agent         — Downloads AI images (Pollinations.ai, free)
    ↓ Video Agent         — Assembles MP4 with Ken Burns effect
    ↓ Subtitle Agent      — Adds captions (Whisper, open source)
    ↓ Thumbnail Agent     — Creates YouTube thumbnail
    ↓ Upload Agent        — Posts to YouTube (optional)
    ↓
   final_video.mp4
```

---

## ⚡ Quick Start

### 1. Clone & Install

```bash
git clone <your-repo>
cd crime_video_agent
pip install -r requirements.txt
```

> **FFmpeg required** (for video export):
> ```bash
> # Ubuntu/Debian
> sudo apt install ffmpeg
> # macOS
> brew install ffmpeg
> # Windows — download from https://ffmpeg.org/download.html
> ```

### 2. Set your free Groq API key

```bash
cp .env.example .env
# Edit .env and set GROQ_API_KEY
# Get free key at: https://console.groq.com (no credit card)
```

### 3. Run

```bash
# Generate a video
python pipeline.py "The Muskan murder case"

# With custom output name
python pipeline.py "The Nirbhaya case" --job-id nirbhaya

# Auto-upload to YouTube (needs client_secrets.json — see below)
python pipeline.py "The Aryan Khan case" --upload
```

---

## 📁 Project Structure

```
crime_video_agent/
├── pipeline.py              ← Main orchestrator (run this)
├── api.py                   ← FastAPI backend (optional web UI)
├── requirements.txt
├── .env.example             ← Copy to .env and fill in keys
│
├── core/
│   ├── config.py            ← Settings + shared PipelineState
│   └── llm.py               ← Groq LLM wrapper
│
├── agents/
│   ├── 01_research_agent.py
│   ├── 02_story_agent.py
│   ├── 03_scene_agent.py
│   ├── 04_prompt_agent.py
│   ├── 05_voice_agent.py
│   ├── 06_image_agent.py
│   ├── 07_video_agent.py
│   ├── 08_subtitle_agent.py
│   ├── 09_thumbnail_agent.py
│   └── 10_upload_agent.py
│
├── output/                  ← Final MP4s and thumbnails (auto-created)
└── temp/                    ← Intermediate files (auto-created)
```

---

## 🆓 Free Stack — Zero Cost

| Component         | Tool                  | Cost  | Notes                                |
|-------------------|-----------------------|-------|--------------------------------------|
| LLM / Script      | Groq + LLaMA 3        | Free  | 30 req/min free tier                 |
| Image generation  | Pollinations.ai       | Free  | No API key, no limits                |
| Voice narration   | Edge-TTS (Microsoft)  | Free  | Natural voices, no key needed        |
| Captions          | OpenAI Whisper        | Free  | Runs locally, open source            |
| Video assembly    | MoviePy + FFmpeg      | Free  | Open source                          |
| Thumbnail         | Pillow                | Free  | Open source                          |
| Upload            | YouTube Data API v3   | Free  | 10,000 units/day free quota          |

---

## 🎙️ Voice Options

Edit `VOICE_NAME` in `.env`:

| Voice Name              | Style              |
|-------------------------|--------------------|
| `en-US-GuyNeural`       | Male, Documentary  |
| `en-US-JennyNeural`     | Female, News       |
| `en-GB-RyanNeural`      | British Male       |
| `en-IN-NeerjaNeural`    | Indian Female      |
| `en-US-ChristopherNeural` | Deep Male        |

---

## 🚀 Run as API (for Next.js frontend)

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

**Endpoints:**

| Method | Path                  | Description                        |
|--------|-----------------------|------------------------------------|
| POST   | `/generate`           | Start job, returns `job_id`        |
| GET    | `/status/{job_id}`    | Poll progress (0–100%)             |
| GET    | `/download/{job_id}`  | Download final MP4                 |
| GET    | `/thumbnail/{job_id}` | Download thumbnail PNG             |
| WS     | `/ws/{job_id}`        | Real-time progress via WebSocket   |

**Example (Next.js):**
```javascript
const { job_id } = await fetch('/generate', {
  method: 'POST',
  body: JSON.stringify({ topic: 'The Muskan case' })
}).then(r => r.json());

// Poll or use WebSocket
const ws = new WebSocket(`ws://localhost:8000/ws/${job_id}`);
ws.onmessage = (e) => console.log(JSON.parse(e.data)); // { progress, status, title }
```

---

## 📺 YouTube Upload Setup (one time)

1. Go to https://console.cloud.google.com
2. Create a project → Enable **YouTube Data API v3**
3. Create **OAuth 2.0** credentials → Download as `client_secrets.json`
4. Place `client_secrets.json` in the project root
5. Run with `--upload` — browser will open to authorize once
6. Token is cached in `youtube_token.pickle` for future runs

---

## 🧩 Build Levels

| Level | Description                         | How                                 |
|-------|-------------------------------------|-------------------------------------|
| 1     | Semi-auto (approve each stage)      | Call each agent manually            |
| 2     | Fully automated (one command → MP4) | `python pipeline.py "topic"`        |
| 3     | Autonomous studio (trending topics) | Add scheduler + YouTube trending API |

---

## 🛠️ Customization

- **Change LLM**: Edit `core/llm.py` to swap Groq → Gemini or Ollama
- **Change images**: Set `IMAGE_PROVIDER=stability` in `.env` for better quality
- **Change voice**: Set `VOICE_NAME` in `.env` (see table above)
- **Add agents**: Create `agents/11_my_agent.py` and add to `PIPELINE` list in `pipeline.py`

---

## 📋 Requirements

- Python 3.10+
- FFmpeg installed on system
- Free Groq API key
- Internet connection (for Pollinations.ai + Edge-TTS)

---

## Next.js Studio UI

This repo now includes a reviewed full-stack workflow:

1. Enter topic notes, video dimensions, FPS, and image/scene count.
2. Choose AI-generated images or upload your own image set.
3. Choose script language: English, Hindi, or Marathi.
4. Choose narration voice, subtitles, image fit, and transition style.
5. Generate a script draft.
6. Review or edit the title, hook, narration, scenes, and image prompts.
7. Confirm the draft to generate voice, images, video, subtitles, and thumbnail.

Voice options include Indian English, Hindi, and Marathi Edge voices, plus gTTS Indian-accent fallbacks. Edge TTS is still the best free no-key neural option in this project; gTTS is useful when Indian pronunciation matters more than neural voice quality.

Extra studio tools:

- Voice preview before render
- Pronunciation dictionary (`Name = phonetic spelling`)
- Per-scene AI image preview/regeneration
- Per-scene uploaded image assignment
- Render quality presets: preview, balanced, final
- Optional generated background music bed
- Timeline metrics for duration, scenes, and canvas
- Project save/load as JSON

Run the backend:

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Run the frontend:

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend calls `http://127.0.0.1:8000` by default. To use another backend URL:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

New reviewed API endpoints:

| Method | Path                | Description                                      |
|--------|---------------------|--------------------------------------------------|
| POST   | `/draft`            | Generate research, script, scenes, image prompts |
| POST   | `/uploads/{job_id}` | Upload source images for upload-image mode       |
| POST   | `/voice-preview`    | Generate a short narration preview               |
| POST   | `/preview-image/{job_id}/{scene}` | Generate/regenerate one scene image  |
| GET    | `/project/{job_id}` | Export current project JSON                      |
| POST   | `/project`          | Import project JSON as a new reviewable job      |
| POST   | `/confirm/{job_id}` | Render the approved script into final video      |
| POST   | `/generate`         | Run the full pipeline without review             |
