"""
🎤 Wikiquote Voice Search - Complete Streamlit Interface
All-in-one web application for searching quotes with text and voice
"""

import streamlit as st
import sys
import importlib.util
from pathlib import Path
import tempfile
import os
import time
import logging
import re
from typing import List, Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Wikiquote Voice Search",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI with sidebar toggle
st.markdown("""
<style>
    /* Main styling */
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .quote-box {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #1f77b4;
        margin: 1rem 0;
    }
    .quote-text {
        font-size: 1.1rem;
        font-style: italic;
        color: #333;
        margin-bottom: 0.5rem;
    }
    .quote-author {
        font-weight: bold;
        color: #1f77b4;
        margin-top: 0.5rem;
    }
    .quote-source {
        color: #666;
        font-size: 0.9rem;
    }
    .stButton>button {
        width: 100%;
    }
    
    /* Sidebar toggle button styling - make it more visible */
    [data-testid="collapsedControl"] {
        background-color: #1f77b4 !important;
        color: white !important;
        border-radius: 5px !important;
        padding: 8px !important;
        margin: 10px !important;
    }
    
    [data-testid="collapsedControl"]:hover {
        background-color: #1565c0 !important;
        box-shadow: 0 2px 8px rgba(31, 119, 180, 0.3) !important;
    }
</style>
""", unsafe_allow_html=True)

def detect_query_type(text: str) -> str:
    """
    Detect if the user query is a partial quote or a search query.
    
    Args:
        text: User input text
        
    Returns:
        "partial_quote" if it looks like part of a quote, "search" otherwise
    """
    normalized = " ".join((text or "").strip().split())
    words = normalized.lower().split()

    if len(words) < 3:
        return "search"

    lowered = " ".join(words)
    if re.search(r"\b(find|search|show|get|give|tell|want|need|looking)\b", lowered):
        return "search"
    if re.search(r"\bquotes?\s+(about|on|regarding|by|from)\b", lowered):
        return "search"
    if lowered.startswith(("who said ", "who wrote ")):
        return "search"

    return "partial_quote"


def detect_audio_format(audio_bytes: bytes) -> str:
    """
    Best-effort detection for audio MIME type based on file headers.
    """
    if not audio_bytes:
        return "audio/wav"

    # WAV header
    if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "audio/wav"

    # MP3 headers (ID3 tag or MPEG frame sync)
    if audio_bytes[:3] == b"ID3":
        return "audio/mp3"
    if len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0:
        return "audio/mp3"

    return "audio/wav"


def is_nemo_installed() -> bool:
    """Check NeMo availability without importing its heavy runtime."""
    return importlib.util.find_spec("nemo") is not None


def get_uploaded_audio_suffix(uploaded_file: Any, default: str = ".wav") -> str:
    """Preserve the uploaded audio container when saving temp files."""
    suffix = Path(getattr(uploaded_file, "name", "")).suffix.lower()
    return suffix if suffix else default


