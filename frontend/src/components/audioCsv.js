export function buildAudioCsv(results) {
    const columns = [
        "filename",
        "synthetic_likelihood",
        "classification",
        "scoring_method",
        "source",
        "error",
        "manipulation_type",
        "manipulation_label",
        "manipulation_status",
        "manipulation_basis",
        "manipulation_description",
        "manipulation_explanation",
        "interpretation_headline",
        "interpretation_explanation",
        "score_label",
        "score_explanation",
        "notice",
        "ai_summary_source",
        "ai_summary_headline",
        "ai_summary_notes",
        "feature_summary",
        "techniques",
        "metadata",
        "segments",
        "runtime_config",
    ];

    const serializeValue = (value) => {
        if (value === null || value === undefined) return "";
        if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
            return String(value);
        }
        if (Array.isArray(value)) {
            return value
                .map((entry) => {
                    if (entry && typeof entry === "object") {
                        return Object.entries(entry)
                            .map(([key, nestedValue]) => `${key}: ${serializeValue(nestedValue)}`)
                            .join(" | ");
                    }
                    return serializeValue(entry);
                })
                .join("\n");
        }
        if (typeof value === "object") {
            return Object.entries(value)
                .map(([key, nestedValue]) => `${key}: ${serializeValue(nestedValue)}`)
                .join("\n");
        }
        return String(value);
    };

    const escape = (value, column) => {
        let text = serializeValue(value);
        if (column !== "synthetic_likelihood" && /^[\s]*[=+\-@]/.test(text)) {
            text = "'" + text;
        }
        return '"' + text.replaceAll('"', '""') + '"';
    };

    return [columns.join(","), ...results.map((result) => {
        const row = {
            ...result,
            manipulation_label: result.manipulation_assessment?.label ?? result.manipulation_label ?? "",
            manipulation_status: result.manipulation_assessment?.status ?? result.manipulation_status ?? "",
            manipulation_basis: result.manipulation_assessment?.basis ?? result.manipulation_basis ?? "",
            manipulation_description: result.manipulation_assessment?.description ?? "",
            manipulation_explanation: result.manipulation_assessment?.explanation ?? "",
            interpretation_headline: result.interpretation?.headline ?? "",
            interpretation_explanation: result.interpretation?.explanation ?? "",
            score_label: result.interpretation?.score_label ?? "",
            score_explanation: result.interpretation?.score_explanation ?? "",
            ai_summary_source: result.ai_summary_source ?? "",
            ai_summary_headline: result.ai_summary?.headline ?? "",
            ai_summary_notes: Array.isArray(result.ai_summary?.notes)
                ? result.ai_summary.notes.map((note) => `${note.label}: ${note.summary}`).join(" | ")
                : "",
            feature_summary: result.feature_summary ? serializeValue(result.feature_summary) : "",
            techniques: Array.isArray(result.techniques) ? serializeValue(result.techniques) : "",
            metadata: result.metadata ? serializeValue(result.metadata) : "",
            segments: Array.isArray(result.segments) ? serializeValue(result.segments) : "",
            runtime_config: result.runtime_config ? serializeValue(result.runtime_config) : "",
        };

        return columns.map((column) => escape(row[column], column)).join(",");
    })].join("\r\n") + "\r\n";
}
