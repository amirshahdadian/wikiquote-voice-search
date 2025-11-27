"""
User Enrollment Script for Voice Recognition System
Enrolls users by collecting audio samples and creating voice profiles
"""

import sys
import os
from pathlib import Path
import sqlite3
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.speaker_identification import SpeakerIdentificationService
from src.wikiquote_voice.config import Config


def get_user_input(prompt: str, default: str = None) -> str:
    """Get user input with optional default"""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        while True:
            user_input = input(f"{prompt}: ").strip()
            if user_input:
                return user_input
            print("This field is required. Please try again.")


def create_tts_preferences(user_id: str):
    """
    Create default TTS preferences for new user in database
    
    Args:
        user_id: User identifier
    """
    db_path = Path(Config.DATA_DIR) / "wikiquote_voice.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tts_preferences (
                user_id TEXT PRIMARY KEY,
                pitch_scale REAL DEFAULT 1.0,
                speaking_rate REAL DEFAULT 1.0,
                energy_scale REAL DEFAULT 1.0,
                style TEXT DEFAULT 'neutral',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Get TTS preferences from user
        print("\n🎛️  Configure TTS Voice Preferences")
        print("=" * 50)
        
        pitch = get_user_input("Pitch scale (0.5-2.0, 1.0=normal)", "1.0")
        speed = get_user_input("Speaking rate (0.5-2.0, 1.0=normal)", "1.0")
        energy = get_user_input("Energy scale (0.5-2.0, 1.0=normal)", "1.0")
        style = get_user_input("Style (neutral/formal/casual)", "neutral")
        
        try:
            pitch = float(pitch)
            speed = float(speed)
            energy = float(energy)
        except ValueError:
            print("⚠️  Invalid numeric value, using defaults")
            pitch, speed, energy = 1.0, 1.0, 1.0
        
        # Insert or update preferences
        cursor.execute("""
            INSERT INTO user_tts_preferences 
            (user_id, pitch_scale, speaking_rate, energy_scale, style, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                pitch_scale = excluded.pitch_scale,
                speaking_rate = excluded.speaking_rate,
                energy_scale = excluded.energy_scale,
                style = excluded.style,
                updated_at = excluded.updated_at
        """, (user_id, pitch, speed, energy, style, datetime.now(), datetime.now()))
        
        conn.commit()
        conn.close()
        
        print(f"✅ TTS preferences saved for '{user_id}'")
        print(f"   Pitch: {pitch}x, Speed: {speed}x, Energy: {energy}x, Style: {style}")
        
    except Exception as e:
        print(f"⚠️  Warning: Failed to save TTS preferences: {e}")


def enroll_user_interactive():
    """Interactive user enrollment workflow"""
    print("\n" + "=" * 60)
    print("🎤 WIKIQUOTE VOICE SEARCH - USER ENROLLMENT")
    print("=" * 60)
    
    # Get user ID
    print("\n📝 User Information")
    user_id = get_user_input("Enter user ID (e.g., john, alice)")
    
    # Check if user already exists
    embeddings_dir = Path(Config.DATA_DIR) / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    
    embedding_file = embeddings_dir / f"{user_id}.pkl"
    if embedding_file.exists():
        overwrite = get_user_input(f"User '{user_id}' already exists. Overwrite? (yes/no)", "no")
        if overwrite.lower() not in ['yes', 'y']:
            print("❌ Enrollment cancelled")
            return
    
    # Get audio files
    print("\n🎙️  Audio Samples")
    print("Please provide 3-5 audio files of the user speaking.")
    print("Each file should be 2-5 seconds of clear speech.")
    print("Supported formats: WAV, MP3, FLAC, OGG")
    print("\nEnter audio file paths (one per line, empty line when done):")
    
    audio_files = []
    while True:
        file_path = input(f"  Audio file {len(audio_files) + 1}: ").strip()
        
        if not file_path:
            if len(audio_files) >= 1:
                break
            else:
                print("⚠️  At least 1 audio file is required")
                continue
        
        # Validate file exists
        if not Path(file_path).exists():
            print(f"❌ File not found: {file_path}")
            continue
        
        audio_files.append(file_path)
        print(f"  ✅ Added: {Path(file_path).name}")
        
        if len(audio_files) >= 5:
            more = get_user_input("Add more files? (yes/no)", "no")
            if more.lower() not in ['yes', 'y']:
                break
    
    if len(audio_files) < 3:
        print(f"⚠️  Warning: Only {len(audio_files)} audio file(s) provided.")
        print("   Recommended: 3-5 files for better accuracy")
        confirm = get_user_input("Continue anyway? (yes/no)", "yes")
        if confirm.lower() not in ['yes', 'y']:
            print("❌ Enrollment cancelled")
            return
    
    # Initialize speaker ID service
    print("\n🔄 Processing...")
    print("This may take a moment...")
    
    try:
        speaker_id = SpeakerIdentificationService(threshold=0.7)
        
        # Enroll user
        print(f"\n📊 Analyzing {len(audio_files)} audio samples...")
        embedding = speaker_id.enroll_speaker(user_id, audio_files)
        
        # Save embedding
        speaker_id.save_embedding(embedding, embedding_file)
        
        print(f"\n✅ SUCCESS! User '{user_id}' enrolled successfully!")
        print(f"💾 Voice profile saved to: {embedding_file}")
        print(f"📊 Embedding shape: {embedding.shape}")
        print(f"📁 Samples used: {len(audio_files)}")
        
        # Create TTS preferences
        create_tts_preferences(user_id)
        
        print("\n" + "=" * 60)
        print("🎉 Enrollment Complete!")
        print("=" * 60)
        print(f"\nUser '{user_id}' can now be identified by voice!")
        print("Next steps:")
        print("  1. Test identification: python services/speaker_identification.py identify <audio.wav>")
        print("  2. Use in voice pipeline: python services/orchestrator.py")
        print("  3. Try in Streamlit app: streamlit run streamlit_app.py")
        
    except Exception as e:
        print(f"\n❌ Enrollment failed: {e}")
        import traceback
        traceback.print_exc()


