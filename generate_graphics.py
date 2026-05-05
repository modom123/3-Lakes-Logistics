"""Generate all Google Play Store graphics for 3 Lakes Driver app."""
from PIL import Image, ImageDraw, ImageFont
import math
import os

OUT = "play-store-graphics"
os.makedirs(OUT, exist_ok=True)

# Brand colors
NAVY       = (15, 40, 90)       # deep navy blue
BLUE       = (30, 80, 172)      # brand blue
LIGHT_BLUE = (59, 130, 246)     # accent
ORANGE     = (234, 88, 12)      # orange accent
WHITE      = (255, 255, 255)
DARK_GRAY  = (20, 25, 40)
MID_GRAY   = (40, 50, 75)
CARD_BG    = (28, 38, 66)


def get_font(size, bold=False):
    """Try system fonts, fall back to default."""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_rounded_rect(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + radius*2, y1 + radius*2], fill=fill)
    draw.ellipse([x2 - radius*2, y1, x2, y1 + radius*2], fill=fill)
    draw.ellipse([x1, y2 - radius*2, x1 + radius*2, y2], fill=fill)
    draw.ellipse([x2 - radius*2, y2 - radius*2, x2, y2], fill=fill)


def draw_truck(draw, cx, cy, size, color=WHITE):
    """Draw a simple truck silhouette."""
    s = size
    # cab
    draw.rectangle([cx - s//2, cy - s//3, cx + s//6, cy + s//4], fill=color)
    # trailer
    draw.rectangle([cx + s//6, cy - s//2, cx + s, cy + s//4], fill=color)
    # wheels
    r = s // 7
    draw.ellipse([cx - s//3 - r, cy + s//4 - r, cx - s//3 + r, cy + s//4 + r], fill=color)
    draw.ellipse([cx + s//2 - r, cy + s//4 - r, cx + s//2 + r, cy + s//4 + r], fill=color)
    draw.ellipse([cx + s*3//4 - r, cy + s//4 - r, cx + s*3//4 + r, cy + s//4 + r], fill=color)
    # windshield
    wc = (NAVY[0]+30, NAVY[1]+50, NAVY[2]+120)
    draw.polygon([
        (cx - s//2 + 4, cy - s//3 + 4),
        (cx + s//8, cy - s//3 + 4),
        (cx + s//8, cy - s//10),
        (cx - s//2 + 4, cy - s//10),
    ], fill=wc)


# ─────────────────────────────────────────────────────────────────
# 1. APP ICON  512 × 512
# ─────────────────────────────────────────────────────────────────
def make_icon():
    img = Image.new("RGB", (512, 512), NAVY)
    draw = ImageDraw.Draw(img)

    # Gradient-ish background circles
    for i in range(8):
        r = 220 - i * 18
        alpha = 40 - i * 4
        c = (BLUE[0], BLUE[1], BLUE[2])
        draw.ellipse([256 - r, 256 - r, 256 + r, 256 + r],
                     fill=(BLUE[0] - i*8, BLUE[1] - i*6, min(255, BLUE[2] + i*4)))

    # Outer ring
    draw.ellipse([30, 30, 482, 482], outline=LIGHT_BLUE, width=6)

    # Truck icon centered
    draw_truck(draw, 200, 256, 110, WHITE)

    # Road line
    draw.rectangle([60, 295, 452, 305], fill=ORANGE)
    # dashes
    for x in range(80, 440, 60):
        draw.rectangle([x, 295, x + 30, 305], fill=NAVY)

    # "3LL" text
    font_big = get_font(96, bold=True)
    font_small = get_font(36)
    draw.text((256, 370), "3LL", fill=WHITE, font=font_big, anchor="mm")
    draw.text((256, 460), "3 Lakes Logistics", fill=LIGHT_BLUE, font=font_small, anchor="mm")

    img.save(f"{OUT}/icon_512x512.png")
    print("✓ icon_512x512.png")


# ─────────────────────────────────────────────────────────────────
# 2. FEATURE GRAPHIC  1024 × 500
# ─────────────────────────────────────────────────────────────────
def make_feature():
    img = Image.new("RGB", (1024, 500), NAVY)
    draw = ImageDraw.Draw(img)

    # Background gradient bands
    for i in range(500):
        r = int(NAVY[0] + (BLUE[0] - NAVY[0]) * i / 500)
        g = int(NAVY[1] + (BLUE[1] - NAVY[1]) * i / 500)
        b = int(NAVY[2] + (BLUE[2] - NAVY[2]) * i / 500)
        draw.line([(0, i), (1024, i)], fill=(r, g, b))

    # Orange accent bar left
    draw.rectangle([0, 0, 8, 500], fill=ORANGE)

    # Large truck on right side
    draw_truck(draw, 680, 260, 180, (255, 255, 255, 200))

    # Road stripe
    draw.rectangle([400, 340, 1024, 355], fill=ORANGE)
    for x in range(420, 1000, 80):
        draw.rectangle([x, 340, x + 40, 355], fill=NAVY)

    # Text left side
    font_title  = get_font(80, bold=True)
    font_sub    = get_font(42, bold=True)
    font_body   = get_font(30)

    draw.text((60, 90),  "3 Lakes Driver", fill=WHITE,      font=font_title)
    draw.text((60, 200), "Real-Time Load Management",        fill=LIGHT_BLUE, font=font_sub)
    draw.text((60, 270), "GPS Tracking • Instant Payouts",   fill=WHITE,      font=font_body)
    draw.text((60, 315), "Secure Dispatch Messaging",        fill=WHITE,      font=font_body)

    # Tagline badge
    draw_rounded_rect(draw, [60, 370, 380, 430], 20, ORANGE)
    draw.text((220, 400), "Built for Drivers", fill=WHITE, font=font_body, anchor="mm")

    img.save(f"{OUT}/feature_graphic_1024x500.png")
    print("✓ feature_graphic_1024x500.png")


# ─────────────────────────────────────────────────────────────────
# 3. SCREENSHOTS  1080 × 1920
# ─────────────────────────────────────────────────────────────────

def make_screenshot_base():
    img = Image.new("RGB", (1080, 1920), DARK_GRAY)
    draw = ImageDraw.Draw(img)
    # Status bar
    draw.rectangle([0, 0, 1080, 80], fill=NAVY)
    draw.text((60, 40), "9:41 AM", fill=WHITE, font=get_font(32), anchor="lm")
    draw.text((1020, 40), "▮▮▮▮", fill=WHITE, font=get_font(28), anchor="rm")
    # Bottom nav bar
    draw.rectangle([0, 1750, 1080, 1920], fill=NAVY)
    tabs = ["Home", "Loads", "Messages", "Documents", "Pay"]
    for i, tab in enumerate(tabs):
        x = 108 + i * 216
        draw.text((x, 1835), tab, fill=LIGHT_BLUE if i == 0 else (120, 140, 180),
                  font=get_font(26), anchor="mm")
    return img, ImageDraw.Draw(img)


def card(draw, x, y, w, h, title, lines, badge=None, badge_color=ORANGE):
    draw_rounded_rect(draw, [x, y, x+w, y+h], 18, CARD_BG)
    draw.text((x+24, y+24), title, fill=WHITE, font=get_font(34, bold=True))
    for i, line in enumerate(lines):
        draw.text((x+24, y+76 + i*44), line, fill=(180, 195, 220), font=get_font(28))
    if badge:
        bw = len(badge) * 18 + 30
        draw_rounded_rect(draw, [x+w-bw-20, y+16, x+w-20, y+60], 14, badge_color)
        draw.text((x+w-bw//2-20, y+38), badge, fill=WHITE, font=get_font(24), anchor="mm")


# Screenshot 1 — Home / Dashboard
def make_screenshot_home():
    img, draw = make_screenshot_base()

    # Header
    draw.rectangle([0, 80, 1080, 200], fill=NAVY)
    draw.text((540, 140), "Good morning, James!", fill=WHITE, font=get_font(40, bold=True), anchor="mm")

    # HOS strip
    draw_rounded_rect(draw, [40, 220, 1040, 310], 14, (20, 100, 60))
    draw.text((540, 265), "HOS Status: 8h 22m remaining  ●  On Duty", fill=(100, 240, 150),
              font=get_font(28), anchor="mm")

    # Current load card
    draw_rounded_rect(draw, [40, 330, 1040, 660], 18, CARD_BG)
    draw.text((80, 360), "CURRENT LOAD", fill=ORANGE, font=get_font(26, bold=True))
    draw.text((80, 405), "CHI → LAX", fill=WHITE, font=get_font(56, bold=True))
    draw.text((80, 475), "📦  Frozen Beef  •  42,000 lbs", fill=(180,195,220), font=get_font(30))
    draw.text((80, 525), "🚚  Pickup: 06:00 AM  •  Del: Tomorrow 3 PM", fill=(180,195,220), font=get_font(28))
    draw.text((80, 575), "Broker: Mike Thompson  •  (312) 555-0182", fill=LIGHT_BLUE, font=get_font(28))
    draw_rounded_rect(draw, [820, 595, 1000, 645], 14, (20, 140, 80))
    draw.text((910, 620), "IN TRANSIT", fill=WHITE, font=get_font(26), anchor="mm")

    # Pay summary
    card(draw, 40, 680, 480, 220, "Today's Pay",
         ["Gross:   $1,850.00", "Dispatch: -$148.00", "Net:     $1,657.00"])
    card(draw, 560, 680, 480, 220, "This Week",
         ["Miles:    1,240 mi", "Loads:    3 delivered", "Earned:  $4,920.00"])

    # Quick actions
    draw.text((540, 940), "Quick Actions", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    actions = [("Navigate", BLUE), ("Call Broker", (20,130,80)), ("Upload Doc", ORANGE)]
    for i, (label, color) in enumerate(actions):
        x = 60 + i * 340
        draw_rounded_rect(draw, [x, 970, x+300, 1070], 18, color)
        draw.text((x+150, 1020), label, fill=WHITE, font=get_font(32, bold=True), anchor="mm")

    # Caption bar at top
    draw_rounded_rect(draw, [40, 1100, 1040, 1200], 14, (0,0,0))
    draw.text((540, 1150), "Full load info — address, broker, pay at a glance",
              fill=WHITE, font=get_font(32), anchor="mm")

    img.save(f"{OUT}/screenshot_1_home.png")
    print("✓ screenshot_1_home.png")


# Screenshot 2 — Load Board
def make_screenshot_loads():
    img, draw = make_screenshot_base()
    draw.rectangle([0, 80, 1080, 200], fill=NAVY)
    draw.text((540, 140), "Available Loads", fill=WHITE, font=get_font(44, bold=True), anchor="mm")

    loads = [
        ("Dallas, TX  →  Atlanta, GA",    "48,000 lbs • Dry Van",  "$2,100", "320 mi", (20,140,80)),
        ("Houston, TX  →  Memphis, TN",   "Steel Coils • Flatbed", "$1,875", "490 mi", (20,140,80)),
        ("Denver, CO  →  Phoenix, AZ",    "Produce • Reefer",      "$2,340", "600 mi", (20,140,80)),
        ("Kansas City  →  St. Louis, MO", "Electronics • Dry Van", "$980",   "250 mi", ORANGE),
    ]
    y = 230
    for origin_dest, details, pay, miles, color in loads:
        draw_rounded_rect(draw, [40, y, 1040, y+210], 18, CARD_BG)
        draw.text((60, y+20), origin_dest, fill=WHITE, font=get_font(36, bold=True))
        draw.text((60, y+70), details, fill=(180,195,220), font=get_font(28))
        draw.text((60, y+115), f"Distance: {miles}", fill=(180,195,220), font=get_font(26))
        draw_rounded_rect(draw, [700, y+20, 1000, y+80], 14, color)
        draw.text((850, y+50), pay, fill=WHITE, font=get_font(38, bold=True), anchor="mm")
        draw_rounded_rect(draw, [700, y+100, 870, y+155], 12, BLUE)
        draw_rounded_rect(draw, [890, y+100, 1000, y+155], 12, (150, 40, 40))
        draw.text((785, y+127), "ACCEPT", fill=WHITE, font=get_font(26, bold=True), anchor="mm")
        draw.text((945, y+127), "SKIP", fill=WHITE, font=get_font(26, bold=True), anchor="mm")
        y += 230

    draw_rounded_rect(draw, [40, 1165, 1040, 1265], 14, (0,0,0))
    draw.text((540, 1215), "Accept loads instantly — one tap from the road",
              fill=WHITE, font=get_font(32), anchor="mm")

    img.save(f"{OUT}/screenshot_2_loads.png")
    print("✓ screenshot_2_loads.png")


# Screenshot 3 — Pay Tab
def make_screenshot_pay():
    img, draw = make_screenshot_base()
    draw.rectangle([0, 80, 1080, 200], fill=NAVY)
    draw.text((540, 140), "My Earnings", fill=WHITE, font=get_font(44, bold=True), anchor="mm")

    # Big pay number
    draw_rounded_rect(draw, [40, 220, 1040, 420], 20, CARD_BG)
    draw.text((540, 295), "$12,480.00", fill=(80, 220, 130), font=get_font(80, bold=True), anchor="mm")
    draw.text((540, 385), "Total Earned This Month", fill=(180,195,220), font=get_font(30), anchor="mm")

    # Pay breakdown
    card(draw, 40, 440, 480, 280, "Load #TL-2847",
         ["Gross:      $1,850.00",
          "Dispatch fee: -$148.00",
          "Insurance:    -$45.00",
          "─────────────────",
          "Net Pay:   $1,657.00"], badge="PAID", badge_color=(20,140,80))
    card(draw, 560, 440, 480, 280, "Load #TL-2831",
         ["Gross:      $2,100.00",
          "Dispatch fee: -$168.00",
          "Insurance:    -$45.00",
          "─────────────────",
          "Net Pay:   $1,887.00"], badge="PAID", badge_color=(20,140,80))

    # Request payout button
    draw_rounded_rect(draw, [140, 750, 940, 850], 24, ORANGE)
    draw.text((540, 800), "Request Payout via Stripe", fill=WHITE,
              font=get_font(38, bold=True), anchor="mm")

    # History
    draw.text((60, 890), "Recent Payouts", fill=WHITE, font=get_font(36, bold=True))
    history = [
        ("May 1, 2026", "CHI → LAX",  "$1,657.00", "Deposited"),
        ("Apr 28, 2026","DAL → ATL",  "$1,887.00", "Deposited"),
        ("Apr 25, 2026","HOU → MEM",  "$1,620.00", "Deposited"),
        ("Apr 22, 2026","DEN → PHX",  "$2,095.00", "Deposited"),
    ]
    y = 945
    for date, route, amount, status in history:
        draw.line([(60, y), (1020, y)], fill=(50,60,90), width=1)
        draw.text((60, y+15), date, fill=(180,195,220), font=get_font(26))
        draw.text((300, y+15), route, fill=WHITE, font=get_font(26))
        draw.text((780, y+15), amount, fill=(80,220,130), font=get_font(26))
        draw.text((960, y+15), status, fill=(80,220,130), font=get_font(22))
        y += 65

    draw_rounded_rect(draw, [40, 1210, 1040, 1310], 14, (0,0,0))
    draw.text((540, 1260), "See every payout, deduction, and deposit",
              fill=WHITE, font=get_font(32), anchor="mm")

    img.save(f"{OUT}/screenshot_3_pay.png")
    print("✓ screenshot_3_pay.png")


# Screenshot 4 — Messages
def make_screenshot_messages():
    img, draw = make_screenshot_base()
    draw.rectangle([0, 80, 1080, 200], fill=NAVY)
    draw.text((540, 140), "Dispatch Messages", fill=WHITE, font=get_font(44, bold=True), anchor="mm")

    msgs = [
        ("Dispatch", "Your load TL-2848 is confirmed for 6 AM pickup at\n1420 W 35th St, Chicago IL.", "10:32 AM", False),
        ("Me",       "Got it, on my way.", "10:35 AM", True),
        ("Dispatch", "Broker confirmed. Dock door 7. Ask for Mike.", "10:37 AM", False),
        ("Me",       "Thanks. ETA 45 min.", "10:52 AM", True),
        ("Dispatch", "Load bumped to 7 AM — shipper running late.\nSorry for the change!", "11:04 AM", False),
        ("Me",       "No problem, I'll grab fuel.", "11:06 AM", True),
        ("Dispatch", "Perfect. Safe travels James 🚛", "11:07 AM", False),
    ]
    y = 230
    for sender, text, time, is_me in msgs:
        lines = text.split('\n')
        h = 80 + (len(lines)-1)*38
        if is_me:
            draw_rounded_rect(draw, [400, y, 1020, y+h], 18, BLUE)
            for i, line in enumerate(lines):
                draw.text((710, y+28+i*38), line, fill=WHITE, font=get_font(28), anchor="mm")
            draw.text((1010, y+h+6), time, fill=(120,140,180), font=get_font(22), anchor="rm")
        else:
            draw_rounded_rect(draw, [60, y, 680, y+h], 18, CARD_BG)
            for i, line in enumerate(lines):
                draw.text((370, y+28+i*38), line, fill=WHITE, font=get_font(28), anchor="mm")
            draw.text((70, y+h+6), time, fill=(120,140,180), font=get_font(22))
        y += h + 40

    # Input bar
    draw_rounded_rect(draw, [40, 1640, 1040, 1730], 24, CARD_BG)
    draw.text((120, 1685), "Type a message…", fill=(100,120,160), font=get_font(30), anchor="lm")
    draw_rounded_rect(draw, [950, 1645, 1030, 1725], 18, BLUE)
    draw.text((990, 1685), "▶", fill=WHITE, font=get_font(36), anchor="mm")

    draw_rounded_rect(draw, [40, 1090, 1040, 1190], 14, (0,0,0))
    draw.text((540, 1140), "Direct line to dispatch — instant, no phone tag",
              fill=WHITE, font=get_font(32), anchor="mm")

    img.save(f"{OUT}/screenshot_4_messages.png")
    print("✓ screenshot_4_messages.png")


# Screenshot 5 — GPS / Documents
def make_screenshot_docs():
    img, draw = make_screenshot_base()
    draw.rectangle([0, 80, 1080, 200], fill=NAVY)
    draw.text((540, 140), "Documents", fill=WHITE, font=get_font(44, bold=True), anchor="mm")

    draw.text((60, 230), "Upload Documents", fill=ORANGE, font=get_font(34, bold=True))

    doc_types = [
        ("Bill of Lading (BOL)",    "Required at pickup",      "📄", (20,140,80)),
        ("Proof of Delivery (POD)", "Required at delivery",    "✅", (20,140,80)),
        ("Lumper Receipt",          "If lumper service used",  "🧾", ORANGE),
        ("Insurance Card",          "Annual renewal",          "🛡️", BLUE),
        ("Medical Card",            "DOT required",            "❤️", (150,40,40)),
    ]
    y = 290
    for name, desc, icon, color in doc_types:
        draw_rounded_rect(draw, [40, y, 1040, y+130], 16, CARD_BG)
        draw_rounded_rect(draw, [40, y, 100, y+130], 16, color)
        draw.text((70, y+65), icon, fill=WHITE, font=get_font(36), anchor="mm")
        draw.text((130, y+30), name, fill=WHITE, font=get_font(32, bold=True))
        draw.text((130, y+80), desc, fill=(180,195,220), font=get_font(26))
        draw_rounded_rect(draw, [820, y+35, 1010, y+95], 16, BLUE)
        draw.text((915, y+65), "📷 Upload", fill=WHITE, font=get_font(28), anchor="mm")
        y += 150

    draw_rounded_rect(draw, [40, 1065, 1040, 1165], 14, (0,0,0))
    draw.text((540, 1115), "Snap & submit BOL, POD, and receipts instantly",
              fill=WHITE, font=get_font(32), anchor="mm")

    img.save(f"{OUT}/screenshot_5_documents.png")
    print("✓ screenshot_5_documents.png")


if __name__ == "__main__":
    print("Generating 3 Lakes Driver — Play Store graphics…\n")
    make_icon()
    make_feature()
    make_screenshot_home()
    make_screenshot_loads()
    make_screenshot_pay()
    make_screenshot_messages()
    make_screenshot_docs()
    print(f"\nAll graphics saved to ./{OUT}/")
    print("\nFiles:")
    for f in sorted(os.listdir(OUT)):
        size = os.path.getsize(f"{OUT}/{f}") // 1024
        print(f"  {f}  ({size} KB)")
