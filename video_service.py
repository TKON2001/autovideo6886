from pathlib import Path

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    ImageClip,
    afx,
    concatenate_videoclips,
    vfx,
)
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

WIDTH = 1080
HEIGHT = 1920
FPS = 30
BACKGROUND_MUSIC_PATH = Path("assets") / "background_music.mp3"
BACKGROUND_MUSIC_VOLUME = 0.1

# Mobile safe zones (in pixels)
MOBILE_SAFE_TOP = 180
MOBILE_SAFE_BOTTOM = 240
MOBILE_SAFE_SIDE = 90

# Caption layout
CAPTION_MAX_WIDTH = 860
CAPTION_AREA_TOP = 1320
CAPTION_AREA_BOTTOM = 1580
CAPTION_FONT_SIZE_MAIN = 64
CAPTION_FONT_SIZE_SMALL = 42
CAPTION_SIDE_MARGIN = MOBILE_SAFE_SIDE

VIDEO_PRESETS = {
    "standard": {
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "bitrate": "5000k",
        "encoder_preset": "fast",
    },
    "deep": {
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "bitrate": "8000k",
        "encoder_preset": "medium",
    },
    "premium": {
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "bitrate": "10000k",
        "encoder_preset": "medium",
    },
}


def _load_font(size: int):
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans-Bold.ttf",
        "arialbd.ttf",
        "arial.ttf",
    ]

    for font_name in font_candidates:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue

    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current = ""

    dummy_img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(dummy_img)

    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        text_width = bbox[2] - bbox[0]

        if text_width <= max_width:
            current = test
            continue

        if current:
            lines.append(current)
        current = word

    if current:
        lines.append(current)

    return lines


def _caption_layout(caption: str, max_width: int) -> tuple:
    """Layout caption text for mobile safe zone.
    
    For main captions: start at 64px, descend to 56px if needed.
    For secondary text: 38-46px.
    """
    font_size = CAPTION_FONT_SIZE_MAIN
    lines = []

    while font_size >= CAPTION_FONT_SIZE_SMALL:
        font = _load_font(font_size)
        lines = _wrap_text(caption, font, max_width)
        if len(lines) <= 3:
            break
        font_size -= 4

    line_height = int(font_size * 1.22)
    return font, lines, line_height


def _draw_shadow_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    fill: str = "white",
    shadow_alpha: int = 200,
) -> None:
    """Draw text with strong shadow for mobile readability."""
    x, y = xy
    # Multiple shadow offsets for depth
    shadow_offsets = [(0, 2), (2, 2), (-2, 2), (0, 4), (2, 4), (-2, 4), (1, 3), (-1, 3)]
    for offset in shadow_offsets:
        draw.text(
            (x + offset[0], y + offset[1]),
            text,
            font=font,
            fill=(0, 0, 0, shadow_alpha),
        )
    draw.text((x, y), text, font=font, fill=fill)


def _draw_lower_third(draw: ImageDraw.ImageDraw, caption: str) -> None:
    """Draw caption in mobile-safe lower third area.
    
    Caption area: y=1320 to y=1580 (adjusted for 1920px height).
    Safe margins: 90px left/right, 240px bottom, 180px top.
    """
    # Position caption in mobile safe zone
    panel_left = MOBILE_SAFE_SIDE
    panel_right = WIDTH - MOBILE_SAFE_SIDE
    max_width = CAPTION_MAX_WIDTH
    
    font, lines, line_height = _caption_layout(caption, max_width)
    text_height = len(lines) * line_height
    
    # Center caption vertically in safe zone
    # Caption area bottom: 1920 - 240 = 1680
    # Caption area top: 1320
    panel_height = text_height + 80
    panel_bottom = min(HEIGHT - MOBILE_SAFE_BOTTOM, CAPTION_AREA_BOTTOM)
    panel_top = max(panel_bottom - panel_height, CAPTION_AREA_TOP)
    
    # Ensure caption stays within bounds
    if panel_top < CAPTION_AREA_TOP:
        panel_top = CAPTION_AREA_TOP
    if panel_bottom > HEIGHT - MOBILE_SAFE_BOTTOM:
        panel_bottom = HEIGHT - MOBILE_SAFE_BOTTOM
    
    # Draw semi-transparent background
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        radius=24,
        fill=(0, 0, 0, 160),
        outline=(255, 255, 255, 40),
        width=2,
    )
    
    # Draw centered text with strong shadow
    y = panel_top + 40
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (WIDTH - text_width) // 2
        _draw_shadow_text(draw, (x, y), line, font, fill=(255, 255, 255), shadow_alpha=200)
        y += line_height


