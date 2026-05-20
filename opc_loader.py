from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
OPC_ROOT = PROJECT_ROOT / "autovideo_opc"

OPC_FILES = [
    OPC_ROOT / "_knowledge" / "video_quality_standard.md",
    OPC_ROOT / "_knowledge" / "style_library.md",
    OPC_ROOT / "_rules" / "video_output_rules.md",
    OPC_ROOT / "_skills_agents" / "script_director.md",
    OPC_ROOT / "_skills_agents" / "visual_director.md",
    OPC_ROOT / "_rules" / "content_policy.md",
]

DEFAULT_OPC_CONTEXT = """
AutoVideo Bot must create vertical 9:16 videos with clear structure, strong script, cinematic visuals, readable captions, natural voice, and no unnecessary corner labels or logos.
""".strip()


def read_markdown(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""

    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _trim_context(context: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""

    if len(context) <= max_chars:
        return context

    suffix = "\n\n[OPC context truncated]"
    if max_chars <= len(suffix):
        return context[:max_chars]

    trim_limit = max_chars - len(suffix)
    trimmed = context[:trim_limit].rstrip()
    last_break = trimmed.rfind("\n\n")

    if last_break > trim_limit // 2:
        trimmed = trimmed[:last_break].rstrip()

    return f"{trimmed}{suffix}"


def load_opc_context(max_chars: int = 12000) -> str:
    chunks: list[str] = []

    for path in OPC_FILES:
        content = read_markdown(path).strip()
        if content:
            relative_path = path.relative_to(PROJECT_ROOT)
            chunks.append(f"# {relative_path.as_posix()}\n{content}")

    if not chunks:
        return _trim_context(DEFAULT_OPC_CONTEXT, max_chars)

    context = "\n\n".join(chunks)
    return _trim_context(context, max_chars)
