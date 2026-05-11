# Demo Video Update Guide

## What This Does

Your demo video currently mentions **$200/month** for the Founders program. This guide updates it to **$300/month**.

**Current:** "The Founders program is $200 a month..."  
**Updated:** "The Founders program is $300 a month. Forever..."

---

## Quick Start (5 minutes)

### Step 1: Install Requirements

**macOS:**
```bash
brew install ffmpeg
pip3 install pydub gtts
```

**Ubuntu/Linux:**
```bash
sudo apt-get install ffmpeg
pip3 install pydub gtts
```

**Windows:**
- Download ffmpeg from https://ffmpeg.org/download.html
- Add to PATH
- Run: `pip install pydub gtts`

---

### Step 2: Run the Update Script

Navigate to your backend directory and run:

```bash
cd backend
python3 update_demo_pricing.py
```

**What it does:**
1. ✅ Generates new voiceover with $300 pricing (using Google TTS)
2. ✅ Extracts audio from your original video
3. ✅ Replaces the last ~30 seconds with updated pricing
4. ✅ Re-encodes the video
5. ✅ Outputs: `demo.mp4` (ready to deploy)

**Expected output:**
```
==================================================
3 Lakes Logistics Demo Video — Pricing Update
Updating voiceover: $200 → $300
==================================================
🎙️  Generating new pricing voiceover ($300/month)...
✓ Pricing voiceover generated: pricing_segment_300.mp3
  Duration: ~17.5 seconds
🔊 Extracting audio from video...
✓ Audio extracted: audio_extracted.wav
🔄 Replacing pricing audio segment...
  Original audio: 203.4s
  New segment: 17.5s
✓ Audio merged: audio_final.wav
  Final duration: 190.9s
🎬 Rebuilding video with updated audio...
✓ Video complete: demo.mp4
  File size: 22.8 MB
🧹 Cleaning up temporary files...
==================================================
✅ SUCCESS! Updated demo video ready:
   /path/to/backend/demo.mp4
==================================================
```

---

### Step 3: Deploy

Once you have `demo.mp4`:

1. **Upload to your web server:**
   ```bash
   scp demo.mp4 your_server:/var/www/3lakeslogistics.com/
   ```

2. **Or use in follow-up emails:**
   - The video is embedded in the follow-up email template
   - Link: `https://3lakeslogistics.com/demo.mp4`

---

## What Changed in the Script

### Original Pricing Text
```
"The Founders program is $200 a month..."
```

### New Pricing Text
```
"The Founders program is $300 a month. Forever. 
That's our commitment to early adopters who trust us to grow with them. 
No per-load fees. No percentage of earnings. 
No surprise price hikes in 18 months. 
$300. All your loads automated. 100% of your earnings."
```

**Duration:** ~17.5 seconds (replaces last 30 seconds of original)

---

## Troubleshooting

### "ffmpeg not found"
- Install ffmpeg (see Step 1 above)
- Verify: `ffmpeg -version`

### "No module named 'pydub'" or "gtts"
```bash
pip install pydub gtts
```

### Audio quality is bad
The script uses Google TTS (free). For professional quality:
1. Manually record the pricing segment
2. Save as `pricing_segment_300.mp3` in the backend folder
3. Run the script (it will use your recording instead)

### Video processing is slow
This is normal. Encoding takes 2-5 minutes depending on your CPU.

---

## Manual Alternative

If the script doesn't work, you can use **DaVinci Resolve** (free):

1. Open `demo-video-original.mp4`
2. Find the last 30 seconds (around 3:30–4:00)
3. Replace audio with new voiceover mentioning $300/month
4. Export as `demo.mp4`

---

## File Locations

```
backend/
├── demo-video-original.mp4       ← Original video ($200)
├── update_demo_pricing.py        ← Update script
├── demo.mp4                      ← Final output ($300) ← USE THIS
├── audio_extracted.wav           ← Temp (auto-deleted)
├── pricing_segment_300.mp3       ← Temp (auto-deleted)
└── audio_final.wav               ← Temp (auto-deleted)
```

---

## Integration with Follow-Up Email

The email template already references:
```
DEMO_VIDEO_URL = "https://3lakeslogistics.com/demo.mp4"
```

So once you deploy the updated `demo.mp4`, it's automatically used in:
- ✅ Follow-up emails (sent to interested prospects)
- ✅ SMS links (calendar + video)
- ✅ Website (if hosted there)

---

## Questions?

If something doesn't work:
1. Check you have ffmpeg: `ffmpeg -version`
2. Check you have Python libraries: `pip list | grep -E "pydub|gtts"`
3. Make sure `demo-video-original.mp4` is in the `backend/` folder

Good luck! 🚀
