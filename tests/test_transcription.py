from src.transcription import render_audio_transcript


def test_render_audio_transcript_with_segments():
    payload = {
        "text": "hello world",
        "segments": [
            {"start": 0.0, "end": 2.5, "text": "hello"},
            {"start": 2.5, "end": 5.0, "text": "world"},
        ],
    }
    out = render_audio_transcript(payload)
    assert "[00:00.00 - 00:02.50] SEGMENT 1: hello" in out
    assert "[00:02.50 - 00:05.00] SEGMENT 2: world" in out


def test_render_audio_transcript_falls_back_to_text():
    payload = {"text": "single block", "segments": []}
    out = render_audio_transcript(payload)
    assert "single block" in out
