"""Plain-language results with an explicit basis for every manipulation label."""

import hashlib
import re
from collections import Counter

# Identity of the original generated tone fixture; filenames are not evidence.
DEMO_SHA256 = "cffb29f63dd77e69d297fbb8a8cfa0109d3bb4130f3c62950e450933d339546c"

MANIPULATION_CATEGORIES = [
    {"id": "tts", "label": "Text-to-speech (TTS)",
     "description": "An AI system turns written text into spoken words."},
    {"id": "voice_conversion", "label": "Voice cloning / voice conversion",
     "description": "Speech is generated or transformed to sound like another speaker."},
    {"id": "splicing", "label": "Splicing / partial synthesis",
     "description": "Real audio is mixed with inserted or replaced sections, which may be generated."},
    {"id": "audio_editing", "label": "Audio editing",
     "description": "Audio is cut, combined, sped up, slowed down, or changed in pitch."},
    {"id": "fully_synthetic", "label": "Fully synthetic speech",
     "description": "The whole spoken recording is generated rather than captured from a real speaker."},
    {"id": "real", "label": "Real / unmodified",
     "description": "A recording of a real speaker with no relevant alteration found, using the dataset's definition."},
]
CATEGORY_BY_ID = {category["id"]: category for category in MANIPULATION_CATEGORIES}
ALIASES = {
    "tts": "tts", "text_to_speech": "tts", "text_to_speech_tts": "tts",
    "voice_cloning": "voice_conversion", "voice_conversion": "voice_conversion",
    "voice_cloning_voice_conversion": "voice_conversion", "vc": "voice_conversion",
    "splicing": "splicing", "partial_synthesis": "splicing",
    "splicing_partial_synthesis": "splicing",
    "audio_editing": "audio_editing", "editing": "audio_editing", "edited": "audio_editing",
    "fully_synthetic": "fully_synthetic", "fully_synthetic_speech": "fully_synthetic",
    "real": "real", "unmodified": "real", "real_unmodified": "real",
    "bonafide": "real", "bona_fide": "real",
}


def normalize_manipulation_label(label):
    token = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    # Generic "synthetic" does not establish that the entire file is synthetic.
    return ALIASES.get(token)


