"""Ensure presentation never turns sound measurements into unsupported type claims."""

from pathlib import Path

import pytest
import soundfile as sf

from audio_forensics.inference import analyze_audio
from audio_forensics.interpretation import assess_manipulation

SAMPLE = Path(__file__).with_name("sample.wav")


@pytest.fixture
def unknown_audio(tmp_path):
    waveform, sample_rate = sf.read(SAMPLE)
    target = tmp_path / "argus-demo.wav"
    sf.write(target, waveform * 0.7, sample_rate)
    return target


def test_demo_identity_uses_contents_not_filename(tmp_path, unknown_audio):
    renamed = tmp_path / "some-recording.wav"
    renamed.write_bytes(SAMPLE.read_bytes())
    demo = analyze_audio(str(renamed))
    assert demo["source"] == "known_demo"
    assert demo["manipulation_type"] == "generated_test_audio"
    assert demo["manipulation_assessment"]["status"] == "known_source"
    assert "not a person's voice" in demo["interpretation"]["explanation"]
    assert len(demo["manipulation_assessment"]["categories"]) == 6

    other = analyze_audio(str(unknown_audio))
    assert other["source"] == "uploaded_audio"
    assert other["manipulation_type"] is not None
    assert other["manipulation_assessment"]["status"] == "heuristic"
    assert "feature-based heuristic" in other["interpretation"]["explanation"].lower()
    assert len(other["interpretation"]["insights"]) == 4


@pytest.mark.parametrize("model_label,expected", [
    ("Text-to-speech (TTS)", "tts"),
    ("Voice cloning / voice conversion", "voice_conversion"),
    ("Splicing / partial synthesis", "splicing"),
    ("Audio editing", "audio_editing"),
    ("Fully synthetic speech", "fully_synthetic"),
    ("Real / unmodified", "real"),
])
def test_type_model_categories_are_assessed_independently_of_synthetic_score(unknown_audio, model_label, expected):
    class LowSyntheticScore:
        def predict_synthetic_probability(self, features):
            return 0.1

    class TypeDetector:
        def predict_manipulation_type(self, features):
            return model_label

    result = analyze_audio(str(unknown_audio), model=LowSyntheticScore(), manipulation_model=TypeDetector())
    assert result["synthetic_likelihood"] == 10
    assert result["manipulation_type"] == expected
    assert result["manipulation_assessment"]["status"] == "predicted"
    assert all(segment["manipulation_type"] == expected for segment in result["segments"])
    assert result["manipulation_assessment"]["basis"] == "Type detector prediction"


def test_mixed_or_unsupported_labels_do_not_imply_splicing(unknown_audio):
    class TypeDetector:
        def __init__(self):
            self.labels = iter(["tts", "real", "synthetic"])

        def predict_manipulation_type(self, features):
            return next(self.labels)

    result = analyze_audio(str(unknown_audio), manipulation_model=TypeDetector())
    assert result["manipulation_type"] is None
    assert result["manipulation_assessment"]["status"] == "inconclusive"
    assert "do not prove" in result["manipulation_assessment"]["explanation"]


def test_generic_synthetic_label_does_not_mean_fully_synthetic_speech(unknown_audio):
    class GenericModel:
        def predict_manipulation_type(self, features):
            return "synthetic"

    assessment = assess_manipulation(str(unknown_audio), [{}] * 3, [{} for _ in range(3)], GenericModel())
    assert assessment["type"] is None
    assert assessment["predicted_types"] == []


def test_low_score_alone_does_not_announce_unmodified_audio(unknown_audio):
    class LowScore:
        def predict_synthetic_probability(self, features):
            return 0.0

    result = analyze_audio(str(unknown_audio), model=LowScore())
    assert result["classification"] == "real"
    assert result["manipulation_type"] is None
    assert result["manipulation_assessment"]["status"] == "not_assessed"


def test_baseline_audio_uses_heuristic_type_estimate_when_no_detector_is_available(unknown_audio):
    result = analyze_audio(str(unknown_audio))
    assert result["manipulation_assessment"]["status"] == "heuristic"
    assert result["manipulation_type"] is not None
    assert result["manipulation_assessment"]["basis"] == "Signal-heuristic estimate"


@pytest.mark.parametrize("labels", [
    ["real", "real", "tts"],
    ["fully_synthetic", "fully_synthetic", "real"],
])
def test_whole_recording_labels_require_all_sections_to_agree(unknown_audio, labels):
    class MixedDetector:
        def __init__(self):
            self.labels = iter(labels)

        def predict_manipulation_type(self, features):
            return next(self.labels)

    result = analyze_audio(str(unknown_audio), manipulation_model=MixedDetector())
    assert result["manipulation_type"] is None
    assert result["manipulation_assessment"]["status"] == "inconclusive"


def test_conflicting_detectors_are_explained(unknown_audio):
    class SyntheticDetector:
        def predict_synthetic_probability(self, features):
            return 0.9

    class RealTypeDetector:
        def predict_manipulation_type(self, features):
            return "real"

    result = analyze_audio(str(unknown_audio), model=SyntheticDetector(), manipulation_model=RealTypeDetector())
    assert result["manipulation_type"] == "real"
    assert "disagree" in result["interpretation"]["headline"]
    assert "inconclusive" in result["interpretation"]["explanation"]


def test_type_detector_without_synthetic_model_is_explained(tmp_path):
    waveform, sample_rate = sf.read(SAMPLE)
    target = tmp_path / "unknown.wav"
    sf.write(target, waveform * 0.7, sample_rate)

    class TypeDetector:
        def predict_manipulation_type(self, features):
            return "voice_conversion"

    result = analyze_audio(str(target), manipulation_model=TypeDetector())
    assert result["manipulation_type"] == "voice_conversion"
    assert "type detector" in result["interpretation"]["headline"].lower()
    assert "voice conversion" in result["interpretation"]["explanation"].lower()
