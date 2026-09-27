import { useEffect, useRef, useState } from "react";
import SlideCommit from "./SlideCommit";

const SCAN_PROFILES = [
    { id: "quick", label: "Quick", description: "Rules only" },
    { id: "standard", label: "Standard", description: "Rules + AI agents" },
    { id: "deep", label: "Deep", description: "Full analysis" }
];

function ScanForm({
    repositoryUrl,
    onRepositoryUrlChange,
    scanProfile,
    onScanProfileChange,
    githubToken,
    onGithubTokenChange,
    showTokenField,
    onToggleTokenField,
    loading,
    onSubmit
}) {
    const slideRef = useRef(null);
    const [slideWidth, setSlideWidth] = useState(280);

    useEffect(() => {
        const node = slideRef.current;

        if (!node) {
            return undefined;
        }

        const updateWidth = () => {
            setSlideWidth(Math.max(220, Math.round(node.clientWidth)));
        };

        updateWidth();
        const observer = new ResizeObserver(updateWidth);
        observer.observe(node);

        return () => observer.disconnect();
    }, []);

    return (
        <section className="scan-form" data-reveal>
            <div className="input-section">
                <input
                    type="text"
                    value={repositoryUrl}
                    onChange={(event) => onRepositoryUrlChange(event.target.value)}
                    placeholder="https://github.com/user/repository"
                    disabled={loading}
                    aria-label="GitHub repository URL"
                />

                <div className="scan-slide" ref={slideRef}>
                    <SlideCommit
                        label="Slide to analyze"
                        doneLabel="Analyzed"
                        errorLabel="Scan failed"
                        onConfirm={onSubmit}
                        trackColor="#0b1628"
                        handleColor="#68d4ff"
                        successColor="#34d399"
                        dangerColor="#fb7185"
                        width={slideWidth}
                        height={56}
                        radius={16}
                        speed={55}
                        returnBounce={0.32}
                        holdMs={1800}
                        disabled={loading}
                        className="scan-slide-commit"
                    />
                </div>
            </div>

            <div className="scan-options">
                <div className="option-group">
                    <span className="option-label">Scan profile</span>
                    <div className="profile-selector">
                        {SCAN_PROFILES.map((profile) => (
                            <button
                                key={profile.id}
                                type="button"
                                className={`profile-chip ${scanProfile === profile.id ? "active" : ""}`}
                                onClick={() => onScanProfileChange(profile.id)}
                                disabled={loading}
                                title={profile.description}
                            >
                                {profile.label}
                            </button>
                        ))}
                    </div>
                </div>

                <button
                    type="button"
                    className="link-button"
                    onClick={onToggleTokenField}
                    disabled={loading}
                >
                    {showTokenField ? "Hide token" : "Private repo? Add token"}
                </button>
            </div>

            {showTokenField && (
                <div className="token-field">
                    <input
                        type="password"
                        value={githubToken}
                        onChange={(event) => onGithubTokenChange(event.target.value)}
                        placeholder="GitHub personal access token (repo scope)"
                        disabled={loading}
                        aria-label="GitHub token for private repositories"
                    />
                    <p className="token-hint">
                        Required for private repositories. Token is used only for cloning
                        and is not stored.
                    </p>
                </div>
            )}

        </section>
    );
}

export default ScanForm;
