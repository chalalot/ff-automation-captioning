import os
from pydub import AudioSegment
from moviepy import AudioFileClip
from typing import Tuple, Optional

def trim_audio(input_path: str, output_path: str, start_time: float, end_time: float) -> Tuple[Optional[str], Optional[str]]:
    """
    Trims an audio file from start_time to end_time using pydub.
    start_time and end_time are in seconds.
    Returns a tuple of (output_path, None) on success, or (None, error_message) on failure.
    """
    try:
        # Pydub works in milliseconds
        start_ms = int(start_time * 1000)
        end_ms = int(end_time * 1000)
        
        audio = AudioSegment.from_file(input_path)
        trimmed_audio = audio[start_ms:end_ms]
        
        # Determine format based on extension, default to mp3
        ext = os.path.splitext(output_path)[1].lower().replace('.', '')
        if not ext:
            ext = 'mp3'
            
        trimmed_audio.export(output_path, format=ext)
        return output_path, None
    except Exception as e:
        error_msg = str(e)
        print(f"Error trimming audio: {error_msg}")
        return None, error_msg

def get_audio_duration(file_path: str) -> float:
    """
    Returns the duration of the audio file in seconds.
    """
    try:
        with AudioFileClip(file_path) as clip:
            return clip.duration
    except Exception as e:
        print(f"Error getting audio duration: {e}")
        return 0.0
