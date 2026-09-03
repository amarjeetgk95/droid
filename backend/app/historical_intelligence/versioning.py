"""
Independent Version Governance for Historical Intelligence Engine — §35
"""
from dataclasses import dataclass

ENGINE_VERSION: str = "2.5.0"
FEATURE_VERSION: str = "1.0.0"
EMBEDDING_VERSION: str = "1.0.0"
NORMALIZATION_VERSION: str = "1.0.0"
RETRIEVAL_VERSION: str = "1.0.0"
SIMILARITY_VERSION: str = "1.0.0"
OUTCOME_VERSION: str = "1.0.0"
STATISTICS_VERSION: str = "1.0.0"
SR_VERSION: str = "1.0.0"
SCHEMA_VERSION: str = "1.0.0"


@dataclass(frozen=True, slots=True)
class VersionManifest:
    engine_version: str = ENGINE_VERSION
    feature_version: str = FEATURE_VERSION
    embedding_version: str = EMBEDDING_VERSION
    normalization_version: str = NORMALIZATION_VERSION
    retrieval_version: str = RETRIEVAL_VERSION
    outcome_version: str = OUTCOME_VERSION
    statistics_version: str = STATISTICS_VERSION
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, str]:
        return {
            "engine_version": self.engine_version,
            "feature_version": self.feature_version,
            "embedding_version": self.embedding_version,
            "normalization_version": self.normalization_version,
            "retrieval_version": self.retrieval_version,
            "outcome_version": self.outcome_version,
            "statistics_version": self.statistics_version,
            "schema_version": self.schema_version,
        }


CURRENT_VERSIONS = VersionManifest()