def _apply_readability_overlay(img: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for y in range(HEIGHT):
        ratio = y / HEIGHT
        alpha = int(30 + 155 * (ratio**1.8))
        draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, alpha))

    vignette = Image.new("L", (WIDTH, HEIGHT), 0)
    vignette_draw = ImageDraw.Draw(vignette)
    vignette_draw.ellipse((-250, -120, WIDTH + 250, HEIGHT + 120), fill=180)
    vignette = ImageOps.invert(vignette.filter(ImageFilter.GaussianBlur(120)))
    edge_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 90))
    overlay = Image.alpha_composite(overlay, Image.composite(edge_overlay, Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)), vignette))

    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _create_fallback_background(index: int) -> Image.Image:
    palettes = [
        ((12, 22, 38), (24, 52, 82), (204, 172, 104)),
        ((18, 24, 38), (64, 36, 88), (128, 191, 189)),
        ((15, 32, 39), (55, 79, 71), (222, 180, 117)),
        ((28, 24, 32), (78, 41, 56), (180, 112, 96)),
    ]
    top, bottom, accent = palettes[index % len(palettes)]
    img = Image.new("RGB", (WIDTH, HEIGHT), top)
    draw = ImageDraw.Draw(img)

    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(top[0] * (1 - ratio) + bottom[0] * ratio)
        g = int(top[1] * (1 - ratio) + bottom[1] * ratio)
        b = int(top[2] * (1 - ratio) + bottom[2] * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    light = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    light_draw = ImageDraw.Draw(light)
    light_draw.ellipse(
        (-220, 190 + index * 45, 720, 1180 + index * 45),
        fill=(*accent, 54),
    )
    light_draw.polygon(
        [(WIDTH, 220), (WIDTH, 1080), (300, 1540), (150, 1040)],
        fill=(*accent, 30),
    )
    light = light.filter(ImageFilter.GaussianBlur(110))

    return Image.alpha_composite(img.convert("RGBA"), light).convert("RGB")


def _finish_slide(img: Image.Image, scene: dict, index: int, output_path: Path) -> Path:
    composed = _apply_readability_overlay(img.convert("RGBA"))
    draw = ImageDraw.Draw(composed)
    _draw_lower_third(draw, scene.get("caption", "Untitled"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    composed.convert("RGB").save(output_path, quality=95)
    return output_path


def create_slide(scene: dict, index: int, output_dir: Path) -> Path:
    img = _create_fallback_background(index)
    path = output_dir / f"slide_{index + 1}.png"
    return _finish_slide(img, scene, index, path)


def create_image_slide(scene: dict, image_path: Path, index: int, output_dir: Path) -> Path:
    with Image.open(image_path) as source:
        img = source.convert("RGB")

    img = ImageOps.fit(
        img,
        (WIDTH, HEIGHT),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )

    path = output_dir / f"image_slide_{index + 1}.png"
    return _finish_slide(img, scene, index, path)


def _target_duration(index: int, scene_durations: list[float] | None) -> float | None:
    if not scene_durations or index >= len(scene_durations):
        return None

    try:
        duration = float(scene_durations[index])
    except (TypeError, ValueError):
        return None

    return max(2.0, duration)


def _make_motion_clip(slide_path: Path, duration: float, index: int):
    # Keep rendering reliable on local Windows machines. MoviePy pan/zoom at
    # 1080x1920 is frame-by-frame and can make short clips take many minutes.
    clip = ImageClip(str(slide_path)).set_duration(duration)

    fade_duration = min(0.45, duration / 5)
    return clip.fx(vfx.fadein, fade_duration).fx(vfx.fadeout, fade_duration)


def _normalized_audio(audio_path: Path):
    audio = AudioFileClip(str(audio_path))
    try:
        return audio.fx(afx.audio_normalize)
    except Exception:
        return audio


def _add_background_music(final_clip):
    if not BACKGROUND_MUSIC_PATH.exists():
        return final_clip, []

    music = AudioFileClip(str(BACKGROUND_MUSIC_PATH))
    music = music.fx(afx.audio_loop, duration=final_clip.duration)
    music = music.volumex(BACKGROUND_MUSIC_VOLUME)

    if final_clip.audio:
        mixed_audio = CompositeAudioClip([final_clip.audio, music])
    else:
        mixed_audio = CompositeAudioClip([music])

    return final_clip.set_audio(mixed_audio), [music, mixed_audio]


def build_video(
    slide_paths: list[Path],
    audio_paths: list[Path],
    output_path: Path,
    scene_durations: list[float] | None = None,
    preset_name: str = "deep",
) -> Path:
    clips = []
    audio_clips = []
    extra_audio_clips = []
    final = None

    preset = VIDEO_PRESETS.get(preset_name, VIDEO_PRESETS["deep"])

    try:
        for index, (slide_path, audio_path) in enumerate(zip(slide_paths, audio_paths)):
            audio = _normalized_audio(audio_path)
            audio_clips.append(audio)

            target_duration = _target_duration(index, scene_durations)
            duration = max(audio.duration + 0.25, target_duration or 0)
            clip = _make_motion_clip(slide_path, duration, index).set_audio(audio)
            clips.append(clip)

        final = concatenate_videoclips(clips, method="compose")
        final, extra_audio_clips = _add_background_music(final)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        final.write_videofile(
            str(output_path),
            fps=preset["fps"],
            codec="libx264",
            audio_codec="aac",
            bitrate=preset["bitrate"],
            preset=preset["encoder_preset"],
            threads=4,
            temp_audiofile=str(output_path.parent / "temp_audio.m4a"),
            remove_temp=True,
            ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            verbose=False,
            logger=None,
        )

        return output_path
    finally:
        if final is not None:
            final.close()

        for clip in clips:
            clip.close()

        for audio in audio_clips + extra_audio_clips:
            try:
                audio.close()
            except Exception:
                pass
