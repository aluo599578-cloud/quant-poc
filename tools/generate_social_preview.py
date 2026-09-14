"""generate_social_preview.py — 用 Pillow 画 1280x640 PNG（不依赖 cairo）"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def get_font(size, bold=False):
    """优先用支持中文的字体（msyh.ttc = 微软雅黑）"""
    # msyh.ttc 是 collection 字体，需要指定 index
    candidates = [
        ("C:/Windows/Fonts/msyhbd.ttc", 1) if bold else ("C:/Windows/Fonts/msyh.ttc", 0),  # 微软雅黑
        ("C:/Windows/Fonts/simhei.ttf", None),  # 黑体
        ("C:/Windows/Fonts/simsun.ttc", 0),  # 宋体
        ("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf", None),
    ]
    for c, idx in candidates:
        if os.path.exists(c):
            try:
                if idx is not None:
                    return ImageFont.truetype(c, size, index=idx)
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def main():
    out = Path("docs/screenshots/social_preview.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    W, H = 1280, 640
    img = Image.new("RGB", (W, H), (10, 14, 39))  # #0a0e27
    draw = ImageDraw.Draw(img)

    # 渐变背景（用矩形模拟）
    for y in range(H):
        ratio = y / H
        r = int(10 + (26 - 10) * ratio)
        g = int(14 + (31 - 14) * ratio)
        b = int(39 + (78 - 39) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # 网格线
    for x in range(320, W, 320):
        draw.line([(x, 0), (x, H)], fill=(0, 212, 255, 30), width=1)
    for y in range(160, H, 160):
        draw.line([(0, y), (W, y)], fill=(0, 212, 255, 30), width=1)

    # 股票折线
    points = [(80, 480), (200, 440), (320, 460), (440, 400),
              (560, 380), (680, 300), (800, 320), (920, 240), (1040, 220), (1160, 160)]
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=(0, 212, 255), width=4)
    for x, y in points[:-1]:
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(0, 212, 255))
    # 最后一个点（高亮）
    x, y = points[-1]
    draw.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(0, 212, 255), outline=(255, 255, 255), width=2)

    # 项目名
    draw.text((80, 130), "quant-poc", font=get_font(72, bold=True), fill=(255, 255, 255))
    draw.text((80, 215), "A 股 / 港股 量化研究 PoC", font=get_font(24), fill=(0, 212, 255))
    draw.text((80, 260), "TradingView → Paper Engine → 12 Lean-style Strategies → 富途实盘",
              font=get_font(20), fill=(197, 201, 214))

    # 4 个流程盒子
    boxes = [
        (80, 320, "TradingView", "alert webhook", (0, 212, 255)),
        (340, 320, "Paper Engine", "vnpy + SQLite", (123, 44, 191)),
        (600, 320, "12 Strategies", "Lean-style", (0, 212, 255)),
        (860, 320, "富途 OpenD", "HK 模拟实盘", (123, 44, 191)),
    ]
    for x, y, title, sub, color in boxes:
        draw.rounded_rectangle([x, y, x + 220, y + 80], radius=8, outline=color, width=2,
                              fill=(26, 31, 78))
        # title 居中
        bbox = draw.textbbox((0, 0), title, font=get_font(18, bold=True))
        title_w = bbox[2] - bbox[0]
        draw.text((x + 110 - title_w // 2, y + 18), title,
                  font=get_font(18, bold=True), fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), sub, font=get_font(13))
        sub_w = bbox[2] - bbox[0]
        draw.text((x + 110 - sub_w // 2, y + 48), sub,
                  font=get_font(13), fill=(136, 146, 176))

    # 箭头
    for x in [305, 565, 825]:
        draw.line([(x, 360), (x + 30, 360)], fill=(0, 212, 255), width=2)
        draw.polygon([(x + 30, 355), (x + 30, 365), (x + 38, 360)], fill=(0, 212, 255))

    # 关键数据
    stats_y = 460
    stats = [
        ("最佳 Sharpe", "+2.28", (0, 212, 255)),
        ("策略", "12", (123, 44, 191)),
        ("回测", "100+", (0, 212, 255)),
        ("A股+港股", "4+4", (123, 44, 191)),
        ("License", "MIT", (0, 212, 255)),
    ]
    for i, (label, value, color) in enumerate(stats):
        x = 80 + i * 130
        draw.text((x, stats_y), label, font=get_font(14), fill=(136, 146, 176))
        draw.text((x, stats_y + 25), value, font=get_font(32, bold=True), fill=color)

    # Tech 标签
    draw.text((730, 460), "Tech", font=get_font(14), fill=(136, 146, 176))
    draw.text((730, 490), "vnpy + tushare + futu", font=get_font(18), fill=(197, 201, 214))

    # 右上角 v1.0.0
    draw.rounded_rectangle([(1080, 70), (1240, 100)], radius=15,
                           fill=(0, 212, 255, 30))
    draw.text((1160, 80), "v1.0.0 Public", font=get_font(14), fill=(0, 212, 255))

    # 底部 footer
    draw.text((80, 600), "github.com/aluo599578-cloud/quant-poc", font=get_font(14), fill=(136, 146, 176))
    draw.text((1100, 600), "MIT License", font=get_font(14), fill=(136, 146, 176))

    img.save(out, "PNG", quality=95)
    print(f"✓ PNG: {out}")
    print(f"  size: {out.stat().st_size / 1024:.1f} KB")
    print(f"  dimensions: {img.size}")


if __name__ == "__main__":
    main()
