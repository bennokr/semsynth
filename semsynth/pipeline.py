"""The report pipeline. The code lives in the modules below; this one keeps the old import path working.

- :mod:`semsynth.config`: ``PipelineConfig``
- :mod:`semsynth.preprocess`: ``DatasetPreprocessor`` (types, codebook, complete rows, missingness model)
- :mod:`semsynth.evaluate`: metrics as pure functions
- :mod:`semsynth.synthesis`: ``synthesize`` and ``write_run``
- :mod:`semsynth.runner`: ``process_dataset`` (the only part that writes files)
"""

from __future__ import annotations

from .config import PipelineConfig, UmapConfig
from .preprocess import DatasetPreprocessor, PreprocessingResult, UmapArtifacts
from .runner import BackendExecutor, PipelineDeps, ReportWriter, process_dataset

__all__ = [
    "BackendExecutor",
    "DatasetPreprocessor",
    "PipelineConfig",
    "PipelineDeps",
    "PreprocessingResult",
    "ReportWriter",
    "UmapArtifacts",
    "UmapConfig",
    "process_dataset",
]
