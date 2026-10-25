"""Lay out captured UI plus editorial text for the narrated video."""
import sys
from PIL import Image, ImageDraw, ImageFont

source, output, title, points, index = sys.argv[1:]
frame = Image.new("RGB", (1280, 720), "#080d16")
shot = Image.open(source).convert("RGB")
shot.thumbnail((620, 644), Image.Resampling.LANCZOS)
frame.paste(shot, (28 + (620-shot.width)//2, 38 + (644-shot.height)//2))
draw = ImageDraw.Draw(frame)
font = "/System/Library/Fonts/Supplemental/Arial.ttf"
def text(x, y, value, size, color, spacing=10):
    draw.multiline_text((x, y), value, font=ImageFont.truetype(font, size), fill=color, spacing=spacing)
draw.line((675,55,675,665), fill="#253a40", width=1)
text(720,62,"APEXMARKET / MISSION CONTROL",15,"#70e4bf")
text(720,100,"SIMULATED PRODUCT WALKTHROUGH",11,"#edbb72")
text(720,165,title,41,"#e9eff7",12)
text(720,335,points,18,"#a5b7cc",15)
text(720,635,f"{int(index):02} / 09",13,"#70869e")
draw.rectangle((720,604,720+round(int(index)/9*490),607), fill="#70e4bf")
frame.save(output)
