import { useEffect, useRef, useState } from "react";
import "./SlideCommit.css";

const PAD = 4;

function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

export default function SlideCommit({
    label = "Slide to analyze",
    doneLabel = "Analyzed",
    errorLabel = "Scan failed",
    onConfirm,
    onDone,
    onError,
    trackColor = "#0b1628",
    handleColor = "#68d4ff",
    successColor = "#34d399",
    dangerColor = "#fb7185",
    width = 280,
    height = 56,
    radius = 16,
    disabled = false,
    className = "",
}) {
    const [phase, setPhase] = useState("idle");
    const [dragging, setDragging] = useState(false);
    const [offset, setOffset] = useState(0);
    const trackRef = useRef(null);
    const pointerIdRef = useRef(null);
    const maxOffset = Math.max(0, width - height - PAD * 2);
    const handleSize = Math.max(36, height - PAD * 2);

    useEffect(() => {
        if (phase === "done") {
            const timer = window.setTimeout(() => setPhase("idle"), 1400);
            return () => window.clearTimeout(timer);
        }
        return undefined;
    }, [phase]);

    useEffect(() => {
        if (phase !== "error") return undefined;
        const timer = window.setTimeout(() => setPhase("idle"), 1500);
        return () => window.clearTimeout(timer);
    }, [phase]);

    const completeSlide = async () => {
        if (disabled) return;
        setPhase("pending");
        try {
            if (onConfirm) {
                const maybePromise = onConfirm();
                if (maybePromise && typeof maybePromise.then === "function") {
                    await maybePromise;
                }
            }
            setPhase("done");
            onDone?.();
        } catch (error) {
            setPhase("error");
            onError?.(error);
        }
    };

    const handlePointerMove = (event) => {
        if (!dragging || pointerIdRef.current !== event.pointerId || !trackRef.current) return;
        const rect = trackRef.current.getBoundingClientRect();
        const next = clamp(event.clientX - rect.left - handleSize / 2, 0, maxOffset);
        setOffset(next);
    };

    const handlePointerUp = (event) => {
        if (pointerIdRef.current !== event.pointerId) return;
        pointerIdRef.current = null;
        setDragging(false);

        if (offset >= maxOffset * 0.9) {
            setOffset(maxOffset);
            completeSlide();
        } else {
            setOffset(0);
        }
    };

    useEffect(() => {
        window.addEventListener("pointermove", handlePointerMove);
        window.addEventListener("pointerup", handlePointerUp);
        window.addEventListener("pointercancel", handlePointerUp);
        return () => {
            window.removeEventListener("pointermove", handlePointerMove);
            window.removeEventListener("pointerup", handlePointerUp);
            window.removeEventListener("pointercancel", handlePointerUp);
        };
    }, [dragging, offset, maxOffset, handleSize]);

    const startDrag = (event) => {
        if (disabled || phase === "pending") return;
        pointerIdRef.current = event.pointerId;
        setDragging(true);
        const rect = trackRef.current?.getBoundingClientRect();
        if (!rect) return;
        const next = clamp(event.clientX - rect.left - handleSize / 2, 0, maxOffset);
        setOffset(next);
    };

    return (
        <div
            className={`slide-commit ${className}`.trim()}
            style={{
                width,
                height,
                borderRadius: radius,
                "--sc-track": trackColor,
                "--sc-ink": handleColor,
                "--sc-ok": successColor,
                "--sc-no": dangerColor,
            }}
            data-disabled={disabled || undefined}
            data-phase={phase}
            data-held={dragging || undefined}
            aria-live="polite"
        >
            <div
                ref={trackRef}
                className="slide-commit__track"
                onPointerDown={startDrag}
                role="slider"
                aria-disabled={disabled}
                aria-label={label}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round((offset / Math.max(1, maxOffset)) * 100)}
            >
                <div className="slide-commit__label" aria-hidden="true">
                    <span className="slide-commit__text slide-commit__text--plain">{phase === "done" ? doneLabel : phase === "error" ? errorLabel : label}</span>
                    <span className="slide-commit__text slide-commit__text--error">{errorLabel}</span>
                </div>

                <div
                    className="slide-commit__capsule"
                    style={{
                        transform: `translateX(${offset}px)`,
                        width: `${handleSize}px`,
                        borderRadius: Math.max(8, radius - PAD),
                    }}
                >
                    <div className="slide-commit__content">
                        <div className="slide-commit__arrow" aria-hidden="true">
                            {phase === "done" ? "✓" : phase === "pending" ? "…" : "→"}
                        </div>
                        <div className="slide-commit__spin" aria-hidden="true">
                            <span className="slide-commit__spinner">⏳</span>
                        </div>
                        <div className="slide-commit__done" aria-hidden="true">✓</div>
                    </div>
                </div>
            </div>
            <span className="slide-commit__sr">{phase === "done" ? doneLabel : phase === "pending" ? "Processing" : phase === "error" ? errorLabel : label}</span>
        </div>
    );
}
