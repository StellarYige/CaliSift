"""Synthetic regression images, explicitly not a real-photo acceptance dataset."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ocr"


def main():
    ROOT.mkdir(exist_ok=True)
    font_path = next(
        (
            p
            for p in [
                Path("C:/Windows/Fonts/msyh.ttc"),
                Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            ]
            if p.exists()
        ),
        None,
    )
    if not font_path:
        raise RuntimeError("A Chinese font is needed to regenerate fixtures")
    font = ImageFont.truetype(str(font_path), 30)
    rows = [
        ["日期", "姓名", "事项", "时间"],
        ["2026-09-07", "星辰奕歌", "消防培训", "08:00-10:00"],
        ["2026-09-08", "星辰奕歌甲", "其他安排", "14:00-16:00"],
    ]
    image = Image.new("RGB", (1260, 300), "white")
    draw = ImageDraw.Draw(image)
    xs = [20, 290, 570, 850, 1240]
    ys = [20, 100, 180, 260]
    for x in xs:
        draw.line((x, 20, x, 260), fill="black", width=2)
    for y in ys:
        draw.line((20, y, 1240, y), fill="black", width=2)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            draw.text((xs[c] + 14, ys[r] + 22), value, font=font, fill="black")
    image.save(ROOT / "clean.png")
    image.rotate(90, expand=True, fillcolor="white").save(ROOT / "rotated.png")
    image.rotate(3, expand=True, fillcolor="white").save(ROOT / "skewed.png")
    image.save(ROOT / "compressed.jpg", quality=45)
    image.filter(ImageFilter.GaussianBlur(6)).save(ROOT / "blurred.png")
    merged = Image.new("RGB", (1260, 380), "white")
    merged.paste(image, (0, 80))
    md = ImageDraw.Draw(merged)
    md.rectangle((20, 20, 1240, 100), outline="black", width=2)
    md.text((460, 42), "2026年培训安排", font=font, fill="black")
    merged.save(ROOT / "merged.png")
    unbordered = Image.new("RGB", (1260, 300), "white")
    ud = ImageDraw.Draw(unbordered)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            ud.text((xs[c] + 14, ys[r] + 22), value, font=font, fill="black")
    unbordered.save(ROOT / "borderless.png")
    print(ROOT)


if __name__ == "__main__":
    main()
