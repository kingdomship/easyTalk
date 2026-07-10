// ── Expression system ──

interface ExpressionParams {
  eye_curve: number; eye_open: number; eye_pupil: number;
  mouth_curve: number; mouth_open: number; mouth_width: number;
  sparkle: number; brow_angle: number; brow_height: number; brow_asym: number;
}

interface EmotionFrame {
  params: ExpressionParams;
  duration: number;
  label: string;
}

interface RawEmotion {
  eye_curve?: number; eye_open?: number; eye_pupil?: number;
  mouth_curve?: number; mouth_open?: number; mouth_width?: number;
  sparkle?: number; brow_angle?: number; brow_height?: number; brow_asym?: number;
  duration_ms?: number; label?: string;
  duration?: number;
}

// ── Starfield ──

interface Star {
  x: number; y: number;
  size: number; brightness: number;
  phase: number; speed: number;
  driftX: number; driftY: number;
  color: string | null;
  isFunctional: boolean;
  funcType: string | null;
  funcData: Record<string, unknown> | null;
  targetX: number | null; targetY: number | null; targetColor: string | null;
  trail: Array<{ x: number; y: number }>;
}

interface Meteor {
  x: number; y: number;
  vx: number; vy: number;
  life: number; len: number; angle: number;
  hue: number;
}

interface MemoryStar {
  x: number; y: number;
  date: string; mood: string;
  chat_count: number;
  baseSize: number; phase: number;
  color: string;
}

interface PokeSparkle {
  x: number; y: number;
  vx: number; vy: number;
  life: number; size: number;
}

interface SparkleParticle {
  idx: number;
  x: number; y: number;
  vx: number; vy: number;
  life: number; size: number;
}

// ── Mood ──

interface RGB {
  r: number; g: number; b: number;
}

// ── API ──

interface ChatResponse {
  emotions?: RawEmotion[];
  reply?: string;
  source?: string;
  error?: string;
  label?: string;
}

interface SSEEvent {
  type: 'emotions' | 'text' | 'done' | 'error';
  emotions?: RawEmotion[];
  text?: string;
  source?: string;
  label?: string;
}

interface DiaryEntry {
  date: string; content: string;
  chat_count: number;
}

interface NewsItem {
  title: string; url: string; source: string;
}

interface FacePixel {
  r: number; c: number; color: string;
}

// ── Global DOM refs (declared in engine.js) ──

declare const canvas: HTMLCanvasElement;
declare const ctx: CanvasRenderingContext2D;
declare const inputRow: HTMLDivElement;
declare const input: HTMLInputElement;
declare const sendBtn: HTMLButtonElement;
declare const dialog: HTMLDivElement;
declare const dlgBody: HTMLDivElement;
declare const dlgClose: HTMLButtonElement;
declare const topicBubbles: HTMLDivElement;
declare const auxPanel: HTMLDivElement;
declare const auxContent: HTMLDivElement;
declare const auxBack: HTMLButtonElement;
declare const soundToggle: HTMLButtonElement;
declare const debugTrigger: HTMLDivElement;
declare const debugPanel: HTMLDivElement;

// ── Global state (declared in engine.js) ──

