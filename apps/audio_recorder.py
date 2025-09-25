"""Streamlit application for recording audio queries."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

import streamlit as st
from audio_recorder_streamlit import audio_recorder

from wikiquote_voice import Config
from wikiquote_voice.storage import initialize_database

RECORDINGS_DIR = Config.RECORDINGS_DIR


def ensure_recordings_dir() -> None:
    """Ensure the recordings directory exists."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)


def save_audio_file(audio_bytes: bytes) -> Path:
    """Persist the provided audio bytes to a timestamped WAV file."""
    ensure_recordings_dir()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    file_path = RECORDINGS_DIR / f"recording_{timestamp}.wav"
    with open(file_path, "wb") as audio_file:
        audio_file.write(audio_bytes)
    return file_path


def get_recent_recordings(limit: int = 10) -> List[Path]:
    """Return a list of recent recordings sorted by modification time."""
    if not RECORDINGS_DIR.exists():
        return []
    recordings = sorted(
        RECORDINGS_DIR.glob("*.wav"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return recordings[:limit]


def reset_audio_state() -> None:
    """Reset the Streamlit session state used for audio capture."""
    st.session_state.latest_audio = None
    st.session_state.audio_saved = False
    st.session_state.saved_audio_path = None


def initialize_session_state() -> None:
    """Populate Streamlit session state with defaults when required."""
    if "is_recording" not in st.session_state:
        st.session_state.is_recording = False
    if "latest_audio" not in st.session_state:
        st.session_state.latest_audio = None
    if "audio_saved" not in st.session_state:
        st.session_state.audio_saved = False
    if "saved_audio_path" not in st.session_state:
        st.session_state.saved_audio_path = None


def render_recent_recordings() -> None:
    """Display a summary of the most recent audio captures."""
    recordings = get_recent_recordings()
    if not recordings:
        st.info("No recordings saved yet. They will appear here once created.")
        return

    for recording in recordings:
        with st.expander(recording.name, expanded=False):
            st.audio(str(recording), format="audio/wav")
            st.caption(f"Saved on {datetime.fromtimestamp(recording.stat().st_mtime):%Y-%m-%d %H:%M:%S}")


def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(page_title="Wikiquote Voice Recorder", page_icon="🎙️")

    initialize_database(Config.DB_PATH)
    initialize_session_state()

    st.title("🎙️ Wikiquote Voice Search - Audio Recorder")
    st.write(
        "Capture spoken queries and store them as WAV files for later processing. "
        "Use the controls below to start and stop recording."
    )

    with st.sidebar:
        st.header("Storage Status")
        st.write(f"SQLite database: `{Config.DB_PATH}`")
        ensure_recordings_dir()
        st.write(f"Recordings directory: `{RECORDINGS_DIR}`")

    controls = st.columns(2)
    with controls[0]:
        if st.button("Start Recording", use_container_width=True, disabled=st.session_state.is_recording):
            st.session_state.is_recording = True
            reset_audio_state()
    with controls[1]:
        if st.button("Stop Recording", use_container_width=True, disabled=not st.session_state.is_recording):
            st.session_state.is_recording = False

    st.divider()

    audio_bytes = None
    if st.session_state.is_recording:
        st.info("Recording in progress… click the stop button or the square icon in the widget to finish.")
        audio_bytes = audio_recorder(key="audio_recorder")
        if audio_bytes:
            st.session_state.latest_audio = audio_bytes
            st.session_state.is_recording = False
            st.session_state.audio_saved = False

    if st.session_state.latest_audio is not None:
        st.subheader("Latest Recording")
        st.audio(st.session_state.latest_audio, format="audio/wav")

        if not st.session_state.audio_saved:
            saved_path = save_audio_file(st.session_state.latest_audio)
            st.session_state.saved_audio_path = str(saved_path)
            st.session_state.audio_saved = True
            st.success(f"Recording saved as {saved_path.name}")
        else:
            saved_path = Path(st.session_state.saved_audio_path)
            st.success(f"Recording saved as {saved_path.name}")

    st.divider()
    st.subheader("Recent Recordings")
    render_recent_recordings()


if __name__ == "__main__":
    main()
