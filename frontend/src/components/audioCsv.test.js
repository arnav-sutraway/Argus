import { test } from "node:test";
import assert from "node:assert/strict";
import { buildAudioCsv } from "./audioCsv.js";

test("CSV preserves zero scores and leaves failed predictions blank", () => {
    const csv = buildAudioCsv([
        { filename: "real.wav", synthetic_likelihood: 0, classification: "real", scoring_method: "experimental_baseline" },
        { filename: "bad.wav", synthetic_likelihood: null, classification: "error", error: "Could not decode." },
    ]);
    assert.ok(csv.includes('"real.wav","0","real"'));
    assert.ok(csv.includes('"bad.wav","","error","","","Could not decode."'));
    assert.equal(csv.split("\r\n").length, 4);
});

test("CSV quotes names and neutralizes spreadsheet formulas", () => {
    const csv = buildAudioCsv([{ filename: '=SUM(1,2)"\n.wav', manipulation_type: "+type", error: "@error" }]);
    assert.ok(csv.includes('"' + "'=SUM(1,2)" + '""\n.wav"'));
    assert.ok(csv.includes('"' + "'+type" + '"'));
    assert.ok(csv.includes('"' + "'@error" + '"'));
});

test("CSV carries the manipulation assessment and distinguishes known source from prediction", () => {
    const csv = buildAudioCsv([{
        filename: "demo.wav", synthetic_likelihood: 59.7, classification: "synthetic",
        manipulation_type: "generated_test_audio", scoring_method: "experimental_baseline",
        manipulation_assessment: { label: "Generated test audio", status: "known_source", basis: "Known demo" },
    }]);
    assert.ok(csv.includes("manipulation_label,manipulation_status,manipulation_basis"));
    assert.ok(csv.includes('"Generated test audio","known_source","Known demo"'));
});

test("CSV includes detailed analysis descriptions and AI notes", () => {
    const csv = buildAudioCsv([{
        filename: "demo.wav",
        synthetic_likelihood: 71.2,
        classification: "synthetic",
        manipulation_type: "audio_editing",
        manipulation_assessment: {
            label: "Audio Editing / Real",
            status: "heuristic",
            basis: "Signal-heuristic estimate",
            description: "Audio Editing / Real",
            explanation: "This is the heuristic note."
        },
        interpretation: {
            headline: "Signal cues suggest audio editing / real",
            explanation: "The feature-based heuristic identified the likely pattern.",
            score_label: "Estimated synthetic likelihood",
            score_explanation: "Score estimate with caveats."
        },
        ai_summary: {
            headline: "Recording looks edited but natural",
            notes: [{ label: "Signal analysis", summary: "The waveform is consistent with a real capture." }]
        }
    }]);
    assert.ok(csv.includes("manipulation_description"));
    assert.ok(csv.includes("interpretation_headline"));
    assert.ok(csv.includes("Audio Editing / Real"));
    assert.ok(csv.includes("The feature-based heuristic identified the likely pattern."));
});

test("CSV values are formatted for readability instead of one giant JSON blob", () => {
    const csv = buildAudioCsv([{
        filename: "demo.wav",
        feature_summary: { rms: 0.61, dominant_frequency: 2200, spectral_flux: 0.1 },
        metadata: { duration: 12.5, sample_rate: 48000 },
        segments: [{ start: 0, end: 2, score: 0.81 }, { start: 2, end: 4, score: 0.64 }],
    }]);

    assert.ok(csv.includes("rms: 0.61"));
    assert.ok(csv.includes("dominant_frequency: 2200"));
    assert.ok(csv.includes("duration: 12.5"));
    assert.ok(csv.includes("start: 0"));
    assert.ok(!csv.includes('{"rms":0.61'));
});