declare const STATE: { readonly STARFIELD: 'starfield'; readonly CONVERGING: 'converging'; readonly CHAT: 'chat'; readonly AUXILIARY: 'auxiliary' };
declare let state: 'starfield' | 'converging' | 'chat' | 'auxiliary';
declare let curParams: ExpressionParams;
declare let tgtParams: ExpressionParams;
declare let moodColor: RGB;
declare let moodTarget: RGB;
declare let pokeActive: boolean;
declare let pokeTimer: number;
declare let pokeSparkles: PokeSparkle[];
declare let sequence: EmotionFrame[];
declare let seqIdx: number;
declare let seqElapsed: number;
declare let replyText: string;
declare let microTimer: number | null;
declare let blinkTimer: number;
declare let isBlinking: boolean;
declare let faceBob: number;
declare let faceFrame: number;
declare let faceCS: number;
declare let faceOx: number;
declare let faceOy: number;
declare let chatFadeIn: number;
declare let sparkleParticles: SparkleParticle[];
declare let soundOn: boolean;
declare let audioCtx: AudioContext | null;
declare let meteorShowerTimer: number;
declare let meteorShowerActive: boolean;
declare let meteors: Meteor[];
declare let memoryStars: MemoryStar[];
declare let stars: Star[];
declare let functionalPoints: Array<{ star: Star; type: 'diary' | 'news'; data: Record<string, unknown> }>;
declare let cursorX: number | null;
declare let cursorY: number | null;
declare let dlgText: string;
declare let dlgDisplayed: number;
declare let dlgTyping: boolean;
declare let clickCount: number;
declare let clickTimer: ReturnType<typeof setTimeout> | null;
declare let pressTimer: ReturnType<typeof setTimeout> | null;
declare let pressStartX: number;
declare let pressStartY: number;
declare let pending: boolean;
declare let lastT: number;
declare let convergeStart: number;
// ── Global functions (declared across files) ──

// engine.js
declare function lerp(a: number, b: number, t: number): number;
declare function easeInOutCubic(t: number): number;
declare function easeOutElastic(t: number): number;
declare function lerpH(c1: string, c2: string, t: number): string;
declare function fd(r: number, c: number): number;
declare function getFacePixels(params: ExpressionParams): FacePixel[];
declare function setSequence(emotions: RawEmotion[], reply: string): void;
declare function updateSequence(dt: number): void;
declare function triggerPokeReaction(cx: number, cy: number): void;
declare function updateMoodFromEmotion(label: string): void;
declare function circadianBaseColor(): RGB;
declare function circadianBrightness(): number;
declare function updateAtmosphere(dt: number): void;
declare function _initAudio(): void;
declare function playTypingSound(): void;
declare function addDebugLog(level: string, title: string, msg: string, analysis?: string): void;
declare function escapeHtml(s: string): string;
declare function resize(): void;

// visuals.js
declare function initStarfield(): void;
declare function initMemoryStars(): Promise<void>;
declare function updateStarfield(dt: number): void;
declare function drawStarfield(): void;
declare function updateMeteors(dt: number): void;
declare function drawMeteors(): void;
declare function drawMemoryStars(): void;
declare function checkMemoryStarClick(cx: number, cy: number): boolean;
declare function drawPokeSparkles(): void;
declare function startConvergence(): void;
declare function updateConvergence(dt: number): void;
declare function drawConvergence(): void;
declare function updateChat(dt: number): void;
declare function drawChat(): void;
declare function updateFacePixelTargets(): void;
declare function recomputeFaceLayout(): void;
declare function drawFaceOnCanvas(params: ExpressionParams, oy: number): void;
declare function initSparkleParticles(): void;
declare function drawSparkleOverlay(oy: number): void;
declare function drawStar(s: Star, alpha?: number): void;
declare function drawConstellations(mx: number | null, my: number | null): void;

// ui.js
declare function showDialog(text: string, x?: number, y?: number): void;
declare function checkChoices(text: string): void;
declare function openAuxiliary(tab?: string): void;
declare function closeAuxiliary(): void;
declare function sendMessage(): Promise<void>;

// ── Constants ──

declare const GRID: 32;
declare const FACE_COLORS: { face: string; faceD: string; outline: string; dark: string; light: string };
declare const NUM_STARS: 180;
declare const NUM_SPARKLES: 55;
declare const CONVERGE_DURATION: 1.5;
declare const LONG_PRESS_DURATION: 1000;
declare const MOVE_THRESHOLD: 10;
declare const POKE_EXPRESSIONS: Array<Partial<ExpressionParams> & { duration_ms: number }>;
declare const ERROR_PATTERNS: Record<string, { cause: string; fix: string }>;
