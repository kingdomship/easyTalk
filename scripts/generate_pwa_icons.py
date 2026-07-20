"""Generate PWA icons (192x192 and 512x512) with a starfield theme."""
import os
from PIL import Image, ImageDraw

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
ICONS_DIR = os.path.join(STATIC_DIR, "icons")
BG = (10, 10, 26, 255)         # #0a0a1a
ACCENT = (124, 131, 255, 255)  # #7c83ff
WHITE = (200, 200, 224, 255)


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)

    # Radial gradient approximation via concentric circles
    cx, cy = size / 2, size / 2
    r_max = size * 0.7
    steps = 30
    for i in range(steps, 0, -1):
        r = r_max * i / steps
        alpha = int(40 * (1 - i / steps))
        color = (ACCENT[0], ACCENT[1], ACCENT[2], alpha)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # Central star — 4-point sparkle
    arm_len = size * 0.18
    arm_w = size * 0.04
    for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
        import math
        rad = math.radians(angle)
        tip_x = cx + arm_len * 2 * math.cos(rad)
        tip_y = cy + arm_len * 2 * math.sin(rad)
        # Horizontal/vertical arms are longer (main cross)
        if angle % 90 == 0:
            l = arm_len * 2.2
        else:
            l = arm_len * 0.8
        perp_rad = rad + math.pi / 2
        pts = [
            (cx + arm_w * math.cos(perp_rad), cy + arm_w * math.sin(perp_rad)),
            (cx + l * math.cos(rad), cy + l * math.sin(rad)),
            (cx - arm_w * math.cos(perp_rad), cy - arm_w * math.sin(perp_rad)),
        ]
        draw.polygon(pts, fill=WHITE)

    # Small center glow
    glow_r = size * 0.08
    for i in range(4, 0, -1):
        r = glow_r * i / 4
        alpha = int(180 * (1 - i / 5))
        color = (255, 255, 255, alpha)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # Tiny dot stars scattered
    import random
    rng = random.Random(42)
    for _ in range(size // 12):
        sx = rng.randint(int(size * 0.05), int(size * 0.95))
        sy = rng.randint(int(size * 0.05), int(size * 0.95))
        dot_r = rng.choice([1, 1.5, 2])
        a = rng.randint(80, 200)
        dot_color = (WHITE[0], WHITE[1], WHITE[2], a)
        draw.ellipse([sx - dot_r, sy - dot_r, sx + dot_r, sy + dot_r], fill=dot_color)

    return img


def main():
    os.makedirs(ICONS_DIR, exist_ok=True)
    for size in [192, 512]:
        img = draw_icon(size)
        path = os.path.join(ICONS_DIR, f"pwa-{size}.png")
        img.save(path, "PNG")
        print(f"Generated {path} ({size}x{size})")


if __name__ == "__main__":
    main()
