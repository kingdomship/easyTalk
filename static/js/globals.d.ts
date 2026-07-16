// ── Expression system (27 params) ──

interface ExpressionParams {
  eye_curve: number; eye_open: number; eye_pupil: number; eye_wink: number;
  eye_tension: number; iris_size: number;
  mouth_curve: number; mouth_open: number; mouth_width: number; mouth_asym: number;
  lip_pout: number; lip_stretch: number; lip_bite: number; jaw_drop: number; tongue_out: number;
  sparkle: number; brow_angle: number; brow_height: number; brow_asym: number;
  nose_wrinkle: number;
  cheek_raise: number; cheek_puff: number; blush: number;
  head_tilt: number; tear: number; sweat_drop: number; vein_pop: number;
}

interface EmotionFrame {
  params: ExpressionParams;
  duration: number;
  label: string;
}

interface RawEmotion {
  eye_curve?: number; eye_open?: number; eye_pupil?: number; eye_wink?: number;
  eye_tension?: number; iris_size?: number;
  mouth_curve?: number; mouth_open?: number; mouth_width?: number; mouth_asym?: number;
  lip_pout?: number; lip_stretch?: number; lip_bite?: number; jaw_drop?: number; tongue_out?: number;
  sparkle?: number; brow_angle?: number; brow_height?: number; brow_asym?: number;
  nose_wrinkle?: number;
  cheek_raise?: number; cheek_puff?: number; blush?: number;
  head_tilt?: number; tear?: number; sweat_drop?: number; vein_pop?: number;
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

// ── Constellation ──

interface GraphNode {
  id: string; label: string; x: number; y: number;
  vx: number; vy: number; radius: number; color: string;
  isCore: boolean; galaxy: string | null;
  tag: string; summary: string; importance: number;
  galaxyName?: string; clusterSize?: number; opacity?: number;
  onClick?: () => void;
}

interface GraphEdge {
  source: string; target: string; weight: number;
}

interface ConstellationAPI {
  init(data: { nodes: GraphNode[]; edges: GraphEdge[]; coreId?: string; galaxies?: Array<{ id: string; label: string; color: string }> }): void;
  attach(canvas: HTMLCanvasElement): void;
  detach(): void;
  stop(): void;
  clearSelection(): void;
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

interface PankseppAffect {
  seeking: number; play: number; care: number;
  fear: number; rage: number; panic: number;
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
  type: 'emotions' | 'text' | 'done' | 'error' | 'thinking';
  emotions?: RawEmotion[];
  text?: string;
  source?: string;
  label?: string;
  affect?: PankseppAffect;
  color_fields?: ColorField[];
}

interface ColorField {
  color: string;
  cx: number;
  cy: number;
  radius: number;
}

interface DiaryEntry {
  date: string; content: string;
  chat_count: number;
  user_content?: string;
  mood_emoji?: string;
  user_mood_emoji?: string;
  has_user_diary?: boolean;
}

interface NewsItem {
  title: string; url: string; source: string;
}

interface FacePixel {
  r: number; c: number; color: string;
}

// ── Window extension (ui.js / constellation.js) ──

interface ConstellationStarClick {
  id: string; tag: string; summary: string; importance: number;
  color: string; galaxy: string | null; galaxyName?: string;
}

interface Window {
  _onConstellationStarClick?: (star: ConstellationStarClick | null) => void;
}

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
declare function updateMoodFromAffect(affect: PankseppAffect): void;
declare function updateMoodCSS(): void;
declare function updateColorFields(dt: number): void;
declare function circadianBaseColor(): RGB;
declare function circadianBrightness(): number;
declare function updateAtmosphere(dt: number): void;
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
declare function moodStarTint(): string;
declare function drawColorFields(): void;

// ui.js
declare function showDialog(text: string, x?: number, y?: number): void;
declare function checkChoices(text: string): void;
declare function openAuxiliary(tab?: string): void;
declare function closeAuxiliary(): void;
declare function sendMessage(): Promise<void>;