def is_known_demo(file_path):
    digest = hashlib.sha256()
    with open(file_path, "rb") as audio:
        for chunk in iter(lambda: audio.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == DEMO_SHA256


def infer_heuristic_manipulation_type(records):
    if not records:
        return None

    def mean_value(key):
        values = [float(record.get(key, 0.0) or 0.0) for record in records]
        return sum(values) / len(values)

    rms = mean_value("rms")
    flatness = mean_value("spectral_flatness")
    flux = mean_value("spectral_flux")
    quiet = mean_value("quiet_frame_ratio")
    dominant = mean_value("dominant_frequency")
    zero_crossing = mean_value("zero_crossing_rate")
    energy = mean_value("energy_variation")
    mfcc_variation = mean_value("mfcc_std_0")

    scores = {
        "real": 0.0,
        "tts": 0.0,
        "voice_conversion": 0.0,
        "splicing": 0.0,
        "audio_editing": 0.0,
        "fully_synthetic": 0.0,
    }

    if rms > 0.55 and flatness < 0.35 and quiet < 0.08:
        scores["real"] += 1.5
    if dominant > 1500 and flatness < 0.3 and zero_crossing > 0.08:
        scores["tts"] += 2.0
    if dominant > 1200 and mfcc_variation > 0.12 and zero_crossing > 0.09:
        scores["voice_conversion"] += 2.0
    if flux > 0.14 or quiet > 0.12 or energy > 0.22:
        scores["splicing"] += 1.5
        scores["audio_editing"] += 2.5
    if flatness < 0.18 and dominant > 2500 and zero_crossing < 0.07:
        scores["fully_synthetic"] += 2.0

    if rms < 0.25 and flatness < 0.5:
        scores["real"] += 1.0
    if mfcc_variation < 0.05 and quiet < 0.05:
        scores["real"] += 0.5

    best_label, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return None

    return best_label


def assess_manipulation(file_path, records, segments, model=None):
    categories = [dict(category) for category in MANIPULATION_CATEGORIES]
    if is_known_demo(file_path):
        return {
            "type": "generated_test_audio", "label": "Generated test audio",
            "status": "known_source", "basis": "Known demo",
            "description": "This is the built-in recording of computer-generated tones.",
            "explanation": "Its contents match the original demo file. It contains no speech, so TTS, voice cloning, and the speech categories below do not apply.",
            "categories": categories, "predicted_types": [],
        }
    if model is None:
        heuristic_type = infer_heuristic_manipulation_type(records)
        if heuristic_type:
            category = CATEGORY_BY_ID[heuristic_type]
            return {
                "type": heuristic_type, "label": category["label"],
                "status": "heuristic", "basis": "Signal-heuristic estimate",
                "description": category["description"],
                "explanation": "The signal summary suggests this recording is more consistent with a heuristic class than with a verified label. It is a useful first-pass cue, not a forensic proof.",
                "categories": categories, "predicted_types": [{"type": heuristic_type, "label": category["label"], "sections": len(segments)}],
            }
        return {
            "type": None, "label": "Type not established",
            "status": "not_assessed", "basis": "More evidence needed",
            "description": "The sound measurements do not identify how this recording was made.",
            "explanation": "This version cannot separate TTS, voice cloning, splicing, editing, and unmodified audio without a trained type detector. A high or low review score does not settle that question.",
            "categories": categories, "predicted_types": [],
        }

    # Editing and partial replacement may occur even when the overall synthetic
    # score is low. Always run an available type model across every section.
    labels = []
    for record, segment in zip(records, segments):
        raw = model.predict_manipulation_type(record)
        label = normalize_manipulation_label(raw)
        labels.append(label)
        segment["manipulation_type"] = label
    counts = Counter(label for label in labels if label is not None)
    predicted_types = [{"type": label, "label": CATEGORY_BY_ID[label]["label"], "sections": count}
                       for label, count in counts.most_common()]
    winner, votes = counts.most_common(1)[0] if counts else (None, 0)
    whole_recording_claim = winner in ("real", "fully_synthetic")
    if votes <= len(records) / 2 or (whole_recording_claim and votes != len(records)):
        return {
            "type": None, "label": "No single type established",
            "status": "inconclusive", "basis": "Inconclusive type prediction",
            "description": "The type detector did not produce a supported majority result.",
            "explanation": "Section predictions disagree or use unsupported labels. Real/unmodified and fully synthetic require agreement across every checked section. Mixed predictions alone do not prove splicing.",
            "categories": categories, "predicted_types": predicted_types,
        }
    category = CATEGORY_BY_ID[winner]
    return {
        "type": winner, "label": category["label"], "status": "predicted",
        "basis": "Type detector prediction", "description": category["description"],
        "explanation": f"The type detector returned this label for {votes} of {len(records)} overlapping sections. This is a model prediction, not a verified finding.",
        "categories": categories, "predicted_types": predicted_types,
    }


def explain_result(summary, segments, probability, threshold, manipulation, trained=False):
    flagged = sum(segment["score"] >= threshold for segment in segments)
    known_demo = manipulation["status"] == "known_source"
    type_prediction = manipulation.get("status") == "predicted"
    if known_demo:
        title = "You're listening to generated test audio"
        explanation = "This demo contains computer-made tones, not a person's voice. Its origin is known from the demo file; the review score is only an example of the checker's output."
    elif manipulation.get("status") == "heuristic":
        label = manipulation.get("label") or manipulation.get("type") or "the likely manipulation type"
        title = f"Signal cues suggest {label.lower()}"
        explanation = (
            f"The feature-based heuristic identified {label} from the recording's measured signal profile. "
            "This is a useful first-pass estimate, not a forensic proof."
        )
    elif trained and (
        (manipulation["type"] == "real" and probability >= threshold)
        or (manipulation["type"] == "fully_synthetic" and probability < threshold)
    ):
        title = "The checks disagree about this recording"
        explanation = "The overall audio check and the type detector give conflicting predictions. Treat the result as inconclusive and review the recording."
    elif type_prediction:
        label = manipulation.get("label") or manipulation.get("type") or "the detected manipulation"
        title = f"The type detector suggests {label.lower()}"
        explanation = (
            f"The type detector identified {label} across the checked sections. "
            "This is a model prediction, not a verified authenticity claim."
        )
    elif trained:
        title = "The model leans toward generated audio" if probability >= threshold else "The model leans toward recorded audio"
        explanation = "This is the model's estimate for the recording. The manipulation assessment below separately explains whether a particular type could be identified."
    else:
        title = "A closer listen is recommended" if flagged else "No sections crossed the review line"
        explanation = f"{flagged} of {len(segments)} checked sections crossed the review line. These sound measurements help you decide where to listen; they do not establish whether the recording is real or generated."

    quiet = summary["quiet_frame_ratio"] * 100
    return {
        "headline": title, "explanation": explanation,
        "score_label": "Estimated synthetic likelihood" if trained else "Review score",
        "score_explanation": (
            f"The file score uses {len(segments)} overlapping sections. The review line is set at {threshold * 100:g} out of 100. "
            + ("A model score is an estimate; its reliability depends on testing with known recordings." if trained else
               "A score of 60 means the checker returned 60 out of 100, not that there is a verified 60% chance the audio is fake.")
        ),
        "insights": [
            {"id": "levels", "title": "Loudness & peaks",
             "finding": f"Peaks average {summary['crest_factor']:.1f} times the usual level",
             "explanation": "This compares loud peaks with the typical signal level in each section. It describes the recording, not whether it was altered."},
            {"id": "tone", "title": "Tone & noise",
             "finding": "Closer to clear tones than hiss" if summary["spectral_flatness"] < 0.5 else "Closer to hiss than clear tones",
             "explanation": "This describes how the sound spreads across low and high tones. Both recorded and generated audio can have this pattern."},
            {"id": "texture", "title": "Sound texture",
             "finding": "Sound patterns measured",
             "explanation": "The checker captures the sound's overall character. These measurements do not identify a speaker or prove that a voice was cloned."},
            {"id": "timing", "title": "Pauses & pacing",
             "finding": f"{quiet:.1f}% of checked sound windows are very quiet",
             "explanation": "This measures brief quiet moments relative to each section's loudest moment. Quiet moments are not evidence of editing on their own."},
        ],
    }