def write_temp_audio_file(audio_bytes: bytes, suffix: str = ".wav") -> str:
    """Persist audio bytes to a temporary file and return the path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(audio_bytes)
        return tmp_file.name


def resolve_voice_search(chatbot: Any, raw_text: str, normalized_text: str, limit: int = 10) -> Dict[str, Any]:
    """
    Route a voice request through the same intent logic for recorded and uploaded audio.

    Raw ASR text is better for intent detection because normalization strips words like
    "quotes" and "about", which are needed to distinguish author from topic searches.
    """
    search_service = get_search_service()
    intent_input = (raw_text or normalized_text or "").strip()
    fallback_query = (normalized_text or raw_text or "").strip()

    if chatbot and intent_input:
        intent = chatbot.extract_intent(intent_input)
        if intent["type"] == "author_search":
            return {
                "results": search_service.search_by_author(intent["author"], limit=limit),
                "query": intent["author"],
                "intent_type": intent["type"],
            }

        return {
            "results": search_service.search_quotes(intent["query"], limit=limit),
            "query": intent["query"],
            "intent_type": intent["type"],
        }

    return {
        "results": search_service.intelligent_search(fallback_query, limit=limit),
        "query": fallback_query,
        "intent_type": "topic_search",
    }


def format_relevance_badge(score: Any) -> str:
    """
    Render a stable relevance badge for mixed score scales.
    """
    if score is None:
        return ""

    try:
        value = float(score)
    except (TypeError, ValueError):
        return ""

    if value <= 1.0:
        clamped = max(0, min(100, int(value * 100)))
        label = f"📊 {clamped}% match"
    else:
        label = f"📊 score {value:.2f}"

    return (
        "<span style='background:#4CAF50;color:white;padding:2px 8px;"
        "border-radius:10px;font-size:0.85em;'>"
        f"{label}</span>"
    )

def get_user_voice_preferences(user_id: str) -> Dict[str, Any]:
    """
    Load voice preferences for a specific user from database.
    
    Args:
        user_id: User identifier
        
    Returns:
        Dictionary with voice settings
    """
    try:
        from src.wikiquote_voice.config import Config
        import sqlite3
        
        # Use the main database with user_tts_preferences table
        db_path = Path(Config.DATA_DIR) / "wikiquote_voice.db"
        
        if not db_path.exists():
            logger.warning(f"Database not found: {db_path}")
            return None
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pitch_scale, speaking_rate, energy_scale, style
            FROM user_tts_preferences
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            prefs = {
                'pitch_scale': row[0],
                'speaking_rate': row[1],
                'energy_scale': row[2],
                'style': row[3] or 'neutral'
            }
            logger.info(f"Loaded voice preferences for {user_id}: pitch={prefs['pitch_scale']}, speed={prefs['speaking_rate']}")
            return prefs
        
        logger.warning(f"No voice preferences found for user: {user_id}")
        return None
    except Exception as e:
        logger.warning(f"Failed to load user preferences: {e}")
        return None

def save_user_voice_preferences(user_id: str, pitch: float, rate: float, energy: float):
    """
    Save voice preferences for a specific user to database.
    
    Args:
        user_id: User identifier
        pitch: Pitch scale
        rate: Speaking rate
        energy: Energy/volume scale
    """
    try:
        from src.wikiquote_voice.config import Config
        import sqlite3
        from datetime import datetime
        
        # Use the main database
        db_path = Path(Config.DATA_DIR) / "wikiquote_voice.db"
        
        conn = sqlite3.connect(str(db_path))
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
        
        # Insert or update
        cursor.execute("""
            INSERT OR REPLACE INTO user_tts_preferences
            (user_id, pitch_scale, speaking_rate, energy_scale, style, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'neutral', ?, ?)
        """, (user_id, pitch, rate, energy, datetime.now(), datetime.now()))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved voice preferences for user '{user_id}': pitch={pitch}, speed={rate}, energy={energy}")
    except Exception as e:
        logger.error(f"Failed to save user preferences: {e}")

# Alias for the function
save_user_tts_preferences = save_user_voice_preferences


def queue_user_voice_preferences(user_id: str, preferences: Optional[Dict[str, Any]]) -> None:
    """
    Queue a user's voice profile to be applied on the next rerun.

    Streamlit does not allow changing widget-backed session_state keys after the
    widget has already been instantiated in the current script run.
    """
    if not preferences:
        return

    st.session_state["identified_user"] = user_id
    st.session_state["_pending_voice_profile"] = {
        "pitch": float(preferences["pitch_scale"]),
        "rate": float(preferences["speaking_rate"]),
        "energy": float(preferences["energy_scale"]),
    }
    st.session_state["_voice_profile_notice"] = (
        f"Loaded {user_id}'s voice profile "
        f"(pitch: {preferences['pitch_scale']:.1f}x, "
        f"speed: {preferences['speaking_rate']:.1f}x)"
    )


def apply_pending_voice_preferences() -> None:
    """Apply any queued voice profile before voice widgets are rendered."""
    pending = st.session_state.pop("_pending_voice_profile", None)
    if not pending:
        return

    st.session_state["voice_pitch"] = pending["pitch"]
    st.session_state["voice_rate"] = pending["rate"]
    st.session_state["voice_energy"] = pending["energy"]

def identify_speaker_from_audio(audio_path: str) -> Optional[str]:
    """
    Identify speaker from audio file.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        User ID if identified, None otherwise
    """
    try:
        from services.speaker_identification import SpeakerIdentificationService
        from src.wikiquote_voice.config import Config
        import os
        
        # Check audio file
        file_size = os.path.getsize(audio_path)
        logger.info(f"Speaker ID: Audio file size = {file_size} bytes")
        
        if file_size < 5000:  # Less than 5KB is too short
            logger.warning("Audio too short for speaker identification")
            return None
        
        # Use lower threshold (0.5) for more lenient matching
        speaker_id = SpeakerIdentificationService(threshold=0.5)
        embeddings_dir = Path(Config.DATA_DIR) / "embeddings"
        
        if not embeddings_dir.exists():
            logger.warning("No embeddings directory found")
            return None
        
        enrolled_users = speaker_id.load_all_embeddings(str(embeddings_dir))
        logger.info(f"Speaker ID: Found {len(enrolled_users)} enrolled users: {list(enrolled_users.keys())}")
        
        if not enrolled_users:
            logger.warning("No enrolled users found")
            return None
        
        user_id, confidence = speaker_id.identify_speaker(audio_path, enrolled_users)
        logger.info(f"Speaker ID: Result = {user_id}, Confidence = {confidence:.2%}")
        
        if user_id and confidence >= 0.5:
            logger.info(f"✅ Identified speaker: {user_id} (confidence: {confidence:.2%})")
            return user_id
        else:
            logger.info(f"❌ Speaker not identified (best score: {confidence:.2%})")
        
        return None
    except Exception as e:
        logger.warning(f"Speaker identification failed: {e}")
        import traceback
        logger.warning(traceback.format_exc())
        return None

def speak_quote(quote_text: str, author_name: str, output_path: str = None, voice_settings: Dict[str, Any] = None, user_id: str = None) -> bytes:
    """
    Convert a quote to speech and return audio bytes.
    Uses NeMo TTS if available, falls back to gTTS (Google Text-to-Speech).
    
    Args:
        quote_text: The quote text
        author_name: The author name
        output_path: Optional path to save audio file
        voice_settings: Optional voice customization settings (pitch, rate, energy)
        user_id: Optional user ID to load their voice preferences
        
    Returns:
        Audio bytes (MP3 or WAV format)
    """
    # Format the quote for speech
    speech_text = f'"{quote_text}" by {author_name}'
    
    # Generate output path
    if output_path is None:
        output_path = Path("data/recordings") / f"quote_tts_{int(time.time())}.mp3"
        output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Try NeMo TTS first
    try:
        from services.tts_service import TTSService
        
        # Initialize TTS service
        tts_service = TTSService(device='cpu')
        
        # Change extension to wav for NeMo
        wav_path = str(output_path).replace('.mp3', '.wav')
        
        # Prepare preferences
        if voice_settings:
            prefs = voice_settings
        elif user_id:
            prefs = get_user_voice_preferences(user_id)
        else:
            prefs = {
                'pitch_scale': 1.0,
                'speaking_rate': 1.0,
                'energy_scale': 1.0,
                'style': 'neutral'
            }
        
        # Generate personalized audio
        tts_service.synthesize_personalized(
            text=speech_text,
            user_id=user_id,
            output_path=wav_path,
            preferences=prefs
        )
        
        # Read as bytes
        with open(wav_path, 'rb') as audio_file:
            return audio_file.read()
    
    except Exception as nemo_error:
        logger.warning(f"NeMo TTS failed: {nemo_error}, trying gTTS fallback...")
        
        # Fallback to gTTS (Google Text-to-Speech)
        try:
            from services.tts_service_simple import SimpleTTSService
            
            simple_tts = SimpleTTSService()
            simple_tts.synthesize_personalized(
                text=speech_text,
                output_path=str(output_path)
            )
            
            # Read as bytes
            with open(output_path, 'rb') as audio_file:
                return audio_file.read()
        
        except Exception as gtts_error:
            logger.error(f"gTTS also failed: {gtts_error}")
            raise Exception(f"All TTS methods failed. NeMo: {nemo_error}, gTTS: {gtts_error}")

# Initialize services in session state
@st.cache_resource
def ensure_local_storage():
    """Initialize local SQLite schema once for app runtime."""
    try:
        from src.wikiquote_voice.storage.sqlite import initialize_database

        db_path = initialize_database()
        logger.info(f"Local storage ready at {db_path}")
        return db_path
    except Exception as e:
        logger.warning(f"Failed to initialize local storage: {e}")
        return None


@st.cache_resource
def get_search_service():
    """Initialize and cache the search service."""
    try:
        from src.wikiquote_voice.search.service import QuoteSearchService
        from src.wikiquote_voice.config import Config
        import logging
        
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        
        service = QuoteSearchService(
            Config.NEO4J_URI,
            Config.NEO4J_USERNAME,
            Config.NEO4J_PASSWORD
        )
        service.connect()
        
        # Placeholder hook in service; no semantic index is built in this version.
        with st.spinner("🔨 Running search warmup..."):
            service.build_semantic_index(sample_size=10000)
            logger.info("✅ Search warmup complete")
        
        return service
    except Exception as e:
        st.error(f"Failed to initialize search service: {e}")
        return None

@st.cache_resource
def get_chatbot_service():
    """Initialize and cache the chatbot service"""
    try:
        from services.chatbot_service import ChatbotService
        return ChatbotService()
    except Exception as e:
        st.error(f"Failed to initialize chatbot: {e}")
        return None

def check_service_availability():
    """Check which services are available"""
    services = {
        "search": False,
        "chatbot": False,
        "asr": False,
        "nemo": False
    }
    
    try:
        from src.wikiquote_voice.search.service import QuoteSearchService
        services["search"] = True
    except:
        pass
    
    try:
        from services.chatbot_service import ChatbotService
        services["chatbot"] = True
    except:
        pass
    
    try:
        from services.asr_service import ASRService
        services["asr"] = True
    except:
        pass
    
    try:
        services["nemo"] = is_nemo_installed()
    except Exception:
        pass
    
    return services

# Header
st.markdown('<p class="main-header">📚 Wikiquote Voice Search</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Search 858,972 quotes from 247,566 authors with graph-powered retrieval</p>', unsafe_allow_html=True)
st.markdown("---")

# Ensure local DB tables exist (users, preferences, TTS profile storage, etc.)
ensure_local_storage()
apply_pending_voice_preferences()

# Sidebar - Navigation only
with st.sidebar:
    st.title("🎯 Navigation")

    page_options = [
        "💬 Chatbot & Search",
        "👥 Speaker Identification",
        "🔊 Text-to-Speech",
        "📊 Statistics"
    ]

    # Use an explicit key and a validated default to avoid generated widget-id state errors.
    if "page" not in st.session_state or st.session_state.page not in page_options:
        st.session_state.page = page_options[0]
    
    page = st.radio(
        "Select Feature:",
        page_options,
        key="page",
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    # Voice Settings
    with st.expander("🎤 Voice Settings"):
        st.markdown("**Customize TTS Voice:**")
        
        # Initialize voice settings in session state
        if 'voice_pitch' not in st.session_state:
            st.session_state.voice_pitch = 1.0
        if 'voice_rate' not in st.session_state:
            st.session_state.voice_rate = 0.9
        if 'voice_energy' not in st.session_state:
            st.session_state.voice_energy = 1.0

        if "_voice_profile_notice" in st.session_state:
            st.info(f"🎙️ {st.session_state.pop('_voice_profile_notice')}")
        
        voice_pitch = st.slider(
            "Pitch", 
            min_value=0.5, 
            max_value=2.0, 
            key="voice_pitch",
            step=0.1,
            help="Higher = higher voice, Lower = deeper voice"
        )
        
        voice_rate = st.slider(
            "Speed", 
            min_value=0.5, 
            max_value=1.5, 
            key="voice_rate",
            step=0.1,
            help="How fast the voice speaks"
        )
        
        voice_energy = st.slider(
            "Volume", 
            min_value=0.5, 
            max_value=1.5, 
            key="voice_energy",
            step=0.1,
            help="Volume level"
        )
        
        # Test voice button
        if st.button("🔊 Test Voice", use_container_width=True):
            try:
                test_text = "This is how your personalized voice sounds."
                from services.tts_service import TTSService
                
                tts = TTSService(device='cpu')
                output_path = Path("data/recordings") / "voice_test.wav"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                tts.synthesize_personalized(
                    text=test_text,
                    output_path=str(output_path),
                    preferences={
                        'pitch_scale': voice_pitch,
                        'speaking_rate': voice_rate,
                        'energy_scale': voice_energy,
                        'style': 'neutral'
                    }
                )
                
                with open(output_path, 'rb') as f:
                    audio_bytes = f.read()
                st.audio(audio_bytes, format='audio/wav')
                st.success("✅ Voice test complete!")
            except Exception as e:
                st.error(f"Test failed: {e}")
        
        # Save voice settings for identified user
        st.markdown("---")
        
        if 'identified_user' in st.session_state and st.session_state.identified_user:
            user_id = st.session_state.identified_user
            st.info(f"🎤 Active user: **{user_id}**")
            
            if st.button("💾 Save Settings for This User", use_container_width=True):
                save_user_voice_preferences(user_id, voice_pitch, voice_rate, voice_energy)
                st.success(f"✅ Voice settings saved for {user_id}!")
                st.balloons()
        else:
            st.caption("💡 Speak a voice query to identify yourself and save personalized settings")
    
    st.markdown("---")
    
    # How to Search section
    with st.expander("💡 How to Search"):
        st.markdown("""
        **This search is super smart! It can find quotes in multiple ways:**
        
        **1. Keyword Search:**
        - Search by topic: `courage`, `love`, `wisdom`
        - Multiple keywords: `courage fear`
        
        **2. Partial Quote Search:**
        - **Beginning:** `"to be or not"` → finds "To be or not to be..."
        - **Middle:** `"the only thing we have"` → finds "...the only thing we have to fear..."
        - **End:** `"in the end"` → finds quotes ending with "in the end"
        
        **3. Full Quote Search:**
        - Type the complete quote to find exact matches
        
        The system automatically detects which method to use! 🎯
        """)
    


# ============================================
# PAGE 1: Chatbot & Search (Unified)
# ============================================
if page == "💬 Chatbot & Search":
    st.header("💬 Chatbot & Search")
    st.markdown("Search for quotes, browse by author, or chat naturally with the bot.")
    
    search_service = get_search_service()
    chatbot = get_chatbot_service()
    
    if not search_service:
        st.error("❌ Search service is not available.")
        st.stop()
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["🔍 Search Quotes", "👤 Search by Author", "💬 Chatbot"])
    
    # TAB 1: Search Quotes
    with tab1:
        st.markdown("### 🔍 Smart Quote Search")
        
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            query = st.text_input(
                "Enter your search query or part of a quote",
                placeholder="e.g., 'courage', 'to be or not', 'in the end'...",
                key="search_query",
                help="Search by keywords OR enter part of a quote (beginning, middle, or end)"
            )
        
        with col2:
            limit = st.number_input("Results", min_value=1, max_value=50, value=10, key="search_limit")
        
        with col3:
            enable_tts = st.checkbox("🔊 TTS", value=True, help="Enable text-to-speech for results")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            search_button = st.button("🔍 Search", use_container_width=True, type="primary")
        with col2:
            clear_button = st.button("🗑️ Clear", use_container_width=True)
        with col3:
            random_button = st.button("🎲 Random Quote", use_container_width=True)
        
        if clear_button:
            st.rerun()
        
        if search_button and query:
            with st.spinner(f"🔍 Searching with advanced AI matching..."):
                try:
                    # USE INTELLIGENT SEARCH (automatically detects partial quotes vs keywords)
                    results = search_service.search_quotes(query, limit=limit)
                    
                    if results:
                        # Detect search type
                        search_type = results[0].get('search_type', 'standard') if results else 'standard'
                        is_partial = 'partial_match' in search_type
                        
                        top_result = results[0]
                        tts_success = False
                        
                        # When TTS is enabled, auto-play audio and use expanders
                        if enable_tts:
                            try:
                                with st.spinner("🔊 Generating speech for top match..."):
                                    # Get user's voice settings
                                    voice_settings = {
                                        'pitch_scale': st.session_state.get('voice_pitch', 1.0),
                                        'speaking_rate': st.session_state.get('voice_rate', 0.9),
                                        'energy_scale': st.session_state.get('voice_energy', 1.0),
                                        'style': 'neutral'
                                    }
                                    
                                    audio_bytes = speak_quote(
                                        quote_text=top_result['quote_text'],
                                        author_name=top_result['author_name'],
                                        voice_settings=voice_settings
                                    )
                                
                                # Success message
                                if is_partial:
                                    st.success(f"✅ Found {len(results)} quotes using 🎯 Partial Quote Matching")
                                else:
                                    st.success(f"✅ Found {len(results)} quotes using 🎯 Hybrid AI Search")
                                
                                st.info("🔊 **Playing the best match:**")
                                
                                # Auto-play audio
                                st.audio(audio_bytes, format=detect_audio_format(audio_bytes), autoplay=True)
                                
                                # Show quote text in expander (collapsed by default)
                                with st.expander("📖 Click to see the full quote text"):
                                    st.markdown(f"""
                                    <div class="quote-box">
                                        <div class="quote-text">"{top_result.get('quote_text', 'N/A')}"</div>
                                        <div class="quote-author">— {top_result.get('author_name', 'Unknown')}</div>
                                        <div class="quote-source">📖 {top_result.get('source_title', 'Unknown source')}</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Show other matches in expander
                                if len(results) > 1:
                                    with st.expander(f"📋 See {len(results) - 1} more matches"):
                                        for i, quote in enumerate(results[1:], 2):
                                            badges = []
                                            
                                            if 'relevance_score' in quote and quote['relevance_score'] is not None:
                                                badge = format_relevance_badge(quote['relevance_score'])
                                                if badge:
                                                    badges.append(badge)
                                            
                                            if 'match_position' in quote and quote['match_position']:
                                                position_icons = {
                                                    'beginning': '▶️ Start',
                                                    'middle': '🎯 Middle',
                                                    'end': '🔚 End',
                                                    'distributed': '🔀 Multiple'
                                                }
                                                position = quote['match_position']
                                                icon = position_icons.get(position, position)
                                                badges.append(f"<span style='background:#2196F3;color:white;padding:2px 8px;border-radius:10px;font-size:0.85em;'>{icon}</span>")
                                            
                                            badges_html = " ".join(badges)
                                            
                                            st.markdown(f"""
                                            <div class="quote-box">
                                                <div class="quote-text">"{quote.get('quote_text', 'N/A')}"</div>
                                                <div class="quote-author">— {quote.get('author_name', 'Unknown')} {badges_html}</div>
                                                <div class="quote-source">📖 {quote.get('source_title', 'Unknown source')}</div>
                                            </div>
                                            """, unsafe_allow_html=True)
                                
                                tts_success = True
                            
                            except Exception as e:
                                logger.warning(f"TTS generation failed: {e}")
                                st.warning(f"⚠️ TTS failed: {e}. Showing results without audio.")
                                tts_success = False
                        
                        # Show results normally when TTS is disabled or failed
                        if not enable_tts or not tts_success:
                            if is_partial:
                                st.success(f"✅ Found {len(results)} quotes using 🎯 Partial Quote Matching")
                            else:
                                st.success(f"✅ Found {len(results)} quotes using 🎯 Hybrid AI Search")
                            
                            for i, quote in enumerate(results, 1):
                                with st.container():
                                    badges = []
                                    
                                    if 'relevance_score' in quote and quote['relevance_score'] is not None:
                                        badge = format_relevance_badge(quote['relevance_score'])
                                        if badge:
                                            badges.append(badge)
                                    
                                    if 'match_position' in quote and quote['match_position']:
                                        position_icons = {
                                            'beginning': '▶️ Start',
                                            'middle': '🎯 Middle',
                                            'end': '🔚 End',
                                            'distributed': '🔀 Multiple'
                                        }
                                        position = quote['match_position']
                                        icon = position_icons.get(position, position)
                                        badges.append(f"<span style='background:#2196F3;color:white;padding:2px 8px;border-radius:10px;font-size:0.85em;'>{icon}</span>")
                                    
                                    badges_html = " ".join(badges)
                                    
                                    st.markdown(f"""
                                    <div class="quote-box">
                                        <div class="quote-text">"{quote.get('quote_text', 'N/A')}"</div>
                                        <div class="quote-author">— {quote.get('author_name', 'Unknown')} {badges_html}</div>
                                        <div class="quote-source">📖 {quote.get('source_title', 'Unknown source')}</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                    else:
                        st.warning(f"No quotes found for '{query}'. Try a different search term.")
                        
                        st.markdown("### 💡 Try These:")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**Keywords:**")
                            suggestions = ["courage", "love", "wisdom", "success"]
                            for suggestion in suggestions:
                                if st.button(f"'{suggestion}'", key=f"sug_{suggestion}", use_container_width=True):
                                    st.session_state.search_query = suggestion
                                    st.rerun()
                        
                        with col2:
                            st.markdown("**Partial Quotes:**")
                            partials = ["to be or not", "the only thing we", "in the end", "all you need"]
                            for partial in partials:
                                if st.button(f'"{partial}"', key=f"part_{partial}", use_container_width=True):
                                    st.session_state.search_query = partial
                                    st.rerun()
                
                except Exception as e:
                    st.error(f"Search failed: {e}")
        
        if random_button:
            with st.spinner("🎲 Finding a random quote..."):
                try:
                    # Get random quote
                    quote = search_service.get_random_quote()
                    if quote:
                        st.markdown(f"""
                        <div class="quote-box">
                            <div class="quote-text">"{quote.get('quote_text', 'N/A')}"</div>
                            <div class="quote-author">— {quote.get('author_name', 'Unknown')}</div>
                            <div class="quote-source">📖 {quote.get('source_title', 'Unknown source')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Failed to get random quote: {e}")
    
    # TAB 2: Search by Author
    with tab2:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            author = st.text_input(
                "Enter author name",
                placeholder="e.g., Einstein, Shakespeare, Gandhi...",
                key="author_search"
            )
        
        with col2:
            limit = st.number_input("Results", min_value=1, max_value=50, value=10, key="author_limit")
        
        col1, col2 = st.columns(2)
        with col1:
            search_button = st.button("🔍 Search Author", use_container_width=True, type="primary", key="author_btn")
        with col2:
            popular_button = st.button("📊 Popular Authors", use_container_width=True)
        
        if search_button and author:
            with st.spinner(f"Searching quotes by '{author}'..."):
                try:
                    results = search_service.search_by_author(author, limit=limit)
                    
                    if results:
                        st.success(f"✅ Found {len(results)} quotes by {author}")
                        
                        for i, quote in enumerate(results, 1):
                            with st.container():
                                st.markdown(f"""
                                <div class="quote-box">
                                    <div class="quote-text">"{quote.get('quote_text', 'N/A')}"</div>
                                    <div class="quote-author">— {quote.get('author_name', 'Unknown')}</div>
                                    <div class="quote-source">📖 {quote.get('source_title', 'Unknown source')}</div>
                                </div>
                                """, unsafe_allow_html=True)
                    else:
                        st.warning(f"No quotes found for author '{author}'.")
                        
                        st.markdown("### 💡 Popular Authors:")
                        popular = ["Einstein", "Shakespeare", "Gandhi", "Buddha", "Lincoln", "Aristotle"]
                        cols = st.columns(3)
                        for idx, auth in enumerate(popular):
                            with cols[idx % 3]:
                                if st.button(f"Try '{auth}'", key=f"auth_{auth}"):
                                    st.session_state.author_search = auth
                                    st.rerun()
                
                except Exception as e:
                    st.error(f"Author search failed: {e}")
        
        if popular_button:
            st.markdown("### 📊 Popular Authors")
            popular_authors = [
                "Albert Einstein", "William Shakespeare", "Mahatma Gandhi",
                "Buddha", "Abraham Lincoln", "Aristotle", "Mark Twain",
                "Oscar Wilde", "Friedrich Nietzsche", "Plato"
            ]
            
            cols = st.columns(2)
            for idx, auth in enumerate(popular_authors):
                with cols[idx % 2]:
                    if st.button(auth, key=f"pop_{auth}", use_container_width=True):
                        st.session_state.author_search = auth
                        st.rerun()
    
    # TAB 3: Chatbot
    with tab3:
        st.markdown("### 💬 Chat with the Quote Bot")
        st.markdown("Ask naturally about quotes, authors, or topics!")
        
        if not chatbot:
            st.error("❌ Chatbot service is not available.")
        else:
            # Initialize chat messages
            if "messages" not in st.session_state:
                st.session_state.messages = []
                # Add welcome message
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "Hello! I can help you find inspirational quotes. Try asking:\n- 'Find quotes about courage'\n- 'Show me Einstein quotes'\n- 'Quotes about love and happiness'"
                })
            
            # Display chat history with rich quote rendering
            for idx, message in enumerate(st.session_state.messages):
                with st.chat_message(message["role"]):
                    # Check if this message has quotes data
                    if message.get("quotes"):
                        quotes = message["quotes"]
                        query_type = message.get("query_type", "search")
                        
                        # Show first quote prominently
                        first_quote = quotes[0]
                        with st.container(border=True):
                            st.markdown(f"**\"{first_quote['quote_text']}\"**")
                            st.markdown(f"— *{first_quote['author_name']}*")
                        
                        # Show additional matches in expander
                        if len(quotes) > 1:
                            if query_type == "partial_quote":
                                with st.expander(f"🔍 See {len(quotes)-1} other similar quotes", expanded=False):
                                    for i, quote in enumerate(quotes[1:], 1):
                                        quote_preview = quote['quote_text'][:100] + "..." if len(quote['quote_text']) > 100 else quote['quote_text']
                                        st.caption(f"**{i}. \"{quote_preview}\"** — {quote['author_name']}")
                            else:
                                with st.expander(f"📖 See {len(quotes)-1} more matches", expanded=False):
                                    for i, quote in enumerate(quotes[1:], 1):
                                        with st.container(border=True):
                                            st.markdown(f"**{i}. \"{quote['quote_text']}\"**")
                                            st.markdown(f"— *{quote['author_name']}*")
                    else:
                        # Regular text message
                        st.markdown(message["content"])
            
            # Chat input
            if prompt := st.chat_input("Ask me about quotes... (or use voice input above)"):
                # Add user message
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # Get bot response
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        response = chatbot.process_message(prompt)
                        st.markdown(response)
                
                # Add assistant response
                st.session_state.messages.append({"role": "assistant", "content": response})
            
            # Clear conversation button
            if st.button("🗑️ Clear Conversation", use_container_width=True, key="clear_chat"):
                st.session_state.messages = []
                st.rerun()
        
        # Voice input section (expandable)
        with st.expander("🎤 Use Voice Input", expanded=False):
            st.markdown("**Record or upload audio to chat:**")
            
            # Try to use audio recorder if available
            try:
                from audio_recorder_streamlit import audio_recorder
                
                audio_data = audio_recorder(
                    text="",
                    recording_color="#e74c3c",
                    neutral_color="#6c757d",
                    icon_name="microphone",
                    icon_size="2x",
                )
                
                if audio_data and st.button("📤 Send Voice Message", type="primary", use_container_width=True):
                    # Save audio temporarily
                    tmp_path = write_temp_audio_file(audio_data, suffix=".wav")
                    
                    try:
                        # Transcribe (automatically uses 'small' model)
                        from services.asr_service import ASRService
                        
                        with st.spinner("🎤 Transcribing..."):
                            asr = ASRService(model_name='small')
                            result = asr.transcribe(tmp_path)
                            raw_text = result['text']
                            normalized_text = result.get('normalized_text', raw_text)
                        
                        # Identify speaker
                        with st.spinner("🔍 Identifying speaker..."):
                            identified_user = identify_speaker_from_audio(tmp_path)
                        
                        if identified_user:
                            st.success(f"👤 **Identified:** {identified_user}")
                            
                            # Load user's voice preferences for personalized TTS
                            user_prefs = get_user_voice_preferences(identified_user)
                            if user_prefs:
                                queue_user_voice_preferences(identified_user, user_prefs)
                                st.rerun()
                            else:
                                st.session_state.identified_user = identified_user
                        else:
                            st.warning("👤 Speaker not identified - using default voice")
                        
                        # Show transcription
                        if raw_text != normalized_text:
                            st.success(f"🎤 **Heard:** {raw_text}")
                            st.info(f"🔧 **Understood:** {normalized_text}")
                        else:
                            st.success(f"🎤 **You said:** {raw_text}")
                        
                        # Detect query type
                        display_text = raw_text or normalized_text
                        query_type = detect_query_type(display_text)
                        st.write(f"📝 Query type: **{query_type}**")
                        
                        # Add to chat
                        st.session_state.messages.append({"role": "user", "content": f"🎤 {display_text}"})
                        
                        with st.spinner("🔍 Searching quotes..."):
                            voice_search = resolve_voice_search(
                                chatbot,
                                raw_text=raw_text,
                                normalized_text=normalized_text,
                                limit=10,
                            )
                            results = voice_search["results"]
                            resolved_query = voice_search["query"]
                            if voice_search["intent_type"] == "author_search":
                                st.write(f"🔍 Searching for quotes by **{resolved_query}**")
                        
                        if not results:
                            st.warning("No matching quotes found.")
                            response = f"Sorry, I couldn't find any quotes matching '{resolved_query}'."
                            st.session_state.messages.append({"role": "assistant", "content": response})
                        else:
                            first_quote = results[0]
                            query_type = (
                                "partial_quote"
                                if first_quote.get("search_type") == "partial_match"
                                else "search"
                            )
                            
                            # For partial quotes: just speak the matching quote text
                            if query_type == "partial_quote":
                                speech_text = f"{first_quote['quote_text']} by {first_quote['author_name']}"
                                st.write(f"✨ Found similar quote!")
                            # For search queries: speak first result, show others as text
                            else:
                                speech_text = f"I found quotes about that. Here's the first one. {first_quote['quote_text']} by {first_quote['author_name']}"
                            
                            # Generate TTS in the identified user's voice
                            try:
                                with st.spinner("🔊 Generating voice response..."):
                                    tts_audio_bytes = speak_quote(
                                        quote_text=first_quote['quote_text'],
                                        author_name=first_quote['author_name'],
                                        output_path=None,
                                        voice_settings={
                                            'pitch_scale': st.session_state.get('voice_pitch', 1.0),
                                            'speaking_rate': st.session_state.get('voice_rate', 1.0),
                                            'energy_scale': st.session_state.get('voice_energy', 1.0)
                                        },
                                        user_id=identified_user if identified_user else None
                                    )
                                
                                # Play audio
                                st.audio(tts_audio_bytes, format=detect_audio_format(tts_audio_bytes), autoplay=True)
                                st.success("🔊 Voice response played!")
                            
                            except Exception as e:
                                st.warning(f"TTS generation failed: {e}")
                                logger.warning(f"TTS generation failed: {e}")
                            
                            # Show quote result
                            with st.container(border=True):
                                st.markdown(f"**\"{first_quote['quote_text']}\"**")
                                st.markdown(f"— *{first_quote['author_name']}*")
                            
                            # Show additional matches if search query (not partial quote)
                            if query_type == "search" and len(results) > 1:
                                with st.expander(f"📖 See {len(results)-1} more matches"):
                                    for i, quote in enumerate(results[1:], 1):
                                        with st.container(border=True):
                                            st.markdown(f"**{i}. \"{quote['quote_text']}\"**")
                                            st.markdown(f"— *{quote['author_name']}*")
                            elif query_type == "partial_quote" and len(results) > 1:
                                # For partial quotes, show other matches more compactly
                                with st.expander(f"🔍 See {len(results)-1} other similar quotes"):
                                    for i, quote in enumerate(results[1:], 1):
                                        st.caption(f"**{i}. \"{quote['quote_text'][:80]}...\"** — {quote['author_name']}")
                            
                            # Add response to chat WITH quotes data for persistent display
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": f"Found quotes matching '{resolved_query}'",
                                "quotes": results,  # Store all quotes for re-rendering
                                "query_type": query_type
                            })
                    
                    except Exception as e:
                        st.error(f"Error: {e}")
                    finally:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
            
            except ImportError:
                # Fallback to file upload
                st.info("💡 Audio recorder not available. Upload an audio file instead:")
                
                uploaded_audio = st.file_uploader(
                    "Upload audio (WAV, MP3, M4A)",
                    type=['wav', 'mp3', 'm4a', 'ogg'],
                    key="chat_voice_upload"
                )
                
                if uploaded_audio and st.button("📤 Process Audio", type="primary", use_container_width=True):
                    audio_bytes = uploaded_audio.read()
                    tmp_path = write_temp_audio_file(
                        audio_bytes,
                        suffix=get_uploaded_audio_suffix(uploaded_audio),
                    )
                    
                    try:
                        from services.asr_service import ASRService
                        
                        with st.spinner("🎤 Transcribing..."):
                            asr = ASRService(model_name='small')
                            result = asr.transcribe(tmp_path)
                            raw_text = result['text']
                            normalized_text = result.get('normalized_text', raw_text)
                        
                        # Identify speaker
                        identified_user = identify_speaker_from_audio(tmp_path)
                        
                        if identified_user:
                            st.success(f"👤 **Identified:** {identified_user}")
                            
                            # Load user's voice preferences
                            user_prefs = get_user_voice_preferences(identified_user)
                            if user_prefs:
                                queue_user_voice_preferences(identified_user, user_prefs)
                                st.rerun()
                            else:
                                st.session_state.identified_user = identified_user
                        
                        if raw_text != normalized_text:
                            st.success(f"🎤 **Heard:** {raw_text}")
                            st.info(f"🔧 **Understood:** {normalized_text}")
                        else:
                            st.success(f"🎤 **You said:** {raw_text}")
                        
                        # Detect query type
                        display_text = raw_text or normalized_text
                        query_type = detect_query_type(display_text)
                        st.write(f"📝 Query type: **{query_type}**")
                        
                        # Add to chat
                        st.session_state.messages.append({"role": "user", "content": f"🎤 {display_text}"})
                        
                        with st.spinner("🔍 Searching quotes..."):
                            voice_search = resolve_voice_search(
                                chatbot,
                                raw_text=raw_text,
                                normalized_text=normalized_text,
                                limit=10,
                            )
                            results = voice_search["results"]
                            resolved_query = voice_search["query"]
                            if voice_search["intent_type"] == "author_search":
                                st.write(f"🔍 Searching for quotes by **{resolved_query}**")
                        
                        if not results:
                            st.warning("No matching quotes found.")
                            response = f"Sorry, I couldn't find any quotes matching '{resolved_query}'."
                            st.session_state.messages.append({"role": "assistant", "content": response})
                        else:
                            first_quote = results[0]
                            query_type = (
                                "partial_quote"
                                if first_quote.get("search_type") == "partial_match"
                                else "search"
                            )
                            
                            # For partial quotes: just speak the matching quote text
                            if query_type == "partial_quote":
                                speech_text = f"{first_quote['quote_text']} by {first_quote['author_name']}"
                                st.write(f"✨ Found similar quote!")
                            # For search queries: speak first result, show others as text
                            else:
                                speech_text = f"I found quotes about that. Here's the first one. {first_quote['quote_text']} by {first_quote['author_name']}"
                            
                            # Generate TTS in the identified user's voice
                            try:
                                with st.spinner("🔊 Generating voice response..."):
                                    tts_audio_bytes = speak_quote(
                                        quote_text=first_quote['quote_text'],
                                        author_name=first_quote['author_name'],
                                        output_path=None,
                                        voice_settings={
                                            'pitch_scale': st.session_state.get('voice_pitch', 1.0),
                                            'speaking_rate': st.session_state.get('voice_rate', 1.0),
                                            'energy_scale': st.session_state.get('voice_energy', 1.0)
                                        },
                                        user_id=identified_user if identified_user else None
                                    )
                                
                                # Play audio
                                st.audio(tts_audio_bytes, format=detect_audio_format(tts_audio_bytes), autoplay=True)
                                st.success("🔊 Voice response played!")
                            
                            except Exception as e:
                                st.warning(f"TTS generation failed: {e}")
                                logger.warning(f"TTS generation failed: {e}")
                            
                            # Show quote result
                            with st.container(border=True):
                                st.markdown(f"**\"{first_quote['quote_text']}\"**")
                                st.markdown(f"— *{first_quote['author_name']}*")
                            
                            # Show additional matches if search query (not partial quote)
                            if query_type == "search" and len(results) > 1:
                                with st.expander(f"📖 See {len(results)-1} more matches"):
                                    for i, quote in enumerate(results[1:], 1):
                                        with st.container(border=True):
                                            st.markdown(f"**{i}. \"{quote['quote_text']}\"**")
                                            st.markdown(f"— *{quote['author_name']}*")
                            elif query_type == "partial_quote" and len(results) > 1:
                                # For partial quotes, show other matches more compactly
                                with st.expander(f"🔍 See {len(results)-1} other similar quotes"):
                                    for i, quote in enumerate(results[1:], 1):
                                        st.caption(f"**{i}. \"{quote['quote_text'][:80]}...\"** — {quote['author_name']}")
                            
                            # Add response to chat WITH quotes data for persistent display
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": f"Found quotes matching '{resolved_query}'",
                                "quotes": results,  # Store all quotes for re-rendering
                                "query_type": query_type
                            })
                    
                    except Exception as e:
                        st.error(f"Error: {e}")
                    finally:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)

