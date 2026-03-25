from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.services.output_path_service import OutputTargetsCache, load_output_targets
from src.services.skills_service import SkillsState


@dataclass
class AppContext:
    project_root: Path
    skills_root: Path
    config_root: Path
    data_root: Path

    output_targets_path: Path
    preferences_path: Path

    skills_state: SkillsState = field(default_factory=lambda: SkillsState(loaded={}))
    output_targets_cache: OutputTargetsCache = field(default_factory=lambda: OutputTargetsCache(mapping={}, mtime=None))

    def refresh_output_targets(self) -> None:
        self.output_targets_cache = load_output_targets(self.output_targets_path, self.output_targets_cache)


def default_context() -> AppContext:
    project_root = Path(__file__).resolve().parents[2]
    skills_root = project_root / "skills"
    config_root = project_root / "config"
    data_root = project_root / "data"
    ctx = AppContext(
        project_root=project_root,
        skills_root=skills_root,
        config_root=config_root,
        data_root=data_root,
        output_targets_path=config_root / "output_targets.json",
        preferences_path=config_root / "preferences.md",
    )
    ctx.refresh_output_targets()
    return ctx

