"""Generate a simple tray icon for Natural Voice TTS."""

from PIL import Image, ImageDraw, ImageFont

def generate_icon(path: str = 'assets/icon.ico') -> None:
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Blue circle background
        margin = max(1, size // 16)
        draw.ellipse(
            [margin, margin, size - margin - 1, size - margin - 1],
            fill=(50, 120, 220, 255),
        )

        # White "T" letter centered
        font_size = int(size * 0.55)
        try:
            font = ImageFont.truetype('arial.ttf', font_size)
        except OSError:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), 'T', font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (size - tw) // 2 - bbox[0]
        ty = (size - th) // 2 - bbox[1]
        draw.text((tx, ty), 'T', fill=(255, 255, 255, 255), font=font)

        images.append(img)

    # Save as ICO with multiple sizes
    images[0].save(path, format='ICO', sizes=[(s, s) for s in sizes], append_images=images[1:])
    print(f"Icon saved to {path}")


if __name__ == '__main__':
    generate_icon()
