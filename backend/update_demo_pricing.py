#!/usr/bin/env python3
"""
Update 3 Lakes demo video pricing from $200 to $300 in the voiceover.

This script extracts the audio, replaces the pricing audio segment, and re-encodes.

Requirements:
  - ffmpeg (install: brew install ffmpeg, or apt-get install ffmpeg)
  - pydub (pip install pydub)
  - gtts (pip install gtts)

Usage:
  python3 update_demo_pricing.py

Output:
  - demo-video-updated.mp4 (final video with $300 pricing)
"""
import subprocess
import os
from pathlib import Path
from gtts import gTTS
from pydub import AudioSegment

# Paths
PROJECT_DIR = Path(__file__).parent.absolute()
VIDEO_ORIGINAL = PROJECT_DIR / "demo-video-original.mp4"
VIDEO_OUTPUT = PROJECT_DIR / "demo.mp4"
AUDIO_EXTRACTED = PROJECT_DIR / "audio_extracted.wav"
AUDIO_NEW_SEGMENT = PROJECT_DIR / "pricing_segment_300.mp3"
AUDIO_FINAL = PROJECT_DIR / "audio_final.wav"


def generate_pricing_voiceover():
    """Generate the new pricing voiceover ($300 instead of $200)."""
    print("🎙️  Generating new pricing voiceover ($300/month)...")

    # The text that should replace the $200 mention
    pricing_text = (
        "The Founders program is $300 a month. Forever. "
        "That's our commitment to early adopters who trust us to grow with them. "
        "No per-load fees. No percentage of earnings. No surprise price hikes in 18 months. "
        "$300. All your loads automated. 100% of your earnings."
    )

    # Generate MP3 using Google TTS
    tts = gTTS(text=pricing_text, lang='en', slow=False)
    tts.save(str(AUDIO_NEW_SEGMENT))
    print(f"✓ Pricing voiceover generated: {AUDIO_NEW_SEGMENT}")
    print(f"  Duration: ~{get_audio_duration(AUDIO_NEW_SEGMENT):.1f} seconds")


def get_audio_duration(audio_path):
    """Get duration of audio file in seconds."""
    audio = AudioSegment.from_file(str(audio_path))
    return len(audio) / 1000.0


def extract_audio():
    """Extract audio from video."""
    print("🔊 Extracting audio from video...")
    cmd = [
        "ffmpeg", "-i", str(VIDEO_ORIGINAL),
        "-q:a", "9",  # Quality
        "-n",  # Don't overwrite
        str(AUDIO_EXTRACTED)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"✓ Audio extracted: {AUDIO_EXTRACTED}")


def replace_audio_segment():
    """Replace the last ~30 seconds of audio with updated pricing segment."""
    print("🔄 Replacing pricing audio segment...")

    # Load audio files
    audio_original = AudioSegment.from_file(str(AUDIO_EXTRACTED))
    audio_new = AudioSegment.from_file(str(AUDIO_NEW_SEGMENT))

    # Get durations
    orig_duration = len(audio_original)
    new_duration = len(audio_new)

    print(f"  Original audio: {orig_duration/1000:.1f}s")
    print(f"  New segment: {new_duration/1000:.1f}s")

    # Calculate where to cut (last 30 seconds, but we'll be smart about it)
    # Remove last 30 seconds and append the new segment
    cut_point = max(0, orig_duration - 30000)  # Last 30 seconds

    audio_keep = audio_original[:cut_point]
    audio_final_merged = audio_keep + audio_new

    # Export
    audio_final_merged.export(str(AUDIO_FINAL), format="wav")
    print(f"✓ Audio merged: {AUDIO_FINAL}")
    print(f"  Final duration: {len(audio_final_merged)/1000:.1f}s")


def rebuild_video():
    """Rebuild video with new audio track."""
    print("🎬 Rebuilding video with updated audio...")
    cmd = [
        "ffmpeg", "-i", str(VIDEO_ORIGINAL),
        "-i", str(AUDIO_FINAL),
        "-c:v", "copy",  # Copy video codec (no re-encoding)
        "-c:a", "aac",  # AAC audio codec
        "-map", "0:v:0",  # Map video from first input
        "-map", "1:a:0",  # Map audio from second input
        "-shortest",  # Use shortest stream
        "-n",  # Don't overwrite
        str(VIDEO_OUTPUT)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"✓ Video complete: {VIDEO_OUTPUT}")
    print(f"  File size: {os.path.getsize(VIDEO_OUTPUT) / 1024 / 1024:.1f} MB")


def cleanup():
    """Remove temporary files."""
    print("🧹 Cleaning up temporary files...")
    for f in [AUDIO_EXTRACTED, AUDIO_NEW_SEGMENT, AUDIO_FINAL]:
        if f.exists():
            f.unlink()
            print(f"  Removed: {f.name}")


def main():
    print("=" * 60)
    print("3 Lakes Logistics Demo Video — Pricing Update")
    print("Updating voiceover: $200 → $300")
    print("=" * 60)

    if not VIDEO_ORIGINAL.exists():
        print(f"❌ Error: {VIDEO_ORIGINAL} not found!")
        print(f"   Place demo-video-original.mp4 in: {PROJECT_DIR}")
        return False

    try:
        generate_pricing_voiceover()
        extract_audio()
        replace_audio_segment()
        rebuild_video()
        cleanup()

        print("=" * 60)
        print("✅ SUCCESS! Updated demo video ready:")
        print(f"   {VIDEO_OUTPUT}")
        print("=" * 60)
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg error: {e}")
        print("   Make sure ffmpeg is installed:")
        print("   - macOS: brew install ffmpeg")
        print("   - Ubuntu: sudo apt-get install ffmpeg")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