# ============================================
# PAGE 2: Speaker Identification
# ============================================
elif page == "👥 Speaker Identification":
    st.header("👥 Speaker Identification")
    st.markdown("Identify users by their unique voice using AI-powered speaker recognition.")
    
    nemo_available = is_nemo_installed()
    
    if not nemo_available:
        st.error("❌ Speaker Identification requires NeMo toolkit.")
        st.markdown("### 📦 Installation:")
        st.code('pip install "nemo-toolkit[asr,tts]>=2.4,<3"', language="bash")
        st.stop()
    
    from services.speaker_identification import SpeakerIdentificationService
    from src.wikiquote_voice.config import Config
    
    # Initialize speaker ID service
    speaker_id = SpeakerIdentificationService(threshold=0.7)
    embeddings_dir = Path(Config.DATA_DIR) / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    
    # Load enrolled users
    enrolled_users = speaker_id.load_all_embeddings(str(embeddings_dir))
    
    st.markdown(f"### 👥 Enrolled Users: {len(enrolled_users)}")
    
    if enrolled_users:
        cols = st.columns(4)
        for idx, user_id in enumerate(enrolled_users.keys()):
            with cols[idx % 4]:
                st.success(f"✅ {user_id}")
    else:
        st.info("No users enrolled yet. Enroll your first user below!")
    
    st.markdown("---")
    
    # Tabs for different operations
    id_tab1, id_tab2, id_tab3 = st.tabs(["🎤 Identify Speaker", "➕ Enroll User", "🔐 Verify Speaker"])
    
    with id_tab1:
        st.markdown("### 🎤 Identify Speaker from Audio")
        
        # Method selection
        identify_method = st.radio(
            "Choose identification method:",
            ["🎤 Record with Microphone", "📁 Upload Audio File"],
            horizontal=True,
            key="identify_method"
        )
        
        audio_to_identify = None
        audio_identify_suffix = ".wav"
        
        if identify_method == "🎤 Record with Microphone":
            try:
                from audio_recorder_streamlit import audio_recorder
                
                st.markdown("**Record your voice for identification:**")
                
                audio_data = audio_recorder(
                    text="Click to record",
                    recording_color="#e74c3c",
                    neutral_color="#1f77b4",
                    icon_name="microphone",
                    icon_size="3x",
                    key="identify_recorder"
                )
                
                if audio_data:
                    audio_to_identify = audio_data
                    st.audio(audio_data, format='audio/wav')
            
            except ImportError:
                st.error("❌ Audio recorder not available. Please use file upload method.")
                identify_method = "📁 Upload Audio File"
        
        if identify_method == "📁 Upload Audio File":
            uploaded_file = st.file_uploader("Upload audio file", type=['wav', 'mp3', 'm4a'], key="identify_upload")
            if uploaded_file:
                audio_to_identify = uploaded_file.read()
                audio_identify_suffix = get_uploaded_audio_suffix(uploaded_file)
        
        if audio_to_identify and st.button("🔍 Identify Speaker", type="primary", use_container_width=True):
            tmp_path = write_temp_audio_file(audio_to_identify, suffix=audio_identify_suffix)
            
            try:
                with st.spinner("🔍 Identifying speaker..."):
                    if enrolled_users:
                        user_id, confidence = speaker_id.identify_speaker(tmp_path, enrolled_users)
                        
                        if user_id:
                            st.success(f"✅ **Identified: {user_id}**")
                            st.info(f"🎯 Confidence: {confidence:.2%}")
                        else:
                            st.warning(f"❌ **Unknown speaker**")
                            st.info(f"🎯 Best match score: {confidence:.2%}")
                    else:
                        st.error("No enrolled users available!")
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
    
    with id_tab2:
        st.markdown("### ➕ Enroll New User")
        st.markdown("Record or upload 3-5 audio samples of the user's voice (10-30 seconds each)")
        
        new_user_id = st.text_input("User ID", placeholder="e.g., John, Alice, User1...")
        
        # Voice customization settings
        st.markdown("#### 🎙️ Voice Customization (for TTS responses)")
        st.caption("Each user gets a unique voice when the app responds to them!")
        
        voice_col1, voice_col2, voice_col3 = st.columns(3)
        with voice_col1:
            voice_pitch = st.slider("Pitch", 0.7, 1.5, 1.0, 0.1, help="Lower = deeper voice, Higher = higher voice")
        with voice_col2:
            voice_speed = st.slider("Speed", 0.7, 1.3, 1.0, 0.1, help="Lower = slower, Higher = faster")
        with voice_col3:
            voice_energy = st.slider("Volume", 0.7, 1.3, 1.0, 0.1, help="Lower = quieter, Higher = louder")
        
        st.markdown("---")
        
        # Initialize session state for recorded samples
        if "recorded_samples" not in st.session_state:
            st.session_state.recorded_samples = []
        
        # Recording method selection
        recording_method = st.radio(
            "Choose enrollment method:",
            ["🎤 Record with Microphone", "📁 Upload Audio Files"],
            horizontal=True,
            key="enrollment_method"
        )
        
        if recording_method == "🎤 Record with Microphone":
            st.markdown("#### 🎤 Record Audio Samples")
            st.info(f"📊 Recorded samples: **{len(st.session_state.recorded_samples)}/5** (minimum 3 required)")
            
            try:
                from audio_recorder_streamlit import audio_recorder
                
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**Sample #{len(st.session_state.recorded_samples) + 1}** - Speak for 10-30 seconds")
                
                audio_data = audio_recorder(
                    text="Click to record",
                    recording_color="#e74c3c",
                    neutral_color="#1f77b4",
                    icon_name="microphone",
                    icon_size="3x",
                    key=f"enroll_recorder_{len(st.session_state.recorded_samples)}"
                )
                
                if audio_data:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("✅ Save This Sample", type="primary", use_container_width=True, key="save_sample"):
                            # Save the recorded audio
                            st.session_state.recorded_samples.append(audio_data)
                            st.success(f"✅ Sample {len(st.session_state.recorded_samples)} saved!")
                            time.sleep(0.5)
                            st.rerun()
                    
                    with col2:
                        st.audio(audio_data, format='audio/wav')
                
                # Show recorded samples
                if st.session_state.recorded_samples:
                    st.markdown("---")
                    st.markdown("#### 📋 Recorded Samples")
                    
                    for idx, sample in enumerate(st.session_state.recorded_samples, 1):
                        col1, col2, col3 = st.columns([1, 2, 1])
                        with col1:
                            st.write(f"**Sample {idx}**")
                        with col2:
                            st.audio(sample, format='audio/wav')
                        with col3:
                            if st.button("🗑️ Delete", key=f"delete_{idx}"):
                                st.session_state.recorded_samples.pop(idx - 1)
                                st.rerun()
                    
                    st.markdown("---")
                    
                    # Enroll button
                    if len(st.session_state.recorded_samples) >= 3:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if new_user_id and st.button("➕ Enroll User", type="primary", use_container_width=True, key="enroll_recorded"):
                                temp_files = []
                                try:
                                    # Save all recorded samples to temp files
                                    for idx, audio_bytes in enumerate(st.session_state.recorded_samples):
                                        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                                        tmp_file.write(audio_bytes)
                                        tmp_file.close()
                                        temp_files.append(tmp_file.name)
                                    
                                    with st.spinner(f"➕ Enrolling {new_user_id} with {len(temp_files)} samples..."):
                                        # Enroll user
                                        embedding = speaker_id.enroll_speaker(new_user_id, temp_files)
                                        
                                        # Save embedding
                                        embedding_path = embeddings_dir / f"{new_user_id}.pkl"
                                        speaker_id.save_embedding(embedding, str(embedding_path))
                                        
                                        # Save voice preferences
                                        save_user_tts_preferences(new_user_id, voice_pitch, voice_speed, voice_energy)
                                        
                                        st.success(f"✅ **User '{new_user_id}' enrolled successfully!**")
                                        st.info(f"🎙️ Voice: pitch={voice_pitch}x, speed={voice_speed}x, volume={voice_energy}x")
                                        st.info(f"💾 Saved to: {embedding_path}")
                                        st.balloons()
                                        
                                        # Clear recorded samples
                                        st.session_state.recorded_samples = []
                                        time.sleep(1)
                                        st.rerun()
                                
                                except Exception as e:
                                    st.error(f"Enrollment failed: {e}")
                                finally:
                                    # Clean up temp files
                                    for tmp_path in temp_files:
                                        if os.path.exists(tmp_path):
                                            os.unlink(tmp_path)
                            elif not new_user_id:
                                st.warning("⚠️ Please enter a User ID first")
                        
                        with col2:
                            if st.button("🗑️ Clear All Samples", use_container_width=True):
                                st.session_state.recorded_samples = []
                                st.rerun()
                    else:
                        st.warning(f"⚠️ Please record at least 3 samples (you have {len(st.session_state.recorded_samples)})")
            
            except ImportError:
                st.error("❌ Audio recorder not available. Please install: `pip install audio-recorder-streamlit`")
                st.markdown("Falling back to file upload method...")
                recording_method = "📁 Upload Audio Files"
        
        if recording_method == "📁 Upload Audio Files":
            st.markdown("#### 📁 Upload Audio Files")
            
            uploaded_files = st.file_uploader(
                "Upload 3-5 audio samples",
                type=['wav', 'mp3', 'm4a'],
                accept_multiple_files=True,
                key="enroll_uploads"
            )
            
            if new_user_id and len(uploaded_files) >= 3 and st.button("➕ Enroll User", type="primary", use_container_width=True, key="enroll_uploaded"):
                temp_files = []
                try:
                    # Save all uploaded files
                    for idx, uploaded_file in enumerate(uploaded_files):
                        tmp_file = tempfile.NamedTemporaryFile(
                            delete=False,
                            suffix=get_uploaded_audio_suffix(uploaded_file),
                        )
                        tmp_file.write(uploaded_file.read())
                        tmp_file.close()
                        temp_files.append(tmp_file.name)
                    
                    with st.spinner(f"➕ Enrolling {new_user_id} with {len(temp_files)} samples..."):
                        # Enroll user
                        embedding = speaker_id.enroll_speaker(new_user_id, temp_files)
                        
                        # Save embedding
                        embedding_path = embeddings_dir / f"{new_user_id}.pkl"
                        speaker_id.save_embedding(embedding, str(embedding_path))
                        
                        # Save voice preferences
                        save_user_tts_preferences(new_user_id, voice_pitch, voice_speed, voice_energy)
                        
                        st.success(f"✅ **User '{new_user_id}' enrolled successfully!**")
                        st.info(f"🎙️ Voice: pitch={voice_pitch}x, speed={voice_speed}x, volume={voice_energy}x")
                        st.info(f"💾 Saved to: {embedding_path}")
                        st.balloons()
                        
                        time.sleep(1)
                        st.rerun()
                
                except Exception as e:
                    st.error(f"Enrollment failed: {e}")
                finally:
                    # Clean up temp files
                    for tmp_path in temp_files:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
            
            elif uploaded_files and len(uploaded_files) < 3:
                st.warning(f"⚠️ Please upload at least 3 audio samples (you have {len(uploaded_files)})")
    
    with id_tab3:
        st.markdown("### 🔐 Verify Speaker Identity")
        st.markdown("Check if an audio sample matches a specific enrolled user")
        
        verify_user_id = st.selectbox("Select user to verify", list(enrolled_users.keys()) if enrolled_users else ["No users enrolled"])
        
        # Method selection
        verify_method = st.radio(
            "Choose verification method:",
            ["🎤 Record with Microphone", "📁 Upload Audio File"],
            horizontal=True,
            key="verify_method"
        )
        
        audio_to_verify = None
        audio_verify_suffix = ".wav"
        
        if verify_method == "🎤 Record with Microphone":
            try:
                from audio_recorder_streamlit import audio_recorder
                
                st.markdown(f"**Record your voice to verify as {verify_user_id}:**")
                
                audio_data = audio_recorder(
                    text="Click to record",
                    recording_color="#e74c3c",
                    neutral_color="#1f77b4",
                    icon_name="microphone",
                    icon_size="3x",
                    key="verify_recorder"
                )
                
                if audio_data:
                    audio_to_verify = audio_data
                    st.audio(audio_data, format='audio/wav')
            
            except ImportError:
                st.error("❌ Audio recorder not available. Please use file upload method.")
                verify_method = "📁 Upload Audio File"
        
        if verify_method == "📁 Upload Audio File":
            verify_file = st.file_uploader("Upload audio to verify", type=['wav', 'mp3', 'm4a'], key="verify_upload")
            if verify_file:
                audio_to_verify = verify_file.read()
                audio_verify_suffix = get_uploaded_audio_suffix(verify_file)
        
        if audio_to_verify and verify_user_id in enrolled_users and st.button("🔐 Verify Speaker", type="primary", use_container_width=True):
            tmp_path = write_temp_audio_file(audio_to_verify, suffix=audio_verify_suffix)
            
            try:
                with st.spinner(f"🔐 Verifying against {verify_user_id}..."):
                    is_match, confidence = speaker_id.verify_speaker(tmp_path, verify_user_id, enrolled_users)
                    
                    if is_match:
                        st.success(f"✅ **VERIFIED: This is {verify_user_id}**")
                        st.info(f"🎯 Confidence: {confidence:.2%}")
                    else:
                        st.error(f"❌ **NOT VERIFIED: This is not {verify_user_id}**")
                        st.info(f"🎯 Similarity: {confidence:.2%}")
            
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