def enroll_user_batch(user_id: str, audio_files: list):
    """
    Batch enrollment without user interaction
    
    Args:
        user_id: User identifier
        audio_files: List of audio file paths
    """
    print(f"\n🎤 Enrolling user: {user_id}")
    print(f"📁 Audio files: {len(audio_files)}")
    
    # Validate files
    valid_files = []
    for f in audio_files:
        if Path(f).exists():
            valid_files.append(f)
            print(f"  ✅ {Path(f).name}")
        else:
            print(f"  ❌ Not found: {f}")
    
    if not valid_files:
        print("❌ No valid audio files provided")
        return False
    
    try:
        # Initialize service
        speaker_id = SpeakerIdentificationService(threshold=0.7)
        
        # Enroll
        embedding = speaker_id.enroll_speaker(user_id, valid_files)
        
        # Save
        embeddings_dir = Path(Config.DATA_DIR) / "embeddings"
        embeddings_dir.mkdir(parents=True, exist_ok=True)
        embedding_file = embeddings_dir / f"{user_id}.pkl"
        
        speaker_id.save_embedding(embedding, embedding_file)
        
        print(f"✅ User '{user_id}' enrolled successfully!")
        print(f"💾 Saved to: {embedding_file}")
        
        # Create default TTS preferences in database
        db_path = Path(Config.DATA_DIR) / "wikiquote_voice.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tts_preferences (
                user_id TEXT PRIMARY KEY,
                pitch_scale REAL DEFAULT 1.0,
                speaking_rate REAL DEFAULT 1.0,
                energy_scale REAL DEFAULT 1.0,
                style TEXT DEFAULT 'neutral',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            INSERT OR IGNORE INTO user_tts_preferences (user_id)
            VALUES (?)
        """, (user_id,))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Default TTS preferences created")
        
        return True
        
    except Exception as e:
        print(f"❌ Enrollment failed: {e}")
        return False


def list_enrolled_users():
    """List all enrolled users"""
    embeddings_dir = Path(Config.DATA_DIR) / "embeddings"
    
    if not embeddings_dir.exists():
        print("❌ No enrollments directory found")
        return
    
    users = list(embeddings_dir.glob("*.pkl"))
    
    if not users:
        print("📋 No users enrolled yet")
        return
    
    print(f"\n👥 Enrolled Users ({len(users)})")
    print("=" * 50)
    
    for i, user_file in enumerate(users, 1):
        user_id = user_file.stem
        file_size = user_file.stat().st_size
        modified = datetime.fromtimestamp(user_file.stat().st_mtime)
        
        print(f"{i}. {user_id}")
        print(f"   File: {user_file.name}")
        print(f"   Size: {file_size:,} bytes")
        print(f"   Modified: {modified.strftime('%Y-%m-%d %H:%M:%S')}")
        print()


def main():
    """Main entry point"""
    if len(sys.argv) == 1:
        # Interactive mode
        enroll_user_interactive()
    
    elif sys.argv[1] == "list":
        # List enrolled users
        list_enrolled_users()
    
    elif sys.argv[1] == "batch" and len(sys.argv) >= 4:
        # Batch mode: enroll_user.py batch <user_id> <audio1> [audio2 ...]
        user_id = sys.argv[2]
        audio_files = sys.argv[3:]
        enroll_user_batch(user_id, audio_files)
    
    else:
        print("Usage:")
        print("  python enroll_user.py                    # Interactive mode")
        print("  python enroll_user.py list               # List enrolled users")
        print("  python enroll_user.py batch <user_id> <audio1> [audio2 ...]  # Batch mode")


if __name__ == "__main__":
    main()
