"use client";

import {
  AlertTriangle,
  Captions,
  CheckCircle2,
  Clapperboard,
  Download,
  FileText,
  FolderOpen,
  Image as ImageIcon,
  Layers3,
  Loader2,
  Mic2,
  Monitor,
  Play,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  Smartphone,
  Square,
  Trash2,
  UploadCloud,
  Volume2,
  Wand2
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type ImageSource = "ai" | "upload";
type ImageFitMode = "contain_blur" | "cover";
type VoiceProvider = "edge" | "gtts";
type TransitionStyle = "crossfade" | "fade" | "none";
type ScriptLanguage = "en" | "hi" | "mr";

type ScenePayload = {
  number: number;
  duration: number;
  narration: string;
  visual_desc: string;
  image_prompt: string;
  upload_image_index?: number | null;
  image_url?: string;
};

type JobStatus = {
  job_id: string;
  status: string;
  progress: number;
  topic: string;
  details: string;
  script_language: ScriptLanguage;
  pronunciation_map: string;
  title: string;
  hook: string;
  story: string;
  scenes: ScenePayload[];
  video_width: number;
  video_height: number;
  video_fps: number;
  image_count: number;
  image_source: ImageSource;
  image_fit_mode: ImageFitMode;
  uploaded_image_count: number;
  voice_provider: VoiceProvider;
  voice_name: string;
  voice_rate: string;
  voice_pitch: string;
  subtitles_enabled: boolean;
  subtitle_font_size: number;
  transition_style: TransitionStyle;
  transition_duration: number;
  ken_burns_intensity: number;
  render_quality: "preview" | "balanced" | "final";
  background_music: "none" | "suspense" | "ambient" | "emotional";
  background_music_volume: number;
  estimated_duration: number;
  uploaded_images: { index: number; name: string; url: string }[];
  errors: string[];
  video_url: string;
  thumbnail_url: string;
  youtube_url: string;
};

type Preset = {
  id: string;
  label: string;
  width: number;
  height: number;
  fps: number;
  icon: LucideIcon;
};

type VoiceOption = {
  id: string;
  provider: VoiceProvider;
  voice: string;
  label: string;
};

const PRESETS: Preset[] = [
  { id: "hd", label: "HD", width: 1280, height: 720, fps: 24, icon: Monitor },
  { id: "fullhd", label: "Full HD", width: 1920, height: 1080, fps: 24, icon: Clapperboard },
  { id: "shorts", label: "Shorts", width: 1080, height: 1920, fps: 30, icon: Smartphone },
  { id: "square", label: "Square", width: 1080, height: 1080, fps: 24, icon: Square }
];

const VOICES: VoiceOption[] = [
  { id: "edge-prabhat", provider: "edge", voice: "en-IN-PrabhatNeural", label: "Prabhat Indian English" },
  { id: "edge-neerja", provider: "edge", voice: "en-IN-NeerjaNeural", label: "Neerja Indian English" },
  { id: "edge-madhur", provider: "edge", voice: "hi-IN-MadhurNeural", label: "Madhur Hindi" },
  { id: "edge-swara", provider: "edge", voice: "hi-IN-SwaraNeural", label: "Swara Hindi" },
  { id: "edge-manohar", provider: "edge", voice: "mr-IN-ManoharNeural", label: "Manohar Marathi" },
  { id: "edge-aarohi", provider: "edge", voice: "mr-IN-AarohiNeural", label: "Aarohi Marathi" },
  { id: "gtts-en-in", provider: "gtts", voice: "gtts-en-in", label: "gTTS Indian English" },
  { id: "gtts-hi-in", provider: "gtts", voice: "gtts-hi-in", label: "gTTS Hindi" },
  { id: "gtts-mr-in", provider: "gtts", voice: "gtts-mr-in", label: "gTTS Marathi" },
  { id: "edge-guy", provider: "edge", voice: "en-US-GuyNeural", label: "Guy US English" }
];

const LANGUAGE_DEFAULTS: Record<ScriptLanguage, VoiceOption> = {
  en: VOICES[0],
  hi: VOICES[2],
  mr: VOICES[4]
};

const STATUS_LABELS: Record<string, string> = {
  idle: "Idle",
  queued: "Queued",
  drafting: "Drafting",
  researching: "Researching",
  writing_story: "Writing script",
  breaking_scenes: "Breaking scenes",
  generating_prompts: "Writing prompts",
  awaiting_confirmation: "Review ready",
  queued_for_render: "Queued render",
  rendering: "Rendering",
  generating_voice: "Generating voice",
  generating_images: "Preparing images",
  assembling_video: "Assembling video",
  adding_subtitles: "Adding captions",
  creating_thumbnail: "Creating thumbnail",
  uploading: "Uploading",
  done: "Done",
  error: "Error"
};

function assetUrl(path: string) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${API_BASE}${path}`;
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (data.detail) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // Keep status text.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function statusLabel(status?: string) {
  if (!status) return "Not started";
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

export default function StudioPage() {
  const [topic, setTopic] = useState("The Nirbhaya case 2012");
  const [details, setDetails] = useState(
    "Serious documentary tone. Focus on timeline, investigation, legal impact, and public reaction."
  );
  const [scriptLanguage, setScriptLanguage] = useState<ScriptLanguage>("en");
  const [pronunciationMap, setPronunciationMap] = useState("Nirbhaya = निर्भया\nAarushi = आरुषि");
  const [width, setWidth] = useState(1280);
  const [height, setHeight] = useState(720);
  const [fps, setFps] = useState(24);
  const [imageCount, setImageCount] = useState(12);
  const [imageSource, setImageSource] = useState<ImageSource>("ai");
  const [imageFitMode, setImageFitMode] = useState<ImageFitMode>("contain_blur");
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [voiceProvider, setVoiceProvider] = useState<VoiceProvider>("edge");
  const [voiceName, setVoiceName] = useState("en-IN-PrabhatNeural");
  const [voiceRate, setVoiceRate] = useState("+0%");
  const [voicePitch, setVoicePitch] = useState("+0Hz");
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [subtitleFontSize, setSubtitleFontSize] = useState(18);
  const [transitionStyle, setTransitionStyle] = useState<TransitionStyle>("crossfade");
  const [transitionDuration, setTransitionDuration] = useState(0.45);
  const [kenBurnsIntensity, setKenBurnsIntensity] = useState(0.045);
  const [renderQuality, setRenderQuality] = useState<"preview" | "balanced" | "final">("balanced");
  const [backgroundMusic, setBackgroundMusic] = useState<"none" | "suspense" | "ambient" | "emotional">("none");
  const [backgroundMusicVolume, setBackgroundMusicVolume] = useState(0.08);
  const [upload, setUpload] = useState(false);
  const [voicePreviewUrl, setVoicePreviewUrl] = useState("");
  const [previewingVoice, setPreviewingVoice] = useState(false);
  const [imagePreviewing, setImagePreviewing] = useState<number | null>(null);

  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewJobId, setReviewJobId] = useState("");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftHook, setDraftHook] = useState("");
  const [draftStory, setDraftStory] = useState("");
  const [scenes, setScenes] = useState<ScenePayload[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectedPreset = useMemo(
    () => PRESETS.find((preset) => preset.width === width && preset.height === height && preset.fps === fps)?.id,
    [fps, height, width]
  );

  const selectedVoiceId = useMemo(
    () => VOICES.find((option) => option.provider === voiceProvider && option.voice === voiceName)?.id ?? "custom",
    [voiceName, voiceProvider]
  );

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const refreshJob = useCallback(
    async (jobId: string) => {
      try {
        const nextJob = await apiRequest<JobStatus>(`/status/${jobId}`);
        setJob(nextJob);
        if (["awaiting_confirmation", "done", "error"].includes(nextJob.status)) {
          stopPolling();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not refresh job");
        stopPolling();
      }
    },
    [stopPolling]
  );

  const startPolling = useCallback(
    (jobId: string) => {
      stopPolling();
      void refreshJob(jobId);
      pollRef.current = setInterval(() => {
        void refreshJob(jobId);
      }, 1800);
    },
    [refreshJob, stopPolling]
  );

  useEffect(() => stopPolling, [stopPolling]);

  useEffect(() => {
    if (job?.status === "awaiting_confirmation" && job.job_id !== reviewJobId) {
      setDraftTitle(job.title);
      setDraftHook(job.hook);
      setDraftStory(job.story);
      setScenes(job.scenes);
      setReviewJobId(job.job_id);
    }
  }, [job, reviewJobId]);

  const isRunning = Boolean(job && !["awaiting_confirmation", "done", "error"].includes(job.status));
  const draftReady = job?.status === "awaiting_confirmation";
  const hasOutput = Boolean(job?.video_url);
  const uploadedImages = job?.uploaded_images ?? [];
  const estimatedDuration = scenes.reduce((total, scene) => total + Number(scene.duration || 0), 0);
  const needsUpload = imageSource === "upload";
  const uploadReady = !needsUpload || uploadedFiles.length > 0 || uploadedImages.length > 0;
  const canSubmitDraft = topic.trim().length >= 3 && !busy && !isRunning;
  const canConfirm =
    draftReady && Boolean(draftTitle.trim()) && Boolean(draftStory.trim()) && scenes.length > 0 && uploadReady && !busy;

  const renderSettings = {
    script_language: scriptLanguage,
    pronunciation_map: pronunciationMap,
    image_source: imageSource,
    image_fit_mode: imageFitMode,
    voice_provider: voiceProvider,
    voice_name: voiceName,
    voice_rate: voiceRate,
    voice_pitch: voicePitch,
    subtitles_enabled: subtitlesEnabled,
    subtitle_font_size: subtitleFontSize,
    transition_style: transitionStyle,
    transition_duration: transitionDuration,
    ken_burns_intensity: kenBurnsIntensity,
    render_quality: renderQuality,
    background_music: backgroundMusic,
    background_music_volume: backgroundMusicVolume,
    upload_to_youtube: upload
  };

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmitDraft) return;
    setBusy(true);
    setError("");
    setReviewJobId("");
    setJob(null);
    try {
      const nextJob = await apiRequest<JobStatus>("/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: topic.trim(),
          details: details.trim(),
          video_width: width,
          video_height: height,
          video_fps: fps,
          image_count: imageCount,
          ...renderSettings
        })
      });
      setJob(nextJob);
      startPolling(nextJob.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Draft request failed");
    } finally {
      setBusy(false);
    }
  }

  async function uploadImages(jobId: string) {
    if (!needsUpload) return;
    if (!uploadedFiles.length) return;
    const formData = new FormData();
    uploadedFiles.forEach((file) => formData.append("files", file));
    const nextJob = await apiRequest<JobStatus>(`/uploads/${jobId}`, {
      method: "POST",
      body: formData
    });
    setJob(nextJob);
  }

  async function previewVoice() {
    setPreviewingVoice(true);
    setError("");
    try {
      const text = draftReady && scenes[0]?.narration ? scenes[0].narration : topic;
      const result = await apiRequest<{ audio_url: string }>("/voice-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          voice_provider: voiceProvider,
          voice_name: voiceName,
          voice_rate: voiceRate,
          voice_pitch: voicePitch,
          pronunciation_map: pronunciationMap
        })
      });
      setVoicePreviewUrl(assetUrl(result.audio_url));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice preview failed");
    } finally {
      setPreviewingVoice(false);
    }
  }

  async function previewSceneImage(index: number) {
    if (!job) return;
    const scene = scenes[index];
    if (!scene?.image_prompt?.trim()) return;
    setImagePreviewing(index);
    setError("");
    try {
      const nextJob = await apiRequest<JobStatus>(`/preview-image/${job.job_id}/${scene.number}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: scene.image_prompt,
          fit_mode: imageFitMode
        })
      });
      setJob(nextJob);
      setScenes(nextJob.scenes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image preview failed");
    } finally {
      setImagePreviewing(null);
    }
  }

  function saveProject() {
    const project = {
      topic,
      details,
      script_language: scriptLanguage,
      pronunciation_map: pronunciationMap,
      title: draftTitle,
      hook: draftHook,
      story: draftStory,
      scenes,
      settings: {
        video_width: width,
        video_height: height,
        video_fps: fps,
        image_count: imageCount,
        ...renderSettings
      }
    };
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${topic.trim().replace(/[^a-z0-9]+/gi, "-").slice(0, 40) || "crime-video-project"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function loadProject(file: File) {
    setError("");
    try {
      const project = JSON.parse(await file.text());
      setTopic(project.topic ?? "");
      setDetails(project.details ?? "");
      setScriptLanguage(project.script_language ?? "en");
      setPronunciationMap(project.pronunciation_map ?? "");
      setDraftTitle(project.title ?? "");
      setDraftHook(project.hook ?? "");
      setDraftStory(project.story ?? "");
      setScenes(project.scenes ?? []);
      const settings = project.settings ?? {};
      setWidth(settings.video_width ?? 1280);
      setHeight(settings.video_height ?? 720);
      setFps(settings.video_fps ?? 24);
      setImageCount(settings.image_count ?? (project.scenes?.length || 12));
      setImageSource(settings.image_source ?? "ai");
      setImageFitMode(settings.image_fit_mode ?? "contain_blur");
      setVoiceProvider(settings.voice_provider ?? "edge");
      setVoiceName(settings.voice_name ?? "en-IN-PrabhatNeural");
      setVoiceRate(settings.voice_rate ?? "+0%");
      setVoicePitch(settings.voice_pitch ?? "+0Hz");
      setSubtitlesEnabled(settings.subtitles_enabled ?? true);
      setSubtitleFontSize(settings.subtitle_font_size ?? 18);
      setTransitionStyle(settings.transition_style ?? "crossfade");
      setTransitionDuration(settings.transition_duration ?? 0.45);
      setKenBurnsIntensity(settings.ken_burns_intensity ?? 0.045);
      setRenderQuality(settings.render_quality ?? "balanced");
      setBackgroundMusic(settings.background_music ?? "none");
      setBackgroundMusicVolume(settings.background_music_volume ?? 0.08);
      const imported = await apiRequest<JobStatus>("/project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(project)
      });
      setJob(imported);
      setReviewJobId(imported.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load project");
    }
  }

  async function confirmScript() {
    if (!job || !canConfirm) return;
    setBusy(true);
    setError("");
    try {
      await uploadImages(job.job_id);
      const nextJob = await apiRequest<JobStatus>(`/confirm/${job.job_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: draftTitle.trim(),
          hook: draftHook.trim(),
          story: draftStory.trim(),
          scenes,
          ...renderSettings
        })
      });
      setJob(nextJob);
      startPolling(nextJob.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirmation failed");
    } finally {
      setBusy(false);
    }
  }

  function applyPreset(preset: Preset) {
    setWidth(preset.width);
    setHeight(preset.height);
    setFps(preset.fps);
  }

  function chooseVoice(id: string) {
    const option = VOICES.find((item) => item.id === id);
    if (!option) return;
    setVoiceProvider(option.provider);
    setVoiceName(option.voice);
  }

  function chooseLanguage(language: ScriptLanguage) {
    setScriptLanguage(language);
    const voice = LANGUAGE_DEFAULTS[language];
    setVoiceProvider(voice.provider);
    setVoiceName(voice.voice);
  }

  function updateScene<K extends keyof ScenePayload>(index: number, key: K, value: ScenePayload[K]) {
    setScenes((current) =>
      current.map((scene, sceneIndex) => (sceneIndex === index ? { ...scene, [key]: value } : scene))
    );
  }

  function addScene() {
    setScenes((current) => [
      ...current,
      {
        number: current.length + 1,
        duration: 6,
        narration: "",
        visual_desc: "",
        image_prompt: "",
        upload_image_index: null
      }
    ]);
  }

  function removeScene(index: number) {
    setScenes((current) =>
      current
        .filter((_, sceneIndex) => sceneIndex !== index)
        .map((scene, sceneIndex) => ({ ...scene, number: sceneIndex + 1 }))
    );
  }

  return (
    <main className="studio-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Modern dark studio</p>
          <h1>Crime Video Agent</h1>
        </div>
        <div className="api-pill">
          <span className="dot" />
          {API_BASE}
        </div>
        <div className="top-actions">
          <button className="secondary-action" type="button" onClick={saveProject}>
            <Save size={16} />
            <span>Save Project</span>
          </button>
          <label className="secondary-action file-action">
            <FolderOpen size={16} />
            <span>Load Project</span>
            <input type="file" accept="application/json" onChange={(event) => event.target.files?.[0] && loadProject(event.target.files[0])} />
          </label>
        </div>
      </header>

      {error ? (
        <div className="alert" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      ) : null}

      <section className="workspace-grid">
        <form className="panel input-panel" onSubmit={createDraft}>
          <div className="panel-heading">
            <FileText size={20} />
            <h2>Brief</h2>
          </div>

          <label className="field-label" htmlFor="topic">
            Video topic
          </label>
          <input id="topic" value={topic} onChange={(event) => setTopic(event.target.value)} />

          <label className="field-label" htmlFor="details">
            Topic notes
          </label>
          <textarea
            id="details"
            className="notes-area"
            value={details}
            onChange={(event) => setDetails(event.target.value)}
          />

          <label className="field-label" htmlFor="language">
            Script language
          </label>
          <select id="language" value={scriptLanguage} onChange={(event) => chooseLanguage(event.target.value as ScriptLanguage)}>
            <option value="en">English with Indian accent voice</option>
            <option value="hi">Hindi script and Hindi voice</option>
            <option value="mr">Marathi script and Marathi voice</option>
          </select>

          <label className="field-label" htmlFor="pronunciation">
            Pronunciation dictionary
          </label>
          <textarea
            id="pronunciation"
            className="pronunciation-area"
            value={pronunciationMap}
            onChange={(event) => setPronunciationMap(event.target.value)}
            placeholder="Name = phonetic spelling"
          />

          <div className="panel-heading compact">
            <Settings2 size={18} />
            <h2>Canvas</h2>
          </div>

          <div className="preset-row">
            {PRESETS.map((preset) => {
              const Icon = preset.icon;
              return (
                <button
                  type="button"
                  key={preset.id}
                  className={selectedPreset === preset.id ? "preset active" : "preset"}
                  onClick={() => applyPreset(preset)}
                  title={`${preset.width}x${preset.height} at ${preset.fps}fps`}
                >
                  <Icon size={17} />
                  <span>{preset.label}</span>
                </button>
              );
            })}
          </div>

          <div className="settings-grid">
            <label>
              Width
              <input type="number" min={320} max={3840} value={width} onChange={(e) => setWidth(Number(e.target.value))} />
            </label>
            <label>
              Height
              <input type="number" min={320} max={3840} value={height} onChange={(e) => setHeight(Number(e.target.value))} />
            </label>
            <label>
              FPS
              <input type="number" min={12} max={60} value={fps} onChange={(e) => setFps(Number(e.target.value))} />
            </label>
          </div>

          <div className="panel-heading compact">
            <ImageIcon size={18} />
            <h2>Images</h2>
          </div>

          <div className="segmented">
            <button
              type="button"
              className={imageSource === "ai" ? "segment active" : "segment"}
              onClick={() => setImageSource("ai")}
            >
              <Wand2 size={16} />
              <span>AI</span>
            </button>
            <button
              type="button"
              className={imageSource === "upload" ? "segment active" : "segment"}
              onClick={() => setImageSource("upload")}
            >
              <UploadCloud size={16} />
              <span>Upload</span>
            </button>
          </div>

          <label className="field-label" htmlFor="image-count">
            Images / scenes
          </label>
          <div className="range-row">
            <input id="image-count" type="range" min={4} max={24} value={imageCount} onChange={(e) => setImageCount(Number(e.target.value))} />
            <input className="count-input" type="number" min={1} max={24} value={imageCount} onChange={(e) => setImageCount(Number(e.target.value))} />
          </div>

          <label className="field-label" htmlFor="fit-mode">
            Fit mode
          </label>
          <select id="fit-mode" value={imageFitMode} onChange={(e) => setImageFitMode(e.target.value as ImageFitMode)}>
            <option value="contain_blur">Fit with cinematic blur</option>
            <option value="cover">Crop to fill canvas</option>
          </select>

          {imageSource === "upload" ? (
            <>
              <label className="upload-zone">
                <UploadCloud size={20} />
                <span>{uploadedFiles.length ? `${uploadedFiles.length} image files selected` : "Select images"}</span>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={(event) => setUploadedFiles(Array.from(event.target.files ?? []))}
                />
              </label>
              {draftReady && uploadedFiles.length ? (
                <button className="secondary-action wide" type="button" onClick={() => job && uploadImages(job.job_id)}>
                  <UploadCloud size={16} />
                  <span>Upload Images to Project</span>
                </button>
              ) : null}
            </>
          ) : null}

          <div className="panel-heading compact">
            <Mic2 size={18} />
            <h2>Voice</h2>
          </div>

          <label className="field-label" htmlFor="voice">
            Narration voice
          </label>
          <select id="voice" value={selectedVoiceId} onChange={(e) => chooseVoice(e.target.value)}>
            {VOICES.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.label}
              </option>
            ))}
          </select>

          <div className="settings-grid two">
            <label>
              Rate
              <input value={voiceRate} onChange={(event) => setVoiceRate(event.target.value)} disabled={voiceProvider === "gtts"} />
            </label>
            <label>
              Pitch
              <input value={voicePitch} onChange={(event) => setVoicePitch(event.target.value)} disabled={voiceProvider === "gtts"} />
            </label>
          </div>

          <button className="secondary-action wide" type="button" onClick={previewVoice} disabled={previewingVoice}>
            {previewingVoice ? <Loader2 className="spin" size={16} /> : <Volume2 size={16} />}
            <span>Preview Voice</span>
          </button>
          {voicePreviewUrl ? <audio className="audio-preview" src={voicePreviewUrl} controls /> : null}

          <div className="panel-heading compact">
            <Captions size={18} />
            <h2>Subtitles</h2>
          </div>

          <label className="check-row">
            <input type="checkbox" checked={subtitlesEnabled} onChange={(event) => setSubtitlesEnabled(event.target.checked)} />
            <span>Burn subtitles</span>
          </label>

          {subtitlesEnabled ? (
            <>
              <label className="field-label" htmlFor="subtitle-size">
                Subtitle size
              </label>
              <div className="range-row">
                <input
                  id="subtitle-size"
                  type="range"
                  min={12}
                  max={48}
                  value={subtitleFontSize}
                  onChange={(event) => setSubtitleFontSize(Number(event.target.value))}
                />
                <input
                  className="count-input"
                  type="number"
                  min={12}
                  max={48}
                  value={subtitleFontSize}
                  onChange={(event) => setSubtitleFontSize(Number(event.target.value))}
                />
              </div>
            </>
          ) : null}

          <div className="panel-heading compact">
            <Layers3 size={18} />
            <h2>Motion</h2>
          </div>

          <label className="field-label" htmlFor="quality">
            Render quality
          </label>
          <select id="quality" value={renderQuality} onChange={(e) => setRenderQuality(e.target.value as "preview" | "balanced" | "final")}>
            <option value="preview">Fast preview</option>
            <option value="balanced">Balanced</option>
            <option value="final">Final quality</option>
          </select>

          <label className="field-label" htmlFor="transition">
            Transition
          </label>
          <select id="transition" value={transitionStyle} onChange={(e) => setTransitionStyle(e.target.value as TransitionStyle)}>
            <option value="crossfade">Crossfade</option>
            <option value="fade">Fade</option>
            <option value="none">None</option>
          </select>

          <label className="field-label" htmlFor="transition-duration">
            Transition seconds
          </label>
          <div className="range-row">
            <input
              id="transition-duration"
              type="range"
              min={0}
              max={1.5}
              step={0.05}
              value={transitionDuration}
              onChange={(event) => setTransitionDuration(Number(event.target.value))}
            />
            <input
              className="count-input"
              type="number"
              min={0}
              max={2}
              step={0.05}
              value={transitionDuration}
              onChange={(event) => setTransitionDuration(Number(event.target.value))}
            />
          </div>

          <label className="field-label" htmlFor="motion">
            Camera motion
          </label>
          <div className="range-row">
            <input
              id="motion"
              type="range"
              min={0}
              max={0.12}
              step={0.005}
              value={kenBurnsIntensity}
              onChange={(event) => setKenBurnsIntensity(Number(event.target.value))}
            />
            <input
              className="count-input"
              type="number"
              min={0}
              max={0.12}
              step={0.005}
              value={kenBurnsIntensity}
              onChange={(event) => setKenBurnsIntensity(Number(event.target.value))}
            />
          </div>

          <label className="field-label" htmlFor="music">
            Background music
          </label>
          <select id="music" value={backgroundMusic} onChange={(e) => setBackgroundMusic(e.target.value as "none" | "suspense" | "ambient" | "emotional")}>
            <option value="none">None</option>
            <option value="suspense">Suspense bed</option>
            <option value="ambient">Ambient bed</option>
            <option value="emotional">Emotional bed</option>
          </select>

          {backgroundMusic !== "none" ? (
            <>
              <label className="field-label" htmlFor="music-volume">
                Music volume
              </label>
              <div className="range-row">
                <input
                  id="music-volume"
                  type="range"
                  min={0}
                  max={0.35}
                  step={0.01}
                  value={backgroundMusicVolume}
                  onChange={(event) => setBackgroundMusicVolume(Number(event.target.value))}
                />
                <input
                  className="count-input"
                  type="number"
                  min={0}
                  max={0.35}
                  step={0.01}
                  value={backgroundMusicVolume}
                  onChange={(event) => setBackgroundMusicVolume(Number(event.target.value))}
                />
              </div>
            </>
          ) : null}

          <label className="check-row">
            <input type="checkbox" checked={upload} onChange={(event) => setUpload(event.target.checked)} />
            <span>YouTube upload</span>
          </label>

          <button className="primary-action" type="submit" disabled={!canSubmitDraft}>
            {busy || isRunning ? <Loader2 className="spin" size={18} /> : <Wand2 size={18} />}
            <span>Create Script Draft</span>
          </button>
        </form>

        <section className="main-column">
          <div className="panel status-panel">
            <div className="status-copy">
              <p className="eyebrow">Job status</p>
              <h2>{statusLabel(job?.status)}</h2>
              {job?.job_id ? <span className="job-id">Job {job.job_id}</span> : <span className="job-id">No job</span>}
            </div>
            <div className="timeline-stats">
              <span>{Math.round(estimatedDuration || job?.estimated_duration || 0)}s</span>
              <span>{scenes.length || job?.image_count || imageCount} scenes</span>
              <span>{width}x{height}</span>
            </div>
            <div className="progress-wrap" aria-label="Progress">
              <div className="progress-value">{job?.progress ?? 0}%</div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${job?.progress ?? 0}%` }} />
              </div>
            </div>
            {job?.job_id ? (
              <button className="icon-button" type="button" title="Refresh status" onClick={() => refreshJob(job.job_id)}>
                <RefreshCw size={18} />
              </button>
            ) : null}
          </div>

          <section className="panel review-panel">
            <div className="panel-heading review-heading">
              <FileText size={20} />
              <h2>Script Review</h2>
              {draftReady ? (
                <span className="ready-badge">
                  <CheckCircle2 size={15} />
                  Ready
                </span>
              ) : null}
            </div>

            <div className={draftReady ? "review-body" : "review-body muted"}>
              <label className="field-label" htmlFor="title">
                Title
              </label>
              <input id="title" value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} disabled={!draftReady} />

              <label className="field-label" htmlFor="hook">
                Hook
              </label>
              <textarea id="hook" value={draftHook} onChange={(event) => setDraftHook(event.target.value)} disabled={!draftReady} />

              <label className="field-label" htmlFor="story">
                Narration script
              </label>
              <textarea
                id="story"
                className="story-area"
                value={draftStory}
                onChange={(event) => setDraftStory(event.target.value)}
                disabled={!draftReady}
              />

              <div className="scene-toolbar">
                <div>
                  <p className="eyebrow">Scenes</p>
                  <strong>{scenes.length} image slots</strong>
                </div>
                <button className="secondary-action" type="button" onClick={addScene} disabled={!draftReady}>
                  <Plus size={16} />
                  <span>Add Scene</span>
                </button>
              </div>

              <div className="scene-list">
                {scenes.map((scene, index) => (
                  <article className="scene-item" key={`${scene.number}-${index}`}>
                    <div className="scene-topline">
                      <span>Scene {index + 1}</span>
                      <div className="scene-controls">
                        <label>
                          Sec
                          <input
                            type="number"
                            min={1}
                            max={60}
                            value={scene.duration}
                            disabled={!draftReady}
                            onChange={(event) => updateScene(index, "duration", Number(event.target.value))}
                          />
                        </label>
                        <button
                          type="button"
                          className="icon-button danger"
                          title="Remove scene"
                          disabled={!draftReady || scenes.length <= 1}
                          onClick={() => removeScene(index)}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                    {scene.image_url ? (
                      <img className="scene-preview" src={assetUrl(scene.image_url)} alt={`Scene ${index + 1} preview`} />
                    ) : null}
                    <label>
                      Narration
                      <textarea
                        value={scene.narration}
                        disabled={!draftReady}
                        onChange={(event) => updateScene(index, "narration", event.target.value)}
                      />
                    </label>
                    <label>
                      Visual
                      <textarea
                        value={scene.visual_desc}
                        disabled={!draftReady}
                        onChange={(event) => updateScene(index, "visual_desc", event.target.value)}
                      />
                    </label>
                    <label>
                      Image prompt
                      <textarea
                        value={scene.image_prompt}
                        disabled={!draftReady || imageSource === "upload"}
                        onChange={(event) => updateScene(index, "image_prompt", event.target.value)}
                      />
                    </label>
                    {imageSource === "upload" ? (
                      <label>
                        Uploaded image
                        <select
                          value={scene.upload_image_index ?? index}
                          disabled={!draftReady || uploadedImages.length === 0}
                          onChange={(event) => updateScene(index, "upload_image_index", Number(event.target.value))}
                        >
                          {uploadedImages.length ? (
                            uploadedImages.map((image) => (
                              <option key={image.index} value={image.index}>
                                {image.index + 1}. {image.name}
                              </option>
                            ))
                          ) : (
                            <option value={index}>Upload images first</option>
                          )}
                        </select>
                      </label>
                    ) : (
                      <button
                        className="secondary-action wide"
                        type="button"
                        disabled={!draftReady || !scene.image_prompt || imagePreviewing === index}
                        onClick={() => previewSceneImage(index)}
                      >
                        {imagePreviewing === index ? <Loader2 className="spin" size={16} /> : <ImageIcon size={16} />}
                        <span>{scene.image_url ? "Regenerate Image" : "Preview Image"}</span>
                      </button>
                    )}
                  </article>
                ))}
              </div>
            </div>

            <div className="confirm-row">
              {needsUpload && draftReady && !uploadedFiles.length ? (
                <div className="inline-warning">
                  <AlertTriangle size={16} />
                  <span>Select at least one image before confirming.</span>
                </div>
              ) : null}
              <button className="primary-action" type="button" disabled={!canConfirm} onClick={confirmScript}>
                {busy && draftReady ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
                <span>Confirm and Generate Video</span>
              </button>
            </div>
          </section>

          <section className="panel output-panel">
            <div className="panel-heading">
              <ImageIcon size={20} />
              <h2>Output</h2>
            </div>
            {hasOutput && job ? (
              <div className="output-grid">
                <video
                  className="video-preview"
                  src={assetUrl(job.video_url)}
                  controls
                  style={{ aspectRatio: `${job.video_width} / ${job.video_height}` }}
                />
                <div className="asset-actions">
                  {job.thumbnail_url ? (
                    <img className="thumbnail-preview" src={assetUrl(job.thumbnail_url)} alt="Generated thumbnail" />
                  ) : null}
                  <a className="secondary-action" href={assetUrl(job.video_url)} target="_blank" rel="noreferrer">
                    <Download size={16} />
                    <span>Download Video</span>
                  </a>
                  {job.thumbnail_url ? (
                    <a className="secondary-action" href={assetUrl(job.thumbnail_url)} target="_blank" rel="noreferrer">
                      <ImageIcon size={16} />
                      <span>Open Thumbnail</span>
                    </a>
                  ) : null}
                  {job.youtube_url ? (
                    <a className="secondary-action" href={job.youtube_url} target="_blank" rel="noreferrer">
                      <Play size={16} />
                      <span>YouTube</span>
                    </a>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="empty-output">
                <Clapperboard size={32} />
                <span>{job?.status === "error" ? "Generation stopped" : "Waiting for rendered video"}</span>
              </div>
            )}
          </section>
        </section>
      </section>
    </main>
  );
}