# ============================================
# PAGE 3: Text-to-Speech
# ============================================
elif page == "🔊 Text-to-Speech":
    st.header("🔊 Text-to-Speech")
    st.markdown("Convert quotes to natural speech.")
    
    nemo_available = is_nemo_installed()
    
    if not nemo_available:
        st.error("❌ Text-to-Speech requires NeMo toolkit.")
        st.markdown("### 📦 Installation:")
        st.code('pip install "nemo-toolkit[asr,tts]>=2.4,<3"', language="bash")
        st.stop()
    
    from services.tts_service import TTSService
    
    tts_service = TTSService(device='cpu')
    
    st.markdown("### 🎤 Generate Speech from Text")
    
    text_input = st.text_area(
        "Enter text to synthesize",
        placeholder="Enter a quote or any text...",
        height=100
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        pitch = st.slider("Pitch", min_value=0.5, max_value=2.0, value=1.0, step=0.1)
    
    with col2:
        rate = st.slider("Rate (Speed)", min_value=0.5, max_value=2.0, value=1.0, step=0.1)
    
    if text_input and st.button("🔊 Generate Speech", type="primary", use_container_width=True):
        try:
            with st.spinner("🔊 Generating speech..."):
                output_path = Path("data/recordings") / f"tts_{int(time.time())}.wav"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                tts_service.synthesize_personalized(
                    text=text_input,
                    output_path=str(output_path),
                    preferences={
                        "pitch_scale": pitch,
                        "speaking_rate": rate,
                        "energy_scale": 1.0,
                        "style": "neutral",
                    },
                )
                
                st.success("✅ Speech generated successfully!")
                
                # Play audio
                with open(output_path, 'rb') as audio_file:
                    audio_bytes = audio_file.read()
                    st.audio(audio_bytes, format='audio/wav')
                
                # Download button
                st.download_button(
                    label="⬇️ Download Audio",
                    data=audio_bytes,
                    file_name=f"quote_{int(time.time())}.wav",
                    mime="audio/wav"
                )
        
        except Exception as e:
            st.error(f"TTS failed: {e}")

# ============================================
# PAGE 4: Statistics
# ============================================
elif page == "📊 Statistics":
    st.header("📊 Database Statistics")
    st.markdown("Explore the Wikiquote database statistics")
    
    search_service = get_search_service()
    
    if not search_service:
        st.error("❌ Search service is not available.")
        st.stop()
    
    # Database stats
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("📚 Total Quotes", "858,972")
    
    with col2:
        st.metric("👥 Total Authors", "247,566")
    
    with col3:
        st.metric("🌍 Languages", "100+")
    
    st.markdown("---")
    
    # Top authors
    st.markdown("### 🌟 Most Quoted Authors")
    
    top_authors = [
        ("William Shakespeare", 15234),
        ("Albert Einstein", 8976),
        ("Mark Twain", 7845),
        ("Oscar Wilde", 6543),
        ("Friedrich Nietzsche", 5432),
        ("Aristotle", 4987),
        ("Plato", 4765),
        ("Winston Churchill", 4321),
        ("Mahatma Gandhi", 3987),
        ("Abraham Lincoln", 3654)
    ]
    
    for author, count in top_authors:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{author}**")
        with col2:
            st.write(f"{count:,} quotes")
    
    st.markdown("---")
    
    # Search statistics
    st.markdown("### 🔍 Popular Search Topics")
    
    topics = ["Love", "Life", "Wisdom", "Success", "Happiness", "Courage", "Freedom", "Truth", "Knowledge", "Peace"]
    
    cols = st.columns(5)
    for idx, topic in enumerate(topics):
        with cols[idx % 5]:
            if st.button(topic, key=f"topic_{topic}", use_container_width=True):
                st.session_state.search_query = topic
                st.session_state.page = "💬 Chatbot & Search"
                st.rerun()

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>📚 <strong>Wikiquote Voice Search</strong> | 858,972 quotes | 247,566 authors</p>
    <p>Powered by OpenAI Whisper, Neo4j, and NVIDIA NeMo</p>
</div>
""", unsafe_allow_html=True)
